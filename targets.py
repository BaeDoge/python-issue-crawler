"""
발행 대상(Target) 설정 — 어느 레포에, 무엇을, 얼마나 올릴지
========================================================================
포트폴리오 레포와 공개 기술 블로그 레포처럼 여러 곳에 나눠 올리기 위한 설정입니다.
`targets.toml`(예: targets.example.toml)에 [targets.이름] 블록을 추가하면 됩니다.
파일이 없으면 .env의 PORTFOLIO_REPO_PATH / POSTS_SUBDIR / POSTS_EN_SUBDIR / AUTO_PUSH /
GIT_BRANCH / HOLD_THIRD_PARTY로 단일 대상("portfolio")을 만듭니다(예전 방식 그대로).
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import config


@dataclass
class Target:
    name: str
    repo_path: Path
    posts_dir: str = "src/app/[locale]/blog/posts"
    en_posts_dir: str = ""            # 비어 있으면 이 대상엔 영문을 발행하지 않음
    branch: str = "main"
    auto_publish: bool = True         # false면 자동 발행 안 함(수동: --publish-draft --target 이름)
    auto_push: bool = True            # false면 로컬 커밋까지만
    mode: str = "immediate"           # immediate: 글마다 push / batch: 커밋만 쌓고 주기적으로 한꺼번에 push
    push_interval_minutes: int = 360  # batch 모드에서 push 간격
    hold_third_party: bool = True     # 다른 사람 이미지/블로그 글을 참고한 노트는 자동 발행 안 함
    daily_limit: int = 0              # 하루 최대 발행 수(0 = 무제한). 넘치면 대기열에 쌓였다가 다음 날 나감
    topics: list = field(default_factory=list)   # 이 대상에 올릴 주제(비우면 전부)

    @property
    def wants_english(self) -> bool:
        return bool(self.en_posts_dir)

    def accepts(self, topic_key: str) -> bool:
        return not self.topics or topic_key in self.topics


def load_targets() -> list:
    path = config.TARGETS_FILE
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8")).get("targets", {})
        targets = []
        for name, cfg in data.items():
            cfg = dict(cfg)
            repo = cfg.pop("repo_path", "")
            if not repo:
                raise ValueError(f"targets.toml의 [targets.{name}]에 repo_path가 없습니다.")
            targets.append(Target(name=name, repo_path=Path(repo), **cfg))
        return targets

    if config.PORTFOLIO_REPO_PATH is None:
        return []
    return [Target(
        name="portfolio", repo_path=config.PORTFOLIO_REPO_PATH, posts_dir=config.POSTS_SUBDIR,
        en_posts_dir=config.POSTS_EN_SUBDIR, branch=config.GIT_BRANCH,
        auto_push=config.AUTO_PUSH, hold_third_party=config.HOLD_THIRD_PARTY,
    )]


def get_target(name: str):
    return next((t for t in load_targets() if t.name == name), None)


def needs_english() -> bool:
    return any(t.wants_english for t in load_targets())
