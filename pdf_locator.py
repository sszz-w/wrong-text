"""
PDF sentence locator — returns page number and bounding box for a target sentence.

Matching layers:
  1. Exact match
  2. Normalized match (strip spaces/newlines, full/half-width unification)
  3. Fuzzy match (difflib, for minor textual differences)

Optional: highlight=True writes a new PDF with the matched regions highlighted.
"""

import unicodedata
import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber
try:
    import fitz  # pymupdf — optional, only needed for highlight output
except ImportError:
    fitz = None


@dataclass
class HighlightOptions:
    enabled: bool = False
    output_path: Optional[str] = None   # None → auto: "<input>_highlighted.pdf"
    color: tuple = (1, 1, 0)            # RGB 0-1, default yellow
    opacity: float = 0.4
    comment: Optional[str] = None       # popup note attached to the highlight


@dataclass
class MatchResult:
    page: int               # 1-based (页码)
    pageHeight: int         # 页面高度
    pageWidth: int          # 页面宽度
    text: str               # 文本块内容
    x: int                  # 文本块起始位置 x 轴坐标
    y: int                  # 文本块起始位置 y 轴坐标
    width: int              # 文本块宽度
    height: int             # 文本块高度
    bboxes: list[tuple]     # one (x0, y0, x1, y1) per line, in PDF points (保留原有字段)
    match_layer: int        # 1, 2, or 3
    highlighted_path: Optional[str] = field(default=None)  # set when highlight written


def _normalize(text: str) -> str:
    """Remove spaces/newlines and unify full/half-width characters."""
    text = unicodedata.normalize("NFKC", text)
    return "".join(text.split())


def _extract_chars(page) -> list[dict]:
    """Return list of {char, x0, y0, x1, y1} for every character on the page."""
    chars = []
    for ch in page.chars:
        chars.append({
            "char": ch["text"],
            "x0": ch["x0"],
            "y0": ch["top"],
            "x1": ch["x1"],
            "y1": ch["bottom"],
        })
    return chars


def _bboxes_of_chars(chars: list[dict], indices: list[int], line_tol: float = 2.0) -> list[tuple]:
    """Group matched chars by line (y0 within line_tol) and return one bbox per line."""
    selected = [chars[i] for i in indices]
    if not selected:
        return []

    # Sort by y0 then x0
    selected = sorted(selected, key=lambda c: (c["y0"], c["x0"]))

    lines: list[list[dict]] = []
    current_line: list[dict] = [selected[0]]
    for ch in selected[1:]:
        if abs(ch["y0"] - current_line[0]["y0"]) <= line_tol:
            current_line.append(ch)
        else:
            lines.append(current_line)
            current_line = [ch]
    lines.append(current_line)

    return [
        (
            min(c["x0"] for c in line),
            min(c["y0"] for c in line),
            max(c["x1"] for c in line),
            max(c["y1"] for c in line),
        )
        for line in lines
    ]


def _try_exact(raw_text: str, query: str, chars: list[dict]) -> Optional[list[tuple]]:
    """Layer 1: exact substring match in raw char sequence."""
    idx = raw_text.find(query)
    if idx == -1:
        return None
    return _bboxes_of_chars(chars, list(range(idx, idx + len(query))))


def _find_all_indices(text: str, query: str) -> list[int]:
    indices = []
    start = 0
    while True:
        idx = text.find(query, start)
        if idx == -1:
            return indices
        indices.append(idx)
        start = idx + max(len(query), 1)


def _try_exact_all(raw_text: str, query: str, chars: list[dict]) -> list[list[tuple]]:
    """Layer 1: all exact substring matches in raw char sequence."""
    return [
        _bboxes_of_chars(chars, list(range(idx, idx + len(query))))
        for idx in _find_all_indices(raw_text, query)
    ]


def _try_normalized(raw_text: str, query: str, chars: list[dict]) -> Optional[list[tuple]]:
    """Layer 2: match after normalizing both sides; map back to original indices."""
    norm_query = _normalize(query)
    norm_text = ""
    norm_to_orig = []
    for i, ch in enumerate(chars):
        n = _normalize(ch["char"])
        if n:
            norm_to_orig.append(i)
            norm_text += n

    idx = norm_text.find(norm_query)
    if idx == -1:
        return None
    orig_indices = norm_to_orig[idx: idx + len(norm_query)]
    return _bboxes_of_chars(chars, orig_indices)


def _normalized_text_with_orig_indices(chars: list[dict]) -> tuple[str, list[int]]:
    norm_text = ""
    norm_to_orig = []
    for i, ch in enumerate(chars):
        n = _normalize(ch["char"])
        if n:
            norm_to_orig.append(i)
            norm_text += n
    return norm_text, norm_to_orig


def _try_normalized_all(raw_text: str, query: str, chars: list[dict]) -> list[list[tuple]]:
    """Layer 2: all normalized matches mapped back to original character boxes."""
    norm_query = _normalize(query)
    norm_text, norm_to_orig = _normalized_text_with_orig_indices(chars)
    return [
        _bboxes_of_chars(chars, norm_to_orig[idx: idx + len(norm_query)])
        for idx in _find_all_indices(norm_text, norm_query)
    ]


def _try_fuzzy(raw_text: str, query: str, chars: list[dict],
               threshold: float = 0.85) -> Optional[tuple]:
    """Layer 3: sliding window fuzzy match over normalized text."""
    norm_query = _normalize(query)
    norm_text = ""
    norm_to_orig = []
    for i, ch in enumerate(chars):
        n = _normalize(ch["char"])
        if n:
            norm_to_orig.append(i)
            norm_text += n

    qlen = len(norm_query)
    best_ratio, best_idx = 0.0, -1
    step = max(1, qlen // 4)
    for start in range(0, len(norm_text) - qlen + 1, step):
        window = norm_text[start: start + qlen]
        ratio = difflib.SequenceMatcher(None, norm_query, window).ratio()
        if ratio > best_ratio:
            best_ratio, best_idx = ratio, start

    # Refine around best_idx with step=1
    for start in range(max(0, best_idx - step), min(len(norm_text) - qlen + 1, best_idx + step + 1)):
        window = norm_text[start: start + qlen]
        ratio = difflib.SequenceMatcher(None, norm_query, window).ratio()
        if ratio > best_ratio:
            best_ratio, best_idx = ratio, start

    if best_ratio < threshold or best_idx == -1:
        return None

    orig_indices = norm_to_orig[best_idx: best_idx + qlen]
    return _bboxes_of_chars(chars, orig_indices), best_ratio


def _add_freetext_comment(page, rect: "fitz.Rect", comment: str) -> None:
    """
    Add a FreeText annotation next to `rect` containing `comment`.
    FreeText bakes text into its own appearance stream so it renders
    correctly in all viewers regardless of popup support.
    """
    note_rect = fitz.Rect(rect.x1 + 4, rect.y0, rect.x1 + 184, rect.y0 + 60)
    note = page.add_freetext_annot(
        note_rect,
        comment,
        fontsize=9,
        text_color=(0, 0, 0),
        fill_color=(1, 1, 0.8),
    )
    note.update()


def _write_highlight(pdf_path: str, result: MatchResult, opts: HighlightOptions) -> str:
    """
    Write a copy of pdf_path with result.bboxes highlighted on result.page.
    pdfplumber uses top-left origin; pymupdf uses bottom-left — y coords are flipped.
    Returns the output path.
    """
    if fitz is None:
        raise ImportError("pymupdf is required for highlight output: pip install pymupdf")

    out_path = opts.output_path or str(
        Path(pdf_path).with_stem(Path(pdf_path).stem + "_highlighted")
    )

    doc = fitz.open(pdf_path)
    page = doc[result.page - 1]          # 0-based

    for x0, y0, x1, y1 in result.bboxes:
        # pdfplumber top/bottom are already top-left origin, y-down — same as pymupdf Rect
        rect = fitz.Rect(x0, y0, x1, y1)
        annot = page.add_highlight_annot(rect)
        annot.set_colors(stroke=opts.color)
        annot.set_opacity(opts.opacity)
        annot.update()

    if opts.comment and result.bboxes:
        # Attach a single FreeText note anchored to the last highlight line
        last = fitz.Rect(*result.bboxes[-1])
        _add_freetext_comment(page, last, opts.comment)

    doc.save(out_path)
    doc.close()
    return out_path


def _match_query_on_page(raw_text: str, query: str, chars: list[dict]) -> Optional[tuple[list[tuple], str, int]]:
    bboxes = _try_exact(raw_text, query, chars)
    if bboxes:
        return bboxes, query, 1

    bboxes = _try_normalized(raw_text, query, chars)
    if bboxes:
        return bboxes, _normalize(query), 2

    fuzzy = _try_fuzzy(raw_text, query, chars)
    if fuzzy:
        bboxes, ratio = fuzzy
        return bboxes, f"fuzzy(ratio={ratio:.2f})", 3

    return None


def _match_query_all_on_page(raw_text: str, query: str, chars: list[dict]) -> list[tuple[list[tuple], str, int]]:
    matches = _try_exact_all(raw_text, query, chars)
    if matches:
        return [(bboxes, query, 1) for bboxes in matches]

    matches = _try_normalized_all(raw_text, query, chars)
    if matches:
        return [(bboxes, _normalize(query), 2) for bboxes in matches]

    fuzzy = _try_fuzzy(raw_text, query, chars)
    if fuzzy:
        bboxes, ratio = fuzzy
        return [(bboxes, f"fuzzy(ratio={ratio:.2f})", 3)]

    return []


def _build_match_result(
    page_num: int,
    page_width: int,
    page_height: int,
    matched_text: str,
    bboxes: list[tuple],
    match_layer: int,
) -> MatchResult:
    x0_min = int(min(bbox[0] for bbox in bboxes))
    y0_min = int(min(bbox[1] for bbox in bboxes))
    x1_max = int(max(bbox[2] for bbox in bboxes))
    y1_max = int(max(bbox[3] for bbox in bboxes))

    return MatchResult(
        page=page_num,
        pageHeight=page_height,
        pageWidth=page_width,
        text=matched_text,
        x=x0_min,
        y=y0_min,
        width=x1_max - x0_min,
        height=y1_max - y0_min,
        bboxes=bboxes,
        match_layer=match_layer
    )


def locate_sentences(pdf_path: str, queries: list[str]) -> list[Optional[MatchResult]]:
    """
    Search multiple queries in one PDF pass.
    Returns one result per query, preserving input order.
    """
    results: list[Optional[MatchResult]] = [None] * len(queries)
    pending = set(range(len(queries)))

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            if not pending:
                break

            chars = _extract_chars(page)
            if not chars:
                continue

            raw_text = "".join(c["char"] for c in chars)
            page_width = int(page.width)
            page_height = int(page.height)

            for query_index in list(pending):
                match = _match_query_on_page(raw_text, queries[query_index], chars)
                if not match:
                    continue

                bboxes, matched_text, match_layer = match
                results[query_index] = _build_match_result(
                    page_num=page_num,
                    page_width=page_width,
                    page_height=page_height,
                    matched_text=matched_text,
                    bboxes=bboxes,
                    match_layer=match_layer,
                )
                pending.remove(query_index)

    return results


def locate_sentences_all(pdf_path: str, queries: list[str]) -> list[list[MatchResult]]:
    """
    Search all occurrences for multiple queries in one PDF pass.
    Returns one result list per query, preserving input order.
    """
    results: list[list[MatchResult]] = [[] for _ in queries]

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            chars = _extract_chars(page)
            if not chars:
                continue

            raw_text = "".join(c["char"] for c in chars)
            page_width = int(page.width)
            page_height = int(page.height)

            for query_index, query in enumerate(queries):
                for bboxes, matched_text, match_layer in _match_query_all_on_page(raw_text, query, chars):
                    results[query_index].append(
                        _build_match_result(
                            page_num=page_num,
                            page_width=page_width,
                            page_height=page_height,
                            matched_text=matched_text,
                            bboxes=bboxes,
                            match_layer=match_layer,
                        )
                    )

    return results


def locate_sentence(
    pdf_path: str,
    query: str,
    highlight: HighlightOptions = HighlightOptions(),
) -> Optional[MatchResult]:
    """
    Search for `query` in `pdf_path` using three matching layers.
    If highlight.enabled is True, writes a highlighted copy of the PDF.
    Returns the first match found, or None.
    """
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            chars = _extract_chars(page)
            if not chars:
                continue
            raw_text = "".join(c["char"] for c in chars)

            # Get page dimensions
            page_width = int(page.width)
            page_height = int(page.height)

            match = _match_query_on_page(raw_text, query, chars)
            if match:
                bboxes, matched_text, match_layer = match
                break
        else:
            return None

    result = _build_match_result(
        page_num=page_num,
        page_width=page_width,
        page_height=page_height,
        matched_text=matched_text,
        bboxes=bboxes,
        match_layer=match_layer,
    )

    if highlight.enabled:
        result.highlighted_path = _write_highlight(pdf_path, result, highlight)

    return result


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Locate a sentence in a PDF.")
    parser.add_argument("pdf_path")
    parser.add_argument("query")
    parser.add_argument("--highlight", action="store_true",
                        help="Write a highlighted copy of the PDF")
    parser.add_argument("--output", default=None,
                        help="Output path for highlighted PDF (default: auto)")
    parser.add_argument("--color", default="1,1,0",
                        help="Highlight RGB color as r,g,b in 0-1 range (default: 1,1,0 yellow)")
    parser.add_argument("--opacity", type=float, default=0.4,
                        help="Highlight opacity 0-1 (default: 0.4)")
    parser.add_argument("--comment", default=None,
                        help="Popup note text attached to each highlight")
    args = parser.parse_args()

    color = tuple(float(v) for v in args.color.split(","))
    hl_opts = HighlightOptions(
        enabled=args.highlight,
        output_path=args.output,
        color=color,
        opacity=args.opacity,
        comment=args.comment,
    )

    result = locate_sentence(args.pdf_path, args.query, highlight=hl_opts)
    if result:
        print(f"Found on page {result.page} (layer {result.match_layer})")
        print(f"Page dimensions: {result.pageWidth} x {result.pageHeight}")
        print(f"Text block position: x={result.x}, y={result.y}")
        print(f"Text block size: width={result.width}, height={result.height}")
        print(f"Matched text: {result.text}")
        print(f"Detailed bboxes:")
        for i, bbox in enumerate(result.bboxes, start=1):
            print(f"  Line {i}: {bbox}")
        if result.highlighted_path:
            print(f"Highlighted PDF: {result.highlighted_path}")
    else:
        print("Sentence not found in PDF.")
