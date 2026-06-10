"""
PDF 招标文件错别字检查
负责：从 PDF 抽取文字（带页码）→ 安全切分为不超过模型上限的片段 →
调用纠错逻辑 → 将错误定位回页码并附带上下文 →
调用 pdf_locator 获取错字所在句在 PDF 中的物理坐标。
"""

import os
import re
import tempfile

import fitz  # PyMuPDF

from main import correct_batch, filter_errors
from pdf_locator import locate_sentence, MatchResult

# MacBERT 单次输入上限 512 token，中文约 1 字 1 token，
# 留出余量按字符数切分，避免被静默截断。
MAX_CHARS = 480
# 句子结束标点，按这些切句最自然。
SENT_END = "。！？；!?;\n"
# 上下文截取长度（错误位置前后各取多少字符用于人工核对）。
CONTEXT_RADIUS = 15


def extract_pages(pdf_bytes: bytes) -> list[str]:
    """从 PDF 字节流抽取每页文字，返回页文本列表（索引 0 即第 1 页）。"""
    pages = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            pages.append(page.get_text("text"))
    return pages


def split_text(text: str, max_chars: int = MAX_CHARS) -> list[tuple[int, str]]:
    """
    将一页文字切成不超过 max_chars 的片段。
    返回 (片段在本页文本中的起始下标, 片段文本) 列表，
    起始下标用于把片段内的错误位置还原成页内绝对位置。
    """
    chunks = []
    pos = 0
    n = len(text)
    while pos < n:
        end = min(pos + max_chars, n)
        if end < n:
            # 尽量在句末标点处断开，避免切碎句子影响纠错质量。
            window = text[pos:end]
            cut = max(window.rfind(c) for c in SENT_END)
            if cut > 0:
                end = pos + cut + 1
        segment = text[pos:end]
        if segment.strip():
            chunks.append((pos, segment))
        pos = end
    return chunks


def _context(page_text: str, abs_pos: int) -> str:
    """取页内绝对位置周围的文字片段，单行展示，便于人工定位。"""
    start = max(0, abs_pos - CONTEXT_RADIUS)
    end = min(len(page_text), abs_pos + CONTEXT_RADIUS + 1)
    snippet = page_text[start:end].replace("\n", " ").strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(page_text) else ""
    return f"{prefix}{snippet}{suffix}"


def _sentence_at(page_text: str, abs_pos: int) -> str:
    """
    取页内绝对位置所在的整句（以句末标点/换行为边界），
    去掉内部空白后作为 /locate 的查询文本——中文无空格，
    PDF 抽取产生的换行/空格会干扰匹配，统一清除。
    """
    start = abs_pos
    while start > 0 and page_text[start - 1] not in SENT_END:
        start -= 1
    end = abs_pos
    n = len(page_text)
    while end < n and page_text[end] not in SENT_END:
        end += 1
    sentence = page_text[start:end + 1] if end < n else page_text[start:end]
    return re.sub(r"\s+", "", sentence)


def _match_to_location(m: MatchResult) -> dict:
    """把 pdf_locator 的 MatchResult 转成接口返回用的 location 字典。"""
    return {
        "page": m.page,
        "pageWidth": m.pageWidth,
        "pageHeight": m.pageHeight,
        "text": m.text,
        "x": m.x,
        "y": m.y,
        "width": m.width,
        "height": m.height,
        "match_layer": m.match_layer,
        # bboxes 是每行一个 (x0, y0, x1, y1) 元组，转成字典更直观。
        "bboxes": [
            {"x0": b[0], "y0": b[1], "x1": b[2], "y1": b[3]} for b in m.bboxes
        ],
    }


def locate_errors(pdf_bytes: bytes, errors: list[dict]) -> None:
    """
    就地为每个错误补充 location 字段（PDF 物理坐标）。
    按 sentence 去重，同一句只定位一次；定位失败降级为 location=None，
    不影响错字结果本身。
    """
    if not errors:
        return

    # 按查询句去重：句子 -> 共享该句的错误列表。
    by_query: dict[str, list[dict]] = {}
    for err in errors:
        err["location"] = None
        by_query.setdefault(err["sentence"], []).append(err)

    # pdf_locator 接收文件路径，把字节写入临时文件（只写一次）。
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        for query, group in by_query.items():
            if not query:
                continue
            try:
                match = locate_sentence(tmp_path, query)
            except Exception:
                # 定位异常：保持 location=None，best-effort。
                continue
            if match is None:
                continue
            location = _match_to_location(match)
            for err in group:
                err["location"] = location
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def check_pdf(corrector, pdf_bytes: bytes, locate: bool = True) -> dict:
    """
    对整份 PDF 做错别字检查。
    返回结构：每个错误带页码、错字、正字、页内位置、上下文，
    以及（locate=True 时）通过 pdf_locator 获得的 PDF 物理坐标。
    """
    pages = extract_pages(pdf_bytes)

    # 收集所有待纠错片段，并记住每个片段属于哪一页、页内起始位置。
    segments = []  # (page_index, start_in_page, segment_text)
    for page_idx, page_text in enumerate(pages):
        for start, segment in split_text(page_text):
            segments.append((page_idx, start, segment))

    errors = []
    if segments:
        texts = [seg for _, _, seg in segments]
        # 分批送入模型，控制单次显存/内存占用。
        BATCH = 32
        results = []
        for i in range(0, len(texts), BATCH):
            results.extend(correct_batch(corrector, texts[i:i + BATCH]))

        for (page_idx, start, _), result in zip(segments, results):
            for wrong, right, seg_pos in result["errors"]:
                abs_pos = start + seg_pos
                errors.append({
                    "page": page_idx + 1,
                    "wrong": wrong,
                    "correct": right,
                    "position": abs_pos,
                    "context": _context(pages[page_idx], abs_pos),
                    "sentence": _sentence_at(pages[page_idx], abs_pos),
                })

    if locate:
        locate_errors(pdf_bytes, errors)

    return {
        "page_count": len(pages),
        "error_count": len(errors),
        "errors": errors,
    }
