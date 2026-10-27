"""
소스 레지스트리 — 트러블슈팅 / 알고리즘 두 주제의 소재 설정
========================================================
여기 값만 바꾸면 후보 풀이 바로 반영됩니다.
"""

# ---------------------------------------------------------------------
# 트러블슈팅 — 파이썬/라이브러리에서 흔하게 만나는 에러
# ---------------------------------------------------------------------
# 이 목록에서 무작위로 몇 개를 골라 StackOverflow에서 "채택 답변이 있고 추천 수가 높은"
# 질문을 찾습니다. 흔하고 답이 분명한 에러만 다루려고 직접 큐레이션한 시드입니다.
# 에러 메시지(영어)나 "라이브러리명 + 증상"을 자유롭게 추가/삭제하세요.
TROUBLESHOOTING_SEEDS = [
    "ModuleNotFoundError: No module named",
    "ImportError: cannot import name",
    "ImportError: attempted relative import with no known parent package",
    "IndentationError: unexpected indent",
    "SyntaxError: invalid syntax",
    "TypeError: 'NoneType' object is not subscriptable",
    "TypeError: unhashable type",
    "TypeError: can only concatenate str (not \"int\") to str",
    "TypeError: missing 1 required positional argument",
    "TypeError: object is not callable",
    "IndexError: list index out of range",
    "KeyError",
    "AttributeError: 'NoneType' object has no attribute",
    "UnboundLocalError: local variable referenced before assignment",
    "NameError: name is not defined",
    "ValueError: invalid literal for int() with base 10",
    "ValueError: too many values to unpack",
    "ValueError: The truth value of an array with more than one element is ambiguous",
    "FileNotFoundError: [Errno 2] No such file or directory",
    "PermissionError: [Errno 13] Permission denied",
    "UnicodeDecodeError: 'utf-8' codec can't decode byte",
    "UnicodeDecodeError: 'cp949' codec can't decode byte",
    "UnicodeEncodeError: 'cp949' codec can't encode character",
    "RecursionError: maximum recursion depth exceeded",
    "RuntimeError: dictionary changed size during iteration",
    "json.decoder.JSONDecodeError: Expecting value",
    "pip externally-managed-environment",
    "pip is not recognized as an internal or external command",
    "SSL: CERTIFICATE_VERIFY_FAILED",
    "requests.exceptions.ConnectionError",
    "pandas SettingWithCopyWarning",
    "pandas KeyError column not in index",
    "numpy shapes not aligned",
    "matplotlib Korean font glyph missing",
    "venv activate disabled running scripts is disabled on this system",
]

# StackOverflow 필터 — 추천 수 하한(흔하고 검증된 Q&A만), 파이썬2 글 제외
TROUBLESHOOTING_MIN_SCORE = 20
TROUBLESHOOTING_EXCLUDED_TAGS = "python-2.7;python-2.x;python-2.6"
# 시드 몇 개를 뽑아 후보를 만들지 / 시드당 몇 건을 가져올지
TROUBLESHOOTING_SEEDS_PER_RUN = 3
TROUBLESHOOTING_PER_SEED = 4

# GitHub 이슈도 후보에 섞고 싶으면 True (기본 False — 이슈는 해결책이 코멘트에 흩어져 있고
# "접근 권한 대기" 같은 해결 불가 이슈가 섞여 들어와서 품질이 떨어졌음)
TROUBLESHOOTING_USE_GITHUB = False
TROUBLESHOOTING_GITHUB_QUERY = "error+in:title+type:issue+is:closed+comments:5..150+reactions:>5"
TROUBLESHOOTING_MAX_AGE_YEARS = 3   # GitHub 후보에만 적용

# ---------------------------------------------------------------------
# 한국어 블로그(티스토리/velog) 참고 — 선택한 에러에 대한 한국어 설명·스크린샷을 보조로 가져옴
# ---------------------------------------------------------------------
BLOG_DOMAINS = ["tistory.com", "velog.io"]
BLOG_MAX_ARTICLES = 2

# ---------------------------------------------------------------------
# 알고리즘 — LeetCode. 난이도는 "EASY","MEDIUM","HARD" 중 골라서 리스트로.
# ---------------------------------------------------------------------
ALGORITHM_DIFFICULTY = ["EASY", "MEDIUM"]

# LeetCode GraphQL 호출이 실패했을 때(차단, 네트워크 문제 등) 쓸 폴백 풀.
# titleSlug(URL의 마지막 부분, 예: leetcode.com/problems/two-sum/ -> "two-sum")를
# 자유롭게 추가/삭제하면 됩니다.
ALGORITHM_FALLBACK_SLUGS = [
    "two-sum", "valid-parentheses", "merge-two-sorted-lists",
    "best-time-to-buy-and-sell-stock", "maximum-subarray",
    "climbing-stairs", "symmetric-tree", "maximum-depth-of-binary-tree",
    "single-number", "majority-element", "reverse-linked-list",
    "contains-duplicate", "invert-binary-tree", "valid-anagram",
    "binary-search", "flood-fill", "linked-list-cycle",
    "middle-of-the-linked-list", "move-zeroes", "two-city-scheduling",
    "group-anagrams", "product-of-array-except-self",
    "longest-substring-without-repeating-characters",
    "3sum", "container-with-most-water", "search-in-rotated-sorted-array",
]
