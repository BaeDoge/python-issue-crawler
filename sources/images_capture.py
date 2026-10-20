"""
실제 이미지 가져오기 — GitHub/StackOverflow/블로그 글에 첨부된 스크린샷을 "그대로"
다운로드합니다 (AI 생성 아님).
========================================================================
깨진 이미지가 글에 들어가는 일이 없도록, 내려받은 바이트가 진짜 이미지인지 확인합니다.
- 응답이 HTML(로그인 페이지, 403 안내 등)이면 버림 — 예전 버전은 용량만 확인해서
  HTML을 .png로 저장하는 경우가 있었습니다.
- 파일 앞부분(매직 바이트)으로 PNG/JPEG/GIF/WebP를 판별하고, 확장자는 실제 형식에 맞춥니다.
- PNG/JPEG/GIF는 가로·세로를 읽어서 아이콘/이모티콘처럼 너무 작은 이미지는 버립니다.
검증을 통과한 이미지만 반환하므로, 이미지를 못 구한 경우엔 빈 리스트가 나오고
노트는 이미지 없이 만들어집니다(에러 로그가 코드블록으로 충분히 설명되는 글이 대부분).
"""

import re
import struct
from pathlib import Path

from sources import net

MD_IMG_RE = re.compile(r"!\[[^\]]*\]\((https?://[^\s)]+)\)")
HTML_IMG_RE = re.compile(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', re.IGNORECASE)

# 아바타/배지/아이콘/광고처럼 "내용"이 아닌 이미지를 거르는 URL 패턴
_NOISE_PATTERNS = re.compile(
    r"(avatars\.githubusercontent|avatar|/badge/|shields\.io|img\.shields|gravatar|favicon|"
    r"/emoji/|emoticon|/ads?/|banner|tistory_admin|blank\.(gif|png)|spacer|pixel|"
    r"profile|/icon|logo)",
    re.IGNORECASE,
)

MIN_BYTES = 3000
MIN_WIDTH = 200
MIN_HEIGHT = 60
MAX_BYTES = 8 * 1024 * 1024


def extract_content_image_urls(raw_body: str, limit: int = 3) -> list:
    """markdown(GitHub)과 HTML(StackOverflow) 둘 다에서 이미지 URL을 뽑는다.
    아바타/배지류는 제외하고, 순서를 유지한 채 중복 제거."""
    if not raw_body:
        return []
    found = MD_IMG_RE.findall(raw_body) + HTML_IMG_RE.findall(raw_body)
    return filter_image_urls(found, limit)


def filter_image_urls(urls: list, limit: int = 3) -> list:
    seen, out = set(), []
    for url in urls:
        if not url or url in seen or _NOISE_PATTERNS.search(url):
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= limit:
            break
    return out


def sniff_image(data: bytes):
    """반환: (확장자, width|None, height|None) 또는 이미지가 아니면 None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return ".png", w, h
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        w, h = struct.unpack("<HH", data[6:10])
        return ".gif", w, h
    if data[:3] == b"\xff\xd8\xff":
        return (".jpg", *_jpeg_size(data))
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp", None, None
    return None


def _jpeg_size(data: bytes):
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + seg_len
    return None, None


def download_image(url: str, out_stem: Path, *, referer: str | None = None, timeout: int = 15):
    """검증을 통과하면 확장자를 붙여 저장하고 경로를 반환, 아니면 None.
    out_stem: 확장자 없는 경로(예: out_dir/'note-1')"""
    headers = {"Accept": "image/*,*/*;q=0.8"}
    if referer:
        headers["Referer"] = referer
    data = net.get_bytes(url, headers=headers, timeout=timeout, quiet=True)
    if data is None:
        return None

    if len(data) < MIN_BYTES or len(data) > MAX_BYTES:
        return None
    info = sniff_image(data)
    if not info:
        return None  # HTML 등 이미지가 아닌 응답
    ext, w, h = info
    if w is not None and (w < MIN_WIDTH or h < MIN_HEIGHT):
        return None  # 아이콘/이모티콘 크기

    out_path = out_stem.with_suffix(ext)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    return out_path


def capture_images(*, items: list, out_dir: Path, slug_hint: str, max_images: int = 2) -> list:
    """items: [{"section", "urls"(이미 뽑아둔 URL 목록) 또는 "raw_body"(원문),
                "source_url", "platform", "author"}]
    각 item에서 검증을 통과하는 첫 이미지 1장씩, 총 max_images장까지.
    반환: [{"section","local_path","source_url","platform","author","alt"}]"""
    results = []
    used_sections = set()
    for idx, item in enumerate(items):
        if len(results) >= max_images:
            break
        if item["section"] in used_sections:
            continue  # 같은 섹션엔 한 장만
        urls = item.get("urls") or extract_content_image_urls(item.get("raw_body", ""), limit=4)
        for n, url in enumerate(urls):
            path = download_image(url, out_dir / f"{slug_hint}-src{idx}{n}", referer=item.get("source_url"))
            if path:
                results.append({
                    "section": item["section"],
                    "local_path": path,
                    "source_url": item["source_url"],
                    "platform": item.get("platform", ""),
                    "author": item.get("author"),
                    "alt": f"{item['section']} 스크린샷",
                })
                used_sections.add(item["section"])
                break
    return results
