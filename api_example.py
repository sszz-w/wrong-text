"""
API 示例：将纠错功能封装为可复用的模块
"""

from typing import List, Dict, Tuple
from pycorrector import Corrector


class ChineseCorrector:
    """中文错别字纠错器"""

    def __init__(self):
        """初始化纠错器"""
        self.corrector = Corrector()

    def detect(self, text: str) -> List[Tuple]:
        """
        检测文本中的错误

        Args:
            text: 待检测的文本

        Returns:
            错误列表，每个错误包含 (错误词, 开始位置, 结束位置, 错误类型)
        """
        return self.corrector.detect(text)

    def correct(self, text: str) -> Dict:
        """
        纠正文本中的错误

        Args:
            text: 待纠正的文本

        Returns:
            包含原文、纠正后文本和错误详情的字典
        """
        return self.corrector.correct(text)

    def correct_batch(self, texts: List[str]) -> List[Dict]:
        """
        批量纠正多个文本

        Args:
            texts: 待纠正的文本列表

        Returns:
            纠正结果列表
        """
        return self.corrector.correct_batch(texts)

    def has_errors(self, text: str) -> bool:
        """
        判断文本是否包含错误

        Args:
            text: 待检测的文本

        Returns:
            True 如果包含错误，否则 False
        """
        errors = self.detect(text)
        return len(errors) > 0

    def get_error_count(self, text: str) -> int:
        """
        获取文本中的错误数量

        Args:
            text: 待检测的文本

        Returns:
            错误数量
        """
        result = self.correct(text)
        return len(result.get('errors', []))


def main():
    """使用示例"""
    corrector = ChineseCorrector()

    # 示例 1: 检测错误
    text1 = "少先队员因该为老人让坐"
    print(f"文本: {text1}")
    print(f"是否有错误: {corrector.has_errors(text1)}")
    print(f"错误数量: {corrector.get_error_count(text1)}")

    # 示例 2: 纠正错误
    result = corrector.correct(text1)
    print(f"\n原文: {result['source']}")
    print(f"纠正: {result['target']}")

    # 示例 3: 批量处理
    texts = [
        "今天新情很好",
        "机器学习是人工智能的一个重要分枝",
    ]
    results = corrector.correct_batch(texts)
    print("\n批量处理结果:")
    for r in results:
        print(f"  {r['source']} → {r['target']}")


if __name__ == "__main__":
    main()
