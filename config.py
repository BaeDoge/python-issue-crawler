"""
공통 설정 — .env 로딩 + OmniRoute LLM 라우팅 + 배포 대상 설정
================================================================
.env에 최소 이것만 있으면 동작합니다:
  OMNIROUTE_BASE_URL   (기본값 http://127.0.0.1:20128/v1)
  OMNIROUTE_API_KEY
  PORTFOLIO_REPO_PATH  (로컬에 clone해둔 포트폴리오 레포 경로)
"""

import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

PROJECT_ROOT = Path(__file__).parent

# 회사 보안 프로그램이 HTTPS를 가로채는 환경에서는 파이썬이 OS(Windows) 인증서 저장소를
# 못 봐서 SSL 오류가 납니다. truststore가 설치돼 있으면 OS 저장소를 쓰게 합니다
# (설치 안 돼 있으면 아무 일도 안 함: `uv add truststore`). 끄려면 USE_SYSTEM_CERTS=false.
SYSTEM_CERTS_ACTIVE = False
if os.getenv("USE_SYSTEM_CERTS", "true").strip().lower() in ("1", "true", "yes"):
    try:
        import truststore
        truststore.inject_into_ssl()
        SYSTEM_CERTS_ACTIVE = True
    except Exception:
        pass
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(PROJECT_ROOT / ".tiktoken_cache"))

from crewai import LLM
from crewai.utilities.exceptions.context_window_exceeding_exception import (
    CONTEXT_LIMIT_ERRORS,
)
_LLAMA_SERVER_CONTEXT_ERROR_PHRASE = "exceeds the available context size"
if _LLAMA_SERVER_CONTEXT_ERROR_PHRASE not in CONTEXT_LIMIT_ERRORS:
    CONTEXT_LIMIT_ERRORS.append(_LLAMA_SERVER_CONTEXT_ERROR_PHRASE)

# -----------------------------------------------------------------------
# OmniRoute
# -----------------------------------------------------------------------
OMNIROUTE_BASE_URL = os.getenv("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1").strip()
OMNIROUTE_API_KEY = os.getenv("OMNIROUTE_API_KEY", "").strip()

if not OMNIROUTE_API_KEY:
    raise ValueError("OMNIROUTE_API_KEY가 비어있어요. .env에 OmniRoute용 토큰을 넣어주세요.")


def _role_model(env_name: str, default: str) -> str:
    return (os.getenv(env_name, "") or default).strip() or default


def _omni_llm(model_alias: str, **overrides) -> LLM:
    return LLM(
        model=f"openai/{model_alias}",
        base_url=OMNIROUTE_BASE_URL,
        api_key=OMNIROUTE_API_KEY,
        **overrides,
    )


SCOUT_MODEL = _role_model("OMNIROUTE_MODEL_SCOUT", "auto")
WRITER_MODEL = _role_model("OMNIROUTE_MODEL_WRITER", "auto/quality")
VERIFIER_MODEL = _role_model("OMNIROUTE_MODEL_VERIFIER", "auto/quality")

llm_scout = _omni_llm(SCOUT_MODEL, temperature=0.4, max_tokens=1536)
# 추론 모델은 <think> 토큰도 max_tokens에 포함돼서, 값이 작으면 글이 중간에 끊깁니다.
WRITER_MAX_TOKENS = int(os.getenv("OMNIROUTE_WRITER_MAX_TOKENS", "6000"))
llm_writer = _omni_llm(WRITER_MODEL, temperature=0.4, max_tokens=WRITER_MAX_TOKENS)
llm_translator = _omni_llm(WRITER_MODEL, temperature=0.2, max_tokens=WRITER_MAX_TOKENS)
llm_verifier = _omni_llm(VERIFIER_MODEL, temperature=0.1, max_tokens=2048)

# -----------------------------------------------------------------------
# 출력 / 로그
# -----------------------------------------------------------------------
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR") or str(PROJECT_ROOT / "output_files"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------
# 배포 대상 — 포트폴리오 레포 (Vercel에 연결된 GitHub 레포의 로컬 clone)
# -----------------------------------------------------------------------
_portfolio_path = os.getenv("PORTFOLIO_REPO_PATH", "").strip()
PORTFOLIO_REPO_PATH = Path(_portfolio_path) if _portfolio_path else None

# 레포 안에서 mdx 포스트가 저장되는 상대 경로 (Next.js 프로젝트 구조 기준)
POSTS_SUBDIR = os.getenv("POSTS_SUBDIR", "src/app/[locale]/blog/posts")

# 영문 mdx를 넣을 레포 내 경로 (비어 있으면 영문은 만들지도, 발행하지도 않음 — 번역에 GPU 시간이 들기 때문)
# 예: src/app/[locale]/blog/posts/en
POSTS_EN_SUBDIR = os.getenv("POSTS_EN_SUBDIR", "").strip()

# 여러 레포에 나눠 발행하려면 targets.toml을 만드세요 (targets.example.toml 참고).
# 없으면 위의 PORTFOLIO_REPO_PATH 등 환경변수로 단일 대상("portfolio")을 만듭니다.
TARGETS_FILE = Path(os.getenv("TARGETS_FILE") or str(PROJECT_ROOT / "targets.toml"))

# 연속 생성 모드(scheduler.py --continuous)
QUEUE_MAX_READY = int(os.getenv("QUEUE_MAX_READY", "100"))             # 발행 대기 글이 이만큼 쌓이면 생성 일시 중지
CONTINUOUS_COOLDOWN_SEC = int(os.getenv("CONTINUOUS_COOLDOWN_SEC", "5"))  # 글 사이 쉬는 시간

# true면 commit 후 즉시 push까지 수행 (Vercel이 자동 배포). false면 커밋만 하고 push는 안 함
AUTO_PUSH = os.getenv("AUTO_PUSH", "true").strip().lower() in ("1", "true", "yes")

# true면 다른 사람의 이미지/블로그 글을 참고한 노트는 자동 발행하지 않고 초안으로만 남김
# (원저작자 허가를 받은 뒤 engine.py --publish-draft로 발행). 허가 절차가 정리되면 false로.
HOLD_THIRD_PARTY = os.getenv("HOLD_THIRD_PARTY", "true").strip().lower() in ("1", "true", "yes")

# push 대상 브랜치. main으로 바로 올리거나, 검수용 브랜치를 쓰고 싶으면 바꿀 것
GIT_BRANCH = os.getenv("GIT_BRANCH", "main").strip()

if __name__ == "__main__":
    print(f"OmniRoute base_url = {OMNIROUTE_BASE_URL}")
    print(f"writer   -> {llm_writer.model}")
    print(f"verifier -> {llm_verifier.model}")
    print(f"output   -> {OUTPUT_DIR}")
    print(f"portfolio repo -> {PORTFOLIO_REPO_PATH} (posts in {POSTS_SUBDIR})")
    print(f"auto push -> {AUTO_PUSH} (branch: {GIT_BRANCH})")
