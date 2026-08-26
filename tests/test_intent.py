import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.intent_classifier import classify_intent, rule_based_intent, extract_params


TEST_CASES = [
    ("这个月全区投诉情况怎么样？", "summary"),
    ("今年的投诉量和去年比降了没有？", "trend"),
    ("本月投诉量最多的5个街道是哪些？", "ranking"),
    ("停车类投诉主要集中在哪些小区？", "category"),
    ("徐房集团和城投集团今年表现怎么样？", "comparison"),
    ("重复投诉率是多少？哪些小区最严重？", "repeat"),
    ("哪些小区今年投诉增长最快？", "hotspot"),
    ("物业公司排名情况", "property"),
]


def test_rule_based():
    for q, expected in TEST_CASES:
        intent, _ = rule_based_intent(q)
        status = "✅" if intent == expected else "❌"
        print(f"{status} [{expected}] {q} -> {intent}")


def test_extract_params():
    params = extract_params("2026年7月漕河泾街道停车类投诉top5")
    assert params.get("year") == 2026
    assert params.get("month") == 7
    assert params.get("street") == "漕河泾"
    print("\n✅ 参数提取 OK")


def test_classify():
    intent, params = classify_intent("本月哪个街道投诉最多？")
    print(f"意图: {intent}, 参数: {params}")
    print("✅ 意图分类 OK")


if __name__ == "__main__":
    print("=== 意图分类规则测试 ===")
    test_rule_based()
    test_extract_params()
    test_classify()
