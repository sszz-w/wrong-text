"""
中文错别字检测与纠正 API 服务
基于 FastAPI，提供 HTTP 接口供其他项目调用
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from main import create_corrector, correct_sentence, correct_batch
from pdf_check import check_pdf
from pdf_locator import locate_sentence

# 上传 PDF 体积上限，防止超大文件耗尽内存。
MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB

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
        import tempfile
        import os

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
