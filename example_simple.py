"""
简单示例：展示 pycorrector 的基本用法
"""

from pycorrector import Corrector


def main():
    # 初始化纠错器（首次运行会下载语言模型）
    print("正在初始化纠错器...")
    m = Corrector()
    print("初始化完成！\n")

    # 测试句子
    test_sentence = "少先队员因该为老人让坐"

    print(f"原句: {test_sentence}")
    print("-" * 50)

    # 1. 检测错误
    print("\n1. 检测错误:")
    errors = m.detect(test_sentence)
    if errors:
        for error in errors:
            print(f"   发现错误: {error}")
    else:
        print("   未检测到错误")

    # 2. 纠正句子
    print("\n2. 纠正句子:")
    result = m.correct(test_sentence)
    print(f"   原句: {result['source']}")
    print(f"   纠正: {result['target']}")
    if result['errors']:
        print(f"   错误详情:")
        for wrong, right, pos in result['errors']:
            print(f"      位置 {pos}: '{wrong}' → '{right}'")


if __name__ == "__main__":
    main()
