"""
구조화 노트 렌더러 — 트러블슈팅/알고리즘 공용
========================================================
블로그 narrative가 아니라 "현상/원인/해결방법/..." 같은 고정 섹션으로 구성된
담백한 기술 노트를 mdx로 렌더링합니다. 포트폴리오 Next.js 블로그가 기대하는
frontmatter(title/publishedAt/summary/tag) 형식을 그대로 따릅니다.

- 출처는 본문 중간에 달지 않고 글 맨 아래 "## 출처" 섹션에 한 번에 모읍니다.
- 이미지는 mdx와 같은 폴더의 public/blogs/ 아래에 복사해둡니다(포트폴리오 레포와 같은
  구조). 그래서 mdx와 public/ 폴더를 통째로 레포에 복사해도 이미지가 깨지지 않고,
  발행 단계(publish/git_publish.py)도 이 파일들을 그대로 커밋합니다.
- LLM이 코드블록(```)을 문장 중간에 한 줄로 붙여 쓰는 경우가 많아서(렌더링이 깨짐),
  저장 전에 항상 올바른 형태(앞뒤 빈 줄 + 줄바꿈)로 정규화합니다.
"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

PUBLIC_IMAGE_DIR = "public/blogs"   # 포트폴리오 레포 안에서 이미지가 저장되는 위치
PUBLIC_IMAGE_URL_PREFIX = "/blogs"  # mdx에서 참조하는 URL 경로

_KNOWN_LANGS = {
    "python", "py", "bash", "sh", "shell", "zsh", "powershell", "ps1", "cmd", "bat", "console",
    "text", "txt", "json", "yaml", "yml", "toml", "ini", "sql", "diff", "html", "css", "xml",
    "javascript", "js", "typescript", "ts", "tsx", "jsx", "java", "c", "cpp", "go", "rust", "dockerfile",
}
_FENCE_RE = re.compile(r"```(.*?)```", re.DOTALL)


def normalize_code_fences(text: str) -> str:
    """``` ... ``` 블록을 항상 '빈 줄 + ```언어\\n코드\\n``` + 빈 줄' 형태로 다시 쓴다."""
    def repl(m: re.Match) -> str:
        inner = m.group(1)
        lang = ""
        lm = re.match(r"^([A-Za-z0-9_+#-]+)(?=[ \t]|\r?\n)", inner)
        if lm and lm.group(1).lower() in _KNOWN_LANGS:
            lang = lm.group(1)
            inner = inner[lm.end():]
        code = inner.strip("\r\n")
        if "\n" not in code:
            code = code.strip()
        return f"\n\n```{lang}\n{code}\n```\n\n"

    out = _FENCE_RE.sub(repl, text)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def _yaml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _slugify(title: str, content_type: str) -> str:
    plain = re.sub(r"^\[[^\]]+\]\s*", "", title)
    ascii_part = re.sub(r"[^a-zA-Z0-9]+", "-", plain).strip("-").lower()
    if len(ascii_part) >= 4:
        return ascii_part[:60]
    return f"{content_type}-{datetime.now():%Y%m%d-%H%M%S}"


_L10N = {
    "ko": {"sources": "출처", "author": "작성자", "images": "본문 이미지는 위 출처에서 가져왔습니다.",
           "shot": "스크린샷"},
    "en": {"sources": "Sources", "author": "Author", "images": "Images are taken from the sources above.",
           "shot": "screenshot"},
}


def _source_line(src: dict, lang: str = "ko") -> str:
    platform = src.get("platform") or ("원문" if lang == "ko" else "Source")
    label = src.get("title") or src["url"]
    line = f"- {platform}: [{label}]({src['url']})"
    author = src.get("author")
    if author:
        if lang == "en":
            author = author.replace("(질문)", "(question)").replace("(답변)", "(answer)")
        line += f" — {_L10N[lang]['author']}: {author}"
    if platform == "StackOverflow":
        line += " (CC BY-SA)"
    return line


def _compose_mdx(*, title, summary, tag, sections, section_images, sources, has_images, lang) -> str:
    frontmatter = (
        "---\n"
        f"title: {_yaml_str(title)}\n"
        f"publishedAt: {_yaml_str(f'{datetime.now():%Y-%m-%d}')}\n"
        f"summary: {_yaml_str(summary)}\n"
        f"tag: {_yaml_str(tag)}\n"
        "---\n\n"
    )
    body_parts = []
    for header, content in sections.items():
        block = f"## {header}\n\n{normalize_code_fences(content)}\n"
        for img in section_images.get(header, []):
            block += f"\n![{img.get('alt', header)}]({img['url']})\n"
        body_parts.append(block)
    if sources:
        src_block = f"## {_L10N[lang]['sources']}\n\n" + "\n".join(_source_line(s, lang) for s in sources) + "\n"
        if has_images:
            src_block += f"\n{_L10N[lang]['images']}\n"
        body_parts.append(src_block)
    return frontmatter + "\n".join(body_parts)


def render_note(
    *, content_type: str, title: str, summary: str, tag: str,
    sections: dict, out_dir: Path, refine_meta: dict | None = None,
    sources: list | None = None, images: list | None = None,
) -> dict:
    """sections: {"현상": "...", ...} — 순서 보존 dict.
    sources: [{"platform","title","url","author"}]  images: [{"section","local_path","source_url","platform","author","alt"}]
    반환: {"path","meta_path","slug","image_files","image_refs","sources"}  (image_files의 local_path는 out_dir/public/blogs 안의 복사본)"""
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = list(sources or [])
    images = images or []

    slug = _slugify(title, content_type)
    out_path = out_dir / f"{slug}.mdx"
    if out_path.exists():
        slug = f"{slug}-{datetime.now():%H%M%S}"
        out_path = out_dir / f"{slug}.mdx"

    # 이미지를 mdx 옆 public/blogs/로 복사하고, 실제로 복사된 것만 본문에 참조한다
    image_files = []
    section_images: dict = {}
    for n, img in enumerate(images, 1):
        src_path = Path(img["local_path"])
        if not src_path.exists() or src_path.stat().st_size == 0:
            continue
        public_name = f"{slug}-{n}{src_path.suffix or '.png'}"
        bundle_path = out_dir / PUBLIC_IMAGE_DIR / public_name
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_path, bundle_path)
        image_files.append({"local_path": str(bundle_path), "repo_path": f"{PUBLIC_IMAGE_DIR}/{public_name}"})
        section_images.setdefault(img["section"], []).append({**img, "url": f"{PUBLIC_IMAGE_URL_PREFIX}/{public_name}"})
        if img.get("source_url") and not any(s["url"] == img["source_url"] for s in sources):
            sources.append({"platform": img.get("platform"), "title": None,
                            "url": img["source_url"], "author": img.get("author")})

    image_refs = [{"section": sec, "url": im["url"], "alt": im.get("alt", sec)}
                  for sec, ims in section_images.items() for im in ims]
    out_path.write_text(_compose_mdx(title=title, summary=summary, tag=tag, sections=sections,
                                     section_images=section_images, sources=sources,
                                     has_images=bool(image_files), lang="ko"), encoding="utf-8")

    meta_path = out_dir / f"{slug}.meta.json"
    meta_path.write_text(json.dumps({
        "content_type": content_type, "title": title, "tag": tag,
        "sources": sources, "image_files": image_files, **(refine_meta or {}),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"path": out_path, "meta_path": meta_path, "slug": slug, "image_files": image_files,
            "image_refs": image_refs, "sources": sources}


def render_note_en(*, ko_result: dict, title: str, summary: str, tag: str, sections: dict,
                   section_map: dict, out_dir: Path) -> dict:
    """한국어 노트와 같은 slug로 영문 mdx를 out_dir/en/<slug>.mdx에 쓴다(포트폴리오의 en 폴더 구조와 동일).
    이미지는 한국어 노트에서 이미 번들한 파일을 같은 URL로 참조한다(다시 복사하지 않음).
    section_map: {"현상": "Symptom", ...} — 이미지가 붙은 섹션 이름을 영어로 바꾸는 용도."""
    en_dir = out_dir / "en"
    en_dir.mkdir(parents=True, exist_ok=True)
    section_images: dict = {}
    for ref in ko_result.get("image_refs", []):
        en_section = section_map.get(ref["section"], ref["section"])
        section_images.setdefault(en_section, []).append(
            {"url": ref["url"], "alt": f"{en_section} {_L10N['en']['shot']}"})
    out_path = en_dir / f"{ko_result['slug']}.mdx"
    out_path.write_text(_compose_mdx(title=title, summary=summary, tag=tag, sections=sections,
                                     section_images=section_images, sources=ko_result.get("sources", []),
                                     has_images=bool(ko_result.get("image_files")), lang="en"), encoding="utf-8")
    return {"en_path": out_path}
