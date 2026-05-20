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

## 注意事项

- MacBERT 模型需提前下载到 `models/macbert4csc` 目录
- 规则模型首次运行会下载约 2.9GB 的语言模型
- 建议使用 Python 3.12 或更低版本
- 需要安装 numpy<2 以保证兼容性
