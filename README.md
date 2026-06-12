# 中文错别字检测与 PDF 原文定位服务

基于 pycorrector 的中文错别字检测服务，专为招标文件等专业文档设计，提供错别字检测和 PDF 原文精确定位功能。

## 核心功能

- **文本纠错**：单句/批量纠错，支持 MacBERT 和规则模型
- **PDF 全文检查**：上传 PDF 招标文件，自动检测全文错别字
- **原文精确定位**：返回错字在 PDF 中的页码、坐标、bounding box
- **HTTP API**：FastAPI 接口，易于集成到其他系统

## 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境（推荐 Python 3.11-3.12）
python3.12 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 模型准备

默认使用 MacBERT 模型，需下载到 `models/macbert4csc/` 目录：

```bash
# 使用 huggingface-cli 下载（约 391MB）
huggingface-cli download shibing624/macbert4csc-base-chinese \
  --local-dir models/macbert4csc
```

### 3. 启动服务

```bash
source venv/bin/activate
uvicorn app:app --host 0.0.0.0 --port 12342 --workers 2
```

服务启动后访问 http://localhost:12342/docs 查看 API 文档。

## API 接口

### 1. 文本纠错

**单句纠错**：
```bash
curl -X POST http://localhost:12342/correct \
  -H "Content-Type: application/json" \
  -d '{"text": "少先队员因该为老人让坐"}'
```

**批量纠错**（最多 32 条）：
```bash
curl -X POST http://localhost:12342/correct/batch \
  -H "Content-Type: application/json" \
  -d '{"texts": ["今天新情很好", "我也很高心"]}'
```

### 2. PDF 招标文件检查

```bash
curl -X POST http://localhost:12342/correct/pdf \
  -F "file=@招标文件.pdf"
```

**返回示例**：
```json
{
  "filename": "招标文件.pdf",
  "page_count": 12,
  "error_count": 2,
  "errors": [
    {
      "page": 1,
      "wrong": "段",
      "correct": "断",
      "position": 455,
      "context": "…根据历史数据不段优化轧制规程…",
      "sentence": "系统应具备自学习功能，能够根据历史数据不段优化轧制规程。",
      "location": {
        "page": 1,
        "pageWidth": 595,
        "pageHeight": 842,
        "x": 90,
        "y": 329,
        "width": 280,
        "height": 10,
        "match_layer": 1,
        "bboxes": [
          {"x0": 90.0, "y0": 329.0, "x1": 370.0, "y1": 339.0}
        ]
      }
    }
  ]
}
```

**字段说明**：
- `page` / `position`：错字所在页码和页内字符下标
- `context` / `sentence`：错字上下文片段和所在完整句子
- `location`：错字在 PDF 中的物理坐标（x/y 坐标、宽高、精确 bboxes）
- `match_layer`：定位方式（1=精确匹配，2=归一化匹配，3=模糊匹配）
- `location` 为 `null` 时表示定位失败，不影响错字结果本身

### 3. 原文定位

在 PDF 中独立定位任意文本，返回页码和精确坐标（不依赖纠错，可单独调用）。

```bash
curl -X POST http://localhost:12342/locate \
  -F "file=@文档.pdf" \
  -F "query=要查找的文本"
```

**找到时返回**：
```json
{
  "found": true,
  "page": 1,
  "pageWidth": 595,
  "pageHeight": 842,
  "text": "本次招标为道路改造工程",
  "x": 95,
  "y": 72,
  "width": 121,
  "height": 11,
  "match_layer": 1,
  "bboxes": [
    {"x0": 95.0, "y0": 72.7, "x1": 216.0, "y1": 83.7}
  ]
}
```

**未找到时返回**：
```json
{
  "found": false,
  "message": "Sentence not found in PDF."
}
```

### 4. 批量原文定位

在同一个 PDF 中一次定位多段原文，适合把纠错结果、审核项或业务条款批量回填到 PDF 坐标。
每条文本只返回第一处匹配位置。

**请求格式**：`multipart/form-data`

- `file`：PDF 文件
- `queries`：JSON 字符串，支持字符串数组或带 ID 的对象数组

```bash
curl -X POST http://localhost:12342/locate/batch \
  -F "file=@文档.pdf" \
  -F 'queries={"queries":[{"id":"q1","text":"本次招标为道路改造工程"},{"id":"q2","text":"质量保证期"}]}'
```

也可以传简单数组：

```bash
curl -X POST http://localhost:12342/locate/batch \
  -F "file=@文档.pdf" \
  -F 'queries=["本次招标为道路改造工程","质量保证期"]'
```

**返回示例**：

```json
{
  "filename": "文档.pdf",
  "total": 2,
  "found_count": 1,
  "not_found_count": 1,
  "results": [
    {
      "id": "q1",
      "query": "本次招标为道路改造工程",
      "found": true,
      "page": 1,
      "pageWidth": 595,
      "pageHeight": 842,
      "text": "本次招标为道路改造工程",
      "x": 95,
      "y": 72,
      "width": 121,
      "height": 11,
      "match_layer": 1,
      "bboxes": [
        {"x0": 95.0, "y0": 72.7, "x1": 216.0, "y1": 83.7}
      ],
      "message": null
    },
    {
      "id": "q2",
      "query": "质量保证期",
      "found": false,
      "message": "Sentence not found in PDF."
    }
  ]
}
```

**限制**：

- 单个 PDF 文件大小上限：20 MB
- 单次最多定位 100 条文本
- 每条文本长度：1-512 字符

### 5. 批量全部原文定位

如果同一段原文在 PDF 中出现多次，可以使用该接口返回全部匹配位置。
请求格式与 `/locate/batch` 相同，只需要更换 URL。

```bash
curl -X POST http://localhost:12342/locate/batch/all \
  -F "file=@文档.pdf" \
  -F 'queries={"queries":[{"id":"q1","text":"本次招标为道路改造工程"},{"id":"q2","text":"质量保证期"}]}'
```

**返回示例**：

```json
{
  "filename": "文档.pdf",
  "total": 2,
  "found_count": 1,
  "not_found_count": 1,
  "total_match_count": 2,
  "results": [
    {
      "id": "q1",
      "query": "本次招标为道路改造工程",
      "found": true,
      "match_count": 2,
      "matches": [
        {
          "found": true,
          "page": 1,
          "pageWidth": 595,
          "pageHeight": 842,
          "text": "本次招标为道路改造工程",
          "x": 95,
          "y": 72,
          "width": 121,
          "height": 11,
          "match_layer": 1,
          "bboxes": [
            {"x0": 95.0, "y0": 72.7, "x1": 216.0, "y1": 83.7}
          ],
          "message": null
        },
        {
          "found": true,
          "page": 3,
          "pageWidth": 595,
          "pageHeight": 842,
          "text": "本次招标为道路改造工程",
          "x": 95,
          "y": 128,
          "width": 121,
          "height": 11,
          "match_layer": 1,
          "bboxes": [
            {"x0": 95.0, "y0": 128.7, "x1": 216.0, "y1": 139.7}
          ],
          "message": null
        }
      ],
      "message": null
    },
    {
      "id": "q2",
      "query": "质量保证期",
      "found": false,
      "match_count": 0,
      "matches": [],
      "message": "Sentence not found in PDF."
    }
  ]
}
```

### 6. 健康检查

```bash
curl http://localhost:12342/health
# 返回: {"status":"ok","model_loaded":true}
```

## 原文定位原理

错字定位由 `pdf_locator.py` 实现，采用三层匹配策略：

1. **精确匹配**（layer 1）：直接匹配原文字符序列
2. **归一化匹配**（layer 2）：去除空白、统一全半角后匹配
3. **模糊匹配**（layer 3）：使用 difflib 应对细微文本差异

定位过程：
- 使用 `pdfplumber` 解析 PDF 每个字符的坐标
- 按错字所在整句进行查找（自动去重，同一句只查一次）
- 返回匹配文本的页码、坐标、bounding box（每行一个 bbox）

## Python 调用示例

```python
from main import create_corrector, correct_sentence, correct_batch

# 创建纠错器
corrector = create_corrector()  # 默认使用 macbert

# 单句纠错
result = correct_sentence(corrector, "少先队员因该为老人让坐")
print(result)
# {'source': '少先队员因该为老人让坐', 
#  'target': '少先队员应该为老人让座', 
#  'errors': [('因', '应', 4), ('坐', '座', 10)]}

# 批量纠错
results = correct_batch(corrector, ["今天新情很好", "我也很高心"])

# PDF 检查
from pdf_check import check_pdf
with open("招标文件.pdf", "rb") as f:
    result = check_pdf(corrector, f.read())
print(result)

# 独立原文定位
from pdf_locator import locate_sentence
match = locate_sentence("文档.pdf", "本次招标为道路改造工程")
if match:
    print(f"第 {match.page} 页, 坐标 ({match.x}, {match.y}), 匹配方式 layer {match.match_layer}")
```

## 配置说明

在 `main.py` 中可配置：

```python
MODEL_TYPE = "macbert"  # 可选: "macbert", "rule"
MACBERT_MODEL_PATH = "./models/macbert4csc"
```

- **macbert**（默认）：深度学习模型，准确率高，需预下载模型（391MB）
- **rule**：规则+统计模型，首次运行自动下载语言模型（约 2.9GB）

## 重要提示

### 模型能力边界

MacBERT 在通用中文文本上表现良好，但对于招标文件等专业文档：
- **可能漏检**：专业术语、设备型号、国标编号等容易被跳过
- **可能误纠**：上下文不足时会给出错误建议

**建议**：将检测结果作为辅助工具，结合 `context`、`sentence`、`location` 字段人工复核。

### PDF 限制

- 文件大小上限：20 MB
- 支持格式：标准 PDF（含可提取文本层）
- 扫描件 PDF 需先 OCR 转换

## 项目结构

```
.
├── app.py              # FastAPI 服务入口
├── main.py             # 纠错核心逻辑
├── pdf_check.py        # PDF 文件检查与错误定位
├── pdf_locator.py      # PDF 原文坐标定位（3 层匹配）
├── requirements.txt    # 依赖清单
├── README.md           # 本文档
└── DEPLOYMENT.md       # 部署文档
```

## 技术栈

- **FastAPI**：HTTP API 框架
- **pycorrector**：中文纠错引擎（MacBERT 模型）
- **PyMuPDF (fitz)**：PDF 文本抽取
- **pdfplumber**：PDF 字符级坐标解析

## 许可

MIT License
