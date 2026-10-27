"""
주제 레지스트리
========================================================
현재는 트러블슈팅/알고리즘 두 개에 집중합니다. 나중에 다시 늘리고 싶으면
topics/새주제.py를 만들고 여기 한 줄만 추가하면 됩니다.
"""

from topics import troubleshooting, algorithm, opensource

TOPICS = {
    troubleshooting.KEY: troubleshooting,
    algorithm.KEY: algorithm,
    opensource.KEY: opensource,
}


def topic_choices() -> list:
    return [(key, mod.LABEL) for key, mod in TOPICS.items()]
