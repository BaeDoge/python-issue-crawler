"""
공통 설정 — .env 로딩 + OmniRoute LLM 라우팅 + 배포 대상 설정
================================================================
.env에 최소 이것만 있으면 동작합니다:
  OMNIROUTE_BASE_URL   (기본값 http://127.0.0.1:20128/v1)
  OMNIROUTE_API_KEY
  PUBLISH_TARGETS      (발행 대상 저장소 목록을 담은 JSON 환경변수)
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
# 검수 사이클 횟수. 각 사이클은 TopicSpec.max_rounds(기본 5라운드)까지 재작성합니다.
QUALITY_ATTEMPTS = max(1, int(os.getenv("QUALITY_ATTEMPTS", "3")))
llm_writer = _omni_llm(WRITER_MODEL, temperature=0.4, max_tokens=WRITER_MAX_TOKENS)
# English translation uses the writer model with a lower temperature; it is only called when an English target is configured.
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
# 발행 대상 — PUBLISH_TARGETS JSON 배열로 대상 저장소를 확장 가능하게 설정
# -----------------------------------------------------------------------
import json

def _load_publish_targets() -> list[dict]:
    raw = os.getenv("PUBLISH_TARGETS", "").strip()
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "PUBLISH_TARGETS는 JSON 배열이어야 합니다. .env.example의 형식을 확인해주세요."
        ) from exc
    if not isinstance(items, list):
        raise ValueError("PUBLISH_TARGETS 최상위 값은 JSON 배열이어야 합니다.")

    targets = []
    names = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"PUBLISH_TARGETS[{index}]는 객체여야 합니다.")
        name = str(item.get("name", f"target-{index + 1}")).strip()
        repo_raw = str(item.get("repo_path", "")).strip()
        posts_dir = str(item.get("posts_dir", "")).strip()
        if not repo_raw or not posts_dir:
            raise ValueError(
                f"PUBLISH_TARGETS[{index}]에는 repo_path와 posts_dir가 필요합니다."
            )
        if name in names:
            raise ValueError(f"PUBLISH_TARGETS에 중복된 name이 있습니다: {name}")
        names.add(name)

        en_posts_raw = str(item.get("en_posts_dir", "")).strip()
        relative_paths = {
            "posts_dir": posts_dir,
            "images_dir": str(item.get("images_dir", "public/blogs")).strip(),
        }
        if en_posts_raw:
            relative_paths["en_posts_dir"] = en_posts_raw
        for key, value in relative_paths.items():
            path = Path(value)
            if not value or path.is_absolute() or ".." in path.parts:
                raise ValueError(
                    f"PUBLISH_TARGETS[{index}].{key}는 저장소 내부의 상대 경로여야 합니다."
                )

        image_url_prefix = str(item.get("image_url_prefix", "/blogs")).strip()
        if image_url_prefix and not image_url_prefix.startswith("/"):
            raise ValueError(
                f"PUBLISH_TARGETS[{index}].image_url_prefix는 /로 시작해야 합니다."
            )
        targets.append({
            "name": name,
            "repo_path": Path(repo_raw).expanduser(),
            "posts_dir": Path(relative_paths["posts_dir"]),
            "en_posts_dir": Path(relative_paths["en_posts_dir"]) if en_posts_raw else None,
            "category_subdirs": bool(item.get("category_subdirs", False)),
            "images_dir": Path(relative_paths["images_dir"]),
            "image_url_prefix": image_url_prefix.rstrip("/"),
            "branch": str(item.get("branch", os.getenv("GIT_BRANCH", "main"))).strip() or "main",
        })
    return targets


PUBLISH_TARGETS = _load_publish_targets()

# true면 각 대상 레포에 commit 후 push. Vercel이 GitHub push를 감지해 배포합니다.
AUTO_PUSH = os.getenv("AUTO_PUSH", "true").strip().lower() in ("1", "true", "yes")

# 다른 사람의 자료/이미지에 의존한 노트는 허가 전 자동 발행하지 않음
HOLD_THIRD_PARTY = os.getenv("HOLD_THIRD_PARTY", "true").strip().lower() in ("1", "true", "yes")

if __name__ == "__main__":
    print(f"OmniRoute base_url = {OMNIROUTE_BASE_URL}")
    print(f"writer   -> {llm_writer.model}")
    print(f"verifier -> {llm_verifier.model}")
    print(f"output   -> {OUTPUT_DIR}")
    print(f"publish targets -> {[target['name'] for target in PUBLISH_TARGETS]}")
    print(f"auto push -> {AUTO_PUSH}")
