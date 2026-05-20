# 中文错别字检测工具

使用 pycorrector 实现中文句子的错别字检测和纠正，支持多种纠错模型。

## 支持的模型

| 模型 | 配置值 | 说明 |
|------|--------|------|
| MacBertCorrector | `macbert`（默认） | 深度学习模型，准确率高 |
| Corrector | `rule` | 规则+统计模型，无需下载大模型 |

## 安装

```bash
# 创建虚拟环境
python3.12 -m venv venv
source venv/bin/activate

# 安装依赖（使用清华镜像源）
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

### MacBERT 模型准备

默认使用 MacBERT 模型，需要提前下载模型文件到 `models/macbert4csc` 目录：

```bash
# 从 HuggingFace 下载
huggingface-cli download shibing624/macbert4csc-base-chinese --local-dir models/macbert4csc
```

## 配置

在 `main.py` 顶部修改配置项：

```python
MODEL_TYPE = "macbert"  # 可选值: "macbert", "rule"
MACBERT_MODEL_PATH = "./models/macbert4csc"
```

## 使用方法

### 运行示例

```bash
source venv/bin/activate
python main.py
```

### 代码中调用

```python
from main import create_corrector, correct_sentence, correct_batch

# 创建纠错器（默认使用 macbert）
m = create_corrector()

# 纠正单个句子
result = correct_sentence(m, "少先队员因该为老人让坐")
print(result)
# {'source': '少先队员因该为老人让坐', 'target': '少先队员应该为老人让座', 'errors': [...]}

# 批量纠正
results = correct_batch(m, ["今天新情很好", "我也很高心"])

# 使用规则模型
m_rule = create_corrector("rule")
result = correct_sentence(m_rule, "今天新情很好")
```

## API 服务

项目提供 FastAPI HTTP 接口，供其他项目远程调用。

### 启动服务

```bash
source venv/bin/activate
uvicorn app:app --host 0.0.0.0 --port 8000
```

启动后访问 http://localhost:8000/docs 查看 Swagger 文档。

### 接口说明

| 接口 | 方法 | 说明 |
|------|------|------|
| `/correct` | POST | 单句纠错 |
| `/correct/batch` | POST | 批量纠错（最多 32 条） |
| `/health` | GET | 健康检查 |

### 调用示例

```python
import requests

# 单句纠错
resp = requests.post("http://localhost:8000/correct", json={"text": "少先队员因该为老人让坐"})
print(resp.json())
# {"source": "少先队员因该为老人让坐", "target": "少先队员应该为老人让座", "errors": [...], "has_error": true}

# 批量纠错
resp = requests.post("http://localhost:8000/correct/batch", json={"texts": ["今天新情很好", "我也很高心"]})
print(resp.json())
```

### curl 示例

```bash
curl -X POST http://localhost:8000/correct \
  -H "Content-Type: application/json" \
  -d '{"text": "少先队员因该为老人让坐"}'
```

## 注意事项

- MacBERT 模型需提前下载到 `models/macbert4csc` 目录
- 规则模型首次运行会下载约 2.9GB 的语言模型
- 建议使用 Python 3.12 或更低版本
- 需要安装 numpy<2 以保证兼容性
