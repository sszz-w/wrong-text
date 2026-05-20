"""
中文错别字检测与纠正工具
支持多种纠错模型：MacBertCorrector（深度学习）和 Corrector（规则+统计）
通过 MODEL_TYPE 配置项切换模型
"""

import re
import time

MODEL_TYPE = "macbert"  # 可选值: "macbert", "rule"
MACBERT_MODEL_PATH = "./models/macbert4csc"


def is_chinese_char(char: str) -> bool:
    return bool(re.match(r"[一-鿿]", char))


def filter_errors(errors: list) -> list:
    filtered = []
    for wrong, right, pos in errors:
        if is_chinese_char(wrong) and is_chinese_char(right):
            filtered.append((wrong, right, pos))
    return filtered


def create_corrector(model_type: str = MODEL_TYPE):
    """根据配置创建纠错器实例"""
    if model_type == "macbert":
        from pycorrector import MacBertCorrector
        return MacBertCorrector(MACBERT_MODEL_PATH)
    else:
        from pycorrector import Corrector
        return Corrector()


def correct_sentence(m, sentence: str) -> dict:
    """纠正句子中的错别字"""
    result = m.correct(sentence)
    result["errors"] = filter_errors(result["errors"])
    return result


def correct_batch(m, sentences: list[str]) -> list[dict]:
    """批量纠正多个句子"""
    results = m.correct_batch(sentences)
    for result in results:
        result["errors"] = filter_errors(result["errors"])
    return results


if __name__ == "__main__":
    print(f"当前模型: {MODEL_TYPE}")
    print("正在加载模型...")
    start_load = time.time()
    m = create_corrector()
    load_time = time.time() - start_load
    print(f"模型加载耗时: {load_time:.2f} 秒")

    test_sentences = [
        "少先队员因该为老人让坐",
        "你找到你最喜欢的工作，我也很高心。",
        "今天新情很好",
        "我们应该拥护核平",
        "他的话让我很感动，我决定重新做人",
    ]

    print("\n" + "=" * 60)
    print("中文错别字检测与纠正")
    print("=" * 60)

    start_correct = time.time()
    for sent in test_sentences:
        result = correct_sentence(m, sent)
        print(f"\n原句: {result['source']}")
        print(f"纠正: {result['target']}")
        if result["errors"]:
            for wrong, right, pos in result["errors"]:
                print(f"  - 位置 {pos}: '{wrong}' → '{right}'")
        else:
            print("  - 未检测到错误")
    correct_time = time.time() - start_correct
    print(f"\n纠错总耗时: {correct_time:.2f} 秒")

    print("\n" + "=" * 60)
    print("测试招标文件段落")
    print("=" * 60)

    try:
        with open("test_paragraph.txt", "r") as f:
            text = f.read()

        print(f"文本长度: {len(text)} 字符")
        start = time.time()
        sentences = [s.strip() for s in text.replace("\n", "。").split("。") if s.strip()]
        results = correct_batch(m, sentences)
        elapsed = time.time() - start
        print(f"纠错耗时: {elapsed:.2f} 秒\n")

        error_count = 0
        for result in results:
            if result["errors"]:
                for wrong, right, pos in result["errors"]:
                    error_count += 1
                    print(f"  [{error_count}] \"{wrong}\" → \"{right}\" (位置 {pos})")
                    print(f"      原句片段: ...{result['source']}...")
        if error_count == 0:
            print("  未检测到错误")
        else:
            print(f"\n共检测到 {error_count} 个错误")
    except FileNotFoundError:
        print("未找到 test_paragraph.txt 文件，跳过段落测试")
