"""
中文错别字检测与纠正工具
使用 pycorrector 实现中文句子的错别字检测和纠正
"""

from pycorrector import Corrector


def detect_errors(sentence: str) -> list:
    """检测句子中的错别字，返回错误位置信息"""
    m = Corrector()
    return m.detect(sentence)


def correct_sentence(sentence: str) -> dict:
    """纠正句子中的错别字，返回纠正结果"""
    m = Corrector()
    return m.correct(sentence)


def correct_batch(sentences: list[str]) -> list[dict]:
    """批量纠正多个句子"""
    m = Corrector()
    return m.correct_batch(sentences)


if __name__ == "__main__":
    test_sentences = [
        "少先队员因该为老人让坐",
        "你找到你最喜欢的工作，我也很高心。",
        "今天新情很好",
        "我们应该拥护核平",
        "他的话让我很感动，我决定重新做人",
    ]

    m = Corrector()

    print("=" * 60)
    print("中文错别字检测与纠正")
    print("=" * 60)

    for sent in test_sentences:
        result = m.correct(sent)
        print(f"\n原句: {result['source']}")
        print(f"纠正: {result['target']}")
        if result["errors"]:
            for wrong, right, pos in result["errors"]:
                print(f"  - 位置 {pos}: '{wrong}' → '{right}'")
        else:
            print("  - 未检测到错误")

    print("\n" + "=" * 60)
    print("仅检测错误（不纠正）")
    print("=" * 60)

    errors = m.detect("少先队员因该为老人让坐")
    print(f"\n检测结果: {errors}")
