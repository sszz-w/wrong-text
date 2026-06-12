"""
中文错别字检测与纠正 API 服务
基于 FastAPI，提供 HTTP 接口供其他项目调用
"""

import json
import os
import tempfile
import time
from contextlib import asynccontextmanager
from json import JSONDecodeError

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError

from main import create_corrector, correct_sentence, correct_batch
from pdf_check import check_pdf
from pdf_locator import MatchResult, locate_sentence, locate_sentences, locate_sentences_all

# 上传 PDF 体积上限，防止超大文件耗尽内存。
MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_BATCH_LOCATE_QUERIES = 100

corrector = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global corrector
    print("正在加载纠错模型...")
    start = time.time()
    corrector = create_corrector()
    print(f"模型加载完成，耗时 {time.time() - start:.2f} 秒")
    yield
    corrector = None


app = FastAPI(
    title="中文错别字检测与纠正 API",
    version="1.0.0",
    lifespan=lifespan,
)


class CorrectionRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=512, description="待纠正的文本")


class BatchCorrectionRequest(BaseModel):
    texts: list[str] = Field(..., min_items=1, max_items=32, description="待纠正的文本列表")


class ErrorDetail(BaseModel):
    wrong: str
    correct: str
    position: int


class CorrectionResponse(BaseModel):
    source: str
    target: str
    errors: list[ErrorDetail]
    has_error: bool


class BatchCorrectionResponse(BaseModel):
    results: list[CorrectionResponse]
    total: int
    error_count: int


class PdfErrorDetail(BaseModel):
    page: int
    wrong: str
    correct: str
    position: int
    context: str
    sentence: str
    location: dict | None = None  # /locate 返回的物理坐标，不可达时为 None


class PdfCheckResponse(BaseModel):
    filename: str
    page_count: int
    error_count: int
    errors: list[PdfErrorDetail]


class LocateRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512, description="要定位的文本内容")


class BatchLocateQuery(BaseModel):
    id: str | None = Field(default=None, max_length=128, description="调用方用于回填的查询 ID")
    text: str = Field(..., min_length=1, max_length=512, description="要定位的文本内容")


class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class LocateResponse(BaseModel):
    found: bool
    page: int | None = None
    pageWidth: int | None = None
    pageHeight: int | None = None
    text: str | None = None
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
    match_layer: int | None = None
    bboxes: list[BBox] | None = None
    message: str | None = None


class BatchLocateItemResponse(LocateResponse):
    id: str | None = None
    query: str


class BatchLocateResponse(BaseModel):
    filename: str
    total: int
    found_count: int
    not_found_count: int
    results: list[BatchLocateItemResponse]


class BatchLocateAllItemResponse(BaseModel):
    id: str | None = None
    query: str
    found: bool
    match_count: int
    matches: list[LocateResponse]
    message: str | None = None


class BatchLocateAllResponse(BaseModel):
    filename: str
    total: int
    found_count: int
    not_found_count: int
    total_match_count: int
    results: list[BatchLocateAllItemResponse]


def _format_result(result: dict) -> CorrectionResponse:
    errors = [
        ErrorDetail(wrong=w, correct=r, position=p)
        for w, r, p in result["errors"]
    ]
    return CorrectionResponse(
        source=result["source"],
        target=result["target"],
        errors=errors,
        has_error=len(errors) > 0,
    )


def _parse_batch_locate_queries(raw_queries: str) -> list[BatchLocateQuery]:
    try:
        payload = json.loads(raw_queries)
    except JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"queries 必须是 JSON: {e.msg}")

    if isinstance(payload, dict):
        items = payload.get("queries")
    else:
        items = payload

    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="queries 必须是非空数组")

    if len(items) > MAX_BATCH_LOCATE_QUERIES:
        raise HTTPException(
            status_code=400,
            detail=f"queries 最多支持 {MAX_BATCH_LOCATE_QUERIES} 条",
        )

    parsed: list[BatchLocateQuery] = []
    for index, item in enumerate(items):
        if isinstance(item, str):
            item = {"text": item}
        elif isinstance(item, dict) and "query" in item and "text" not in item:
            item = {**item, "text": item["query"]}

        try:
            parsed.append(BatchLocateQuery(**item))
        except (TypeError, ValidationError) as e:
            raise HTTPException(status_code=400, detail=f"queries[{index}] 无效: {e}")

    return parsed


def _format_locate_result(query: BatchLocateQuery, result: MatchResult | None) -> BatchLocateItemResponse:
    if result is None:
        return BatchLocateItemResponse(
            id=query.id,
            query=query.text,
            found=False,
            message="Sentence not found in PDF.",
        )

    return BatchLocateItemResponse(
        id=query.id,
        query=query.text,
        found=True,
        page=result.page,
        pageWidth=result.pageWidth,
        pageHeight=result.pageHeight,
        text=result.text,
        x=result.x,
        y=result.y,
        width=result.width,
        height=result.height,
        match_layer=result.match_layer,
        bboxes=[BBox(x0=b[0], y0=b[1], x1=b[2], y1=b[3]) for b in result.bboxes],
    )


def _format_locate_match(result: MatchResult) -> LocateResponse:
    return LocateResponse(
        found=True,
        page=result.page,
        pageWidth=result.pageWidth,
        pageHeight=result.pageHeight,
        text=result.text,
        x=result.x,
        y=result.y,
        width=result.width,
        height=result.height,
        match_layer=result.match_layer,
        bboxes=[BBox(x0=b[0], y0=b[1], x1=b[2], y1=b[3]) for b in result.bboxes],
    )


def _format_locate_all_result(
    query: BatchLocateQuery,
    matches: list[MatchResult],
) -> BatchLocateAllItemResponse:
    if not matches:
        return BatchLocateAllItemResponse(
            id=query.id,
            query=query.text,
            found=False,
            match_count=0,
            matches=[],
            message="Sentence not found in PDF.",
        )

    return BatchLocateAllItemResponse(
        id=query.id,
        query=query.text,
        found=True,
        match_count=len(matches),
        matches=[_format_locate_match(match) for match in matches],
    )


@app.post("/correct", response_model=CorrectionResponse)
async def correct_text(req: CorrectionRequest):
    """纠正单个文本中的错别字"""
    result = correct_sentence(corrector, req.text)
    return _format_result(result)


@app.post("/correct/batch", response_model=BatchCorrectionResponse)
async def correct_text_batch(req: BatchCorrectionRequest):
    """批量纠正多个文本中的错别字"""
    results = correct_batch(corrector, req.texts)
    formatted = [_format_result(r) for r in results]
    error_count = sum(1 for r in formatted if r.has_error)
    return BatchCorrectionResponse(
        results=formatted,
        total=len(formatted),
        error_count=error_count,
    )


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "model_loaded": corrector is not None}


@app.post("/correct/pdf", response_model=PdfCheckResponse)
async def correct_pdf(file: UploadFile = File(..., description="待检查的 PDF 招标文件")):
    """上传 PDF 招标文件，返回全文错别字检查结果（带页码和上下文）"""
    filename = file.filename or "uploaded.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，上限 {MAX_PDF_BYTES // (1024 * 1024)} MB",
        )

    try:
        # 放线程池执行：check_pdf 既有阻塞的模型推理，
        # 又会回调同一服务的 /locate，必须让出事件循环避免自调用死锁。
        result = await run_in_threadpool(check_pdf, corrector, pdf_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF 解析失败: {e}")

    return PdfCheckResponse(
        filename=filename,
        page_count=result["page_count"],
        error_count=result["error_count"],
        errors=[PdfErrorDetail(**e) for e in result["errors"]],
    )


@app.post("/locate", response_model=LocateResponse)
async def locate_text(
    file: UploadFile = File(..., description="PDF 文件"),
    query: str = Form(..., description="要查找的文本内容")
):
    """
    在 PDF 中定位指定文本，返回页码、坐标和 bounding box。
    支持三层匹配：精确匹配、归一化匹配、模糊匹配。
    """
    filename = file.filename or "uploaded.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    if not query or len(query.strip()) == 0:
        raise HTTPException(status_code=400, detail="查询文本不能为空")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，上限 {MAX_PDF_BYTES // (1024 * 1024)} MB",
        )

    try:
        # 在线程池执行（pdf_locator 需要写临时文件 + pdfplumber 解析）
        def _locate_with_tempfile():
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(pdf_bytes)
                    tmp_path = tmp.name

                result = locate_sentence(tmp_path, query)
                return result
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        result = await run_in_threadpool(_locate_with_tempfile)

        if result is None:
            return LocateResponse(
                found=False,
                message="Sentence not found in PDF."
            )

        return LocateResponse(
            found=True,
            page=result.page,
            pageWidth=result.pageWidth,
            pageHeight=result.pageHeight,
            text=result.text,
            x=result.x,
            y=result.y,
            width=result.width,
            height=result.height,
            match_layer=result.match_layer,
            bboxes=[BBox(x0=b[0], y0=b[1], x1=b[2], y1=b[3]) for b in result.bboxes]
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"定位失败: {e}")


@app.post("/locate/batch", response_model=BatchLocateResponse)
async def locate_text_batch(
    file: UploadFile = File(..., description="PDF 文件"),
    queries: str = Form(..., description="JSON 数组，或包含 queries 字段的 JSON 对象"),
):
    """
    在同一个 PDF 中批量定位多段原文，返回每段文本的页码、坐标和 bounding box。
    """
    filename = file.filename or "uploaded.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    batch_queries = _parse_batch_locate_queries(queries)

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，上限 {MAX_PDF_BYTES // (1024 * 1024)} MB",
        )

    try:
        def _locate_batch_with_tempfile():
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(pdf_bytes)
                    tmp_path = tmp.name

                return locate_sentences(tmp_path, [item.text for item in batch_queries])
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        matches = await run_in_threadpool(_locate_batch_with_tempfile)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"定位失败: {e}")

    results = [
        _format_locate_result(query, match)
        for query, match in zip(batch_queries, matches)
    ]
    found_count = sum(1 for item in results if item.found)

    return BatchLocateResponse(
        filename=filename,
        total=len(results),
        found_count=found_count,
        not_found_count=len(results) - found_count,
        results=results,
    )


@app.post("/locate/batch/all", response_model=BatchLocateAllResponse)
async def locate_text_batch_all(
    file: UploadFile = File(..., description="PDF 文件"),
    queries: str = Form(..., description="JSON 数组，或包含 queries 字段的 JSON 对象"),
):
    """
    在同一个 PDF 中批量定位多段原文，并返回每段文本的全部匹配位置。
    """
    filename = file.filename or "uploaded.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    batch_queries = _parse_batch_locate_queries(queries)

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，上限 {MAX_PDF_BYTES // (1024 * 1024)} MB",
        )

    try:
        def _locate_batch_all_with_tempfile():
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(pdf_bytes)
                    tmp_path = tmp.name

                return locate_sentences_all(tmp_path, [item.text for item in batch_queries])
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        all_matches = await run_in_threadpool(_locate_batch_all_with_tempfile)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"定位失败: {e}")

    results = [
        _format_locate_all_result(query, matches)
        for query, matches in zip(batch_queries, all_matches)
    ]
    found_count = sum(1 for item in results if item.found)
    total_match_count = sum(item.match_count for item in results)

    return BatchLocateAllResponse(
        filename=filename,
        total=len(results),
        found_count=found_count,
        not_found_count=len(results) - found_count,
        total_match_count=total_match_count,
        results=results,
    )
