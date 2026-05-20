"""
批量处理示例：演示如何批量纠正多个句子
"""

from pycorrector import Corrector


def main():
    # 初始化纠错器
    print("正在初始化纠错器...\n")
    m = Corrector()

    # 测试句子列表
    test_sentences = [
        "少先队员因该为老人让坐",
        "你找到你最喜欢的工作，我也很高心。",
        "今天新情很好",
        "机器学习是人工智能的一个重要分枝",
        "这个问题很复杂，需要仔细分晰",
    ]

    print("=" * 60)
    print("批量纠错示例")
    print("=" * 60)

    # 批量纠正
    results = m.correct_batch(test_sentences)

    for i, result in enumerate(results, 1):
        print(f"\n{i}. 原句: {result['source']}")
        print(f"   纠正: {result['target']}")

        if result['errors']:
            print(f"   错误:")
            for wrong, right, pos in result['errors']:
                print(f"      位置 {pos}: '{wrong}' → '{right}'")
        else:
            print(f"   ✓ 未检测到错误")

    print("\n" + "=" * 60)
    print(f"共处理 {len(results)} 个句子")
    total_errors = sum(len(r['errors']) for r in results)
    print(f"共发现 {total_errors} 处错误")
    print("=" * 60)


if __name__ == "__main__":
    main()
