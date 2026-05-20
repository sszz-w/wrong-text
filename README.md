# 中文错别字检测工具

使用 pycorrector 实现中文句子的错别字检测和纠正。

## 安装

```bash
# 创建虚拟环境
python3.12 -m venv venv
source venv/bin/activate

# 安装依赖（使用清华镜像源）
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pycorrector "numpy<2" kenlm torch
```

## 使用方法

### 基础用法

```python
from pycorrector import Corrector

m = Corrector()

# 纠正单个句子
result = m.correct('少先队员因该为老人让坐')
print(result)
# 输出: {
#   'source': '少先队员因该为老人让坐',
#   'target': '少先队员应该为老人让座',
#   'errors': [('因该', '应该', 4), ('坐', '座', 10)]
# }

# 仅检测错误（不纠正）
errors = m.detect('少先队员因该为老人让坐')
print(errors)

# 批量纠正
results = m.correct_batch([
    '少先队员因该为老人让坐',
    '你找到你最喜欢的工作，我也很高心。'
])
```

### 运行示例

```bash
source venv/bin/activate
python main.py
```

## 功能特点

- **错别字检测**: 识别句子中的错别字位置
- **自动纠正**: 提供正确的词语建议
- **批量处理**: 支持批量处理多个句子
- **基于统计语言模型**: 使用 Kenlm 模型，首次运行会自动下载

## 注意事项

- 首次运行会下载约 2.9GB 的语言模型，需要等待几分钟
- 建议使用 Python 3.12 或更低版本（Python 3.14 可能有 SSL 兼容性问题）
- 需要安装 numpy<2 以保证与 torch 2.2.2 的兼容性

## 高级用法

如果需要更高的准确率，可以使用深度学习模型：

```python
from pycorrector import MacBertCorrector

# 使用 MacBERT 模型（需要 GPU 支持以获得更好性能）
m = MacBertCorrector("shibing624/macbert4csc-base-chinese")
result = m.correct('今天新情很好')
print(result)
# 输出: {'source': '今天新情很好', 'target': '今天心情很好', 'errors': [('新', '心', 2)]}
```
