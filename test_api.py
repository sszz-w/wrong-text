"""
API 接口测试示例
演示如何调用错别字检测 API
"""

import requests

BASE_URL = "http://localhost:8000"


def test_single_correction():
    """测试单句纠错"""
    print("=== 测试单句纠错 ===")
    response = requests.post(
        f"{BASE_URL}/correct",
        json={"text": "少先队员因该为老人让坐"}
    )
    result = response.json()
    print(f"原句: {result['source']}")
    print(f"纠正: {result['target']}")
    print(f"有错误: {result['has_error']}")
    if result['errors']:
        for error in result['errors']:
            print(f"  位置 {error['position']}: '{error['wrong']}' → '{error['correct']}'")
    print()


def test_batch_correction():
    """测试批量纠错"""
    print("=== 测试批量纠错 ===")
    response = requests.post(
        f"{BASE_URL}/correct/batch",
        json={
            "texts": [
                "今天新情很好",
                "你找到你最喜欢的工作，我也很高心。",
                "机器学习是人工智能的一个重要分枝"
            ]
        }
    )
    result = response.json()
    print(f"总数: {result['total']}, 有错误: {result['error_count']}")
    for item in result['results']:
        if item['has_error']:
            print(f"  {item['source']} → {item['target']}")
    print()


def test_health():
    """测试健康检查"""
    print("=== 测试健康检查 ===")
    response = requests.get(f"{BASE_URL}/health")
    print(response.json())
    print()


if __name__ == "__main__":
    test_health()
    test_single_correction()
    test_batch_correction()
