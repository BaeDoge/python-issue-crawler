# 트러블슈팅 / 알고리즘 노트 자동 생성 파이프라인

코드 트러블슈팅, 알고리즘(코딩테스트) 문제 풀이 두 가지에 집중해서, 소재
수집 → 작성 → 검증 → 포트폴리오 레포에 커밋/푸시(Vercel 자동 배포)까지
자동으로 처리합니다.

## 구조

```
pipeline/
  engine.py              # 1회 실행(수동) — "지금 하나 만들어줘"
  scheduler.py            # 매일 1회 자동 실행 — PC를 켜두는 동안 돎
  config.py                # .env 로딩 + OmniRoute + 배포 설정
  history.py                # 이미 다룬 소재 기록(중복 방지) -> output_files/history.json
  crew_builder.py           # CrewAI 에이전트 공통 빌더
  topics/
    __init__.py              # 레지스트리 (지금은 troubleshooting, algorithm 둘만)
    _common.py                 # 공통 실행 로직(스카우트→작성→검증→렌더)
    troubleshooting.py          # 파이썬 흔한 에러: StackOverflow + 티스토리/velog
    algorithm.py                  # LeetCode (공개 GraphQL)
  sources/
    registry.py              # 소스 설정 (쿼리, 난이도 범위, 폴백 문제 풀)
    web.py                     # StackOverflow(시드 기반)/GitHub 수집
    blogs.py                    # 티스토리·velog 검색 + 본문/이미지 추출
    algorithm.py                 # LeetCode 문제 수집
    images_capture.py              # 원문 이미지 다운로드 + 검증(깨진 파일 차단)
  output/
    note.py                  # 구조화 mdx 렌더러 (현상/원인/해결... 섹션형)
  publish/
    git_publish.py            # 포트폴리오 레포에 커밋 + push
  verify/
    quality.py                 # 검증-재작성 반복 루프
```

## 글 형식

블로그 narrative가 아니라, 고정 섹션으로 구성된 담백한 노트 형식입니다.

- **트러블슈팅**: 현상 → 원인 → 해결 방법 → 다른 해결 방법 → 추가 참고사항
- **알고리즘**: 문제 → 접근 방법 → 풀이 → 다른 풀이 방법 → 추가 참고사항

제목은 포트폴리오 블로그에서 쓰고 계신 형식 그대로 `[트러블슈팅] ...` /
`[코딩테스트] ...`를 따르도록 프롬프트에 박아뒀습니다.

## Writer 출력 형식과 실패 처리

- Writer는 JSON이 아니라 **`제목:` / `요약:` 줄 + `## 섹션명` 마크다운**으로 씁니다
  (`topics/note_format.py`가 파싱). 코드가 들어간 글을 JSON으로 쓰게 하면 따옴표·줄바꿈 때문에
  JSON이 깨지는 일이 잦아서, 5라운드 내내 파싱에 실패하고 제목이 `untitled`인 빈 글이 저장되는
  문제가 있었습니다. 코드블록 안의 `##` 줄은 섹션 헤더로 오인하지 않습니다.
- Writer가 끝내 형식을 못 지키면 **빈 글을 저장하지 않고** 실패로 처리합니다. 이 소재는
  `history.json`에 기록되지 않아 다음에 다시 시도합니다.
- 검증을 최종 통과하지 못했을 때는 라운드별 작성 결과와 지적 사항이 `logs/troubleshooting_날짜.json`에
  저장됩니다. 왜 계속 걸렸는지 거기서 볼 수 있습니다.
- 추론 모델은 `<think>` 토큰도 `max_tokens`에 포함돼서 글이 중간에 끊길 수 있어, Writer의
  `max_tokens`를 6000으로 올렸습니다(`.env`의 `OMNIROUTE_WRITER_MAX_TOKENS`로 조정).

## 설치 및 실행

```bash
cd pipeline
uv sync
cp .env.example .env
```

`.env`에서 최소 다음 항목을 채워야 합니다.
- `OMNIROUTE_API_KEY`
- `PUBLISH_TARGETS` — 발행 대상 저장소 목록(JSON 배열). 여러 저장소를 하나의 환경변수로 설정할 수 있습니다.

**1회 실행 (원할 때마다)**
```bash
uv run pipeline/engine.py                        # 메뉴에서 선택
uv run pipeline/engine.py --topic troubleshooting
uv run pipeline/engine.py --topic algorithm
uv run pipeline/engine.py --topic both            # 둘 다 한 편씩
uv run pipeline/engine.py --topic both --no-publish  # 생성만, 발행은 안 함
uv run pipeline/engine.py --publish-draft output_files/troubleshooting/xxx.mdx  # 보류 초안 발행
```

**매일 자동 실행 (PC를 켜두는 동안)**
```bash
uv run pipeline/scheduler.py
```
`.env`의 `SCHEDULE_TIME`(기본 09:00)에 트러블슈팅 1편 + 알고리즘 1편을 생성해서
자동으로 발행합니다. 터미널을 계속 켜둬야 해서, 꺼지지 않게 하고 싶으면 OS의
작업 스케줄러(Windows: 작업 스케줄러, macOS/Linux: `launchd`/`cron`이나
`tmux`/`nohup`으로 백그라운드 실행)에 등록하는 걸 권장합니다.

## ⚠️ 자동 발행(AUTO_PUSH) 관련 — 꼭 읽어주세요

기본값은 `AUTO_PUSH=true`입니다. 즉, **검증을 통과한 글은 사람이 보지 않고
바로 push되어 Vercel에 배포**됩니다. 검증 루프(최대 5라운드 재작성 + LLM 검수)가
안전장치이긴 하지만, 로컬 LLM 품질을 고려하면 100% 믿기는 어렵습니다.

- 검증을 최종 통과하지 못한 글은 **자동으로 발행되지 않고** 로컬 파일로만
  남습니다(`pipeline/output_files/`) — 직접 보시고 수동으로 옮기시면 됩니다.
- 처음에는 `AUTO_PUSH=false`로 두고 며칠간 결과물을 직접 확인하신 뒤,
  품질이 믿을 만하다 싶으면 `true`로 바꾸시는 걸 권장합니다.
- `false`로 두면 로컬 커밋까지는 되고, push만 직접 `git push`로 하시면 됩니다.

## 여러 저장소에 자동 발행

발행 대상은 `.env`의 `PUBLISH_TARGETS` JSON 배열 하나로 관리합니다. 대상별로 저장소 경로, MDX 저장 위치, 카테고리 폴더 사용 여부, 이미지 경로, 브랜치를 지정할 수 있습니다. 새 대상을 추가할 때 Python 코드를 수정할 필요 없이 배열 항목만 추가하면 됩니다.

```dotenv
PUBLISH_TARGETS='[
  {
    "name": "target-one",
    "repo_path": "C:/path/to/repository-one",
    "posts_dir": "content",
    "category_subdirs": true,
    "images_dir": "public/blogs",
    "image_url_prefix": "/blogs",
    "branch": "main"
  },
  {
    "name": "target-two",
    "repo_path": "C:/path/to/repository-two",
    "posts_dir": "src/app/blog/posts",
    "category_subdirs": false,
    "images_dir": "public/blogs",
    "image_url_prefix": "/blogs",
    "branch": "main"
  }
]'
AUTO_PUSH=true
```

- `name`: 로그에 표시할 대상 이름(중복 불가)
- `repo_path`: 로컬에 clone한 Git 저장소의 절대 경로
- `posts_dir`: MDX를 저장할 저장소 내부 상대 경로
- `category_subdirs`: `true`면 `posts_dir/algorithm/` 또는 `posts_dir/troubleshooting/`에 저장
- `images_dir`: 이미지 파일을 저장할 저장소 내부 상대 경로
- `image_url_prefix`: MDX 본문에서 이미지를 참조하는 URL 경로. 기본값은 `/blogs`
- `branch`: 대상 저장소에 푸시할 브랜치

각 대상은 독립적으로 처리됩니다. 한쪽 저장소의 발행이 실패해도 다른 대상에 대한 발행은 계속 시도합니다. 대상 저장소에 미커밋 변경사항이 있으면 해당 대상의 발행만 중단합니다.

연결된 배포 플랫폼이 Git push를 감지하도록 설정되어 있어야 자동 배포됩니다. Vercel을 사용하는 프로젝트라면 각 저장소가 해당 Vercel 프로젝트에 연결되어 있어야 합니다. `AUTO_PUSH=true`는 GitHub 인증이 이미 구성된 환경에서 push까지 수행합니다.

새 대상은 예시의 두 객체 중 하나를 복사한 뒤 `name`, `repo_path`, `posts_dir` 등 해당 프로젝트에 맞는 값만 수정해 추가하면 됩니다. 예시 경로는 설명용이므로 실제 경로로 교체해야 합니다.

## 트러블슈팅 — 파이썬/라이브러리의 흔한 에러

답이 없는 글(예: "접근 권한이 풀릴 때까지 기다리세요")이 나온 샘플 리뷰를 계기로,
GitHub 이슈 중심에서 **"흔하고 해결이 분명한 에러" 중심**으로 바꿨습니다.

- **소재**: `sources/registry.py`의 `TROUBLESHOOTING_SEEDS`(ModuleNotFoundError,
  IndentationError, `'NoneType' object is not subscriptable`, UnicodeDecodeError cp949,
  pip externally-managed-environment, pandas 에러 등 35개)에서 매번 3개를 무작위로 골라
  StackOverflow에서 **채택 답변이 있고 추천 수 20 이상**인 파이썬3 Q&A를 후보로 삼습니다.
  검색어가 본문에만 걸려 에러와 무관한 인기 질문이 섞이지 않도록(실제로 `if __name__ == "__main__"`
  질문이 나왔음) 제목에 시드의 핵심 단어가 60% 이상 들어 있는 질문만 인정합니다.
  제목의 HTML 엔티티(`&quot;`)는 풀어주고, 답변의 코드(`<pre>`)는 코드블록으로 변환해 Writer에 줍니다.
  시드는 자유롭게 추가/삭제하세요.
- **해결 단서가 있는 후보만**: 채택 답변 본문이 없거나 너무 짧으면 그 후보는 건너뛰고
  다음 후보로 넘어갑니다.
- **중복 방지**: 이미 다룬 소재는 `output_files/history.json`에 기록되어 다시 안 나옵니다.
- **한국어 블로그 보조(선택)**: 선택된 에러로 티스토리/velog 글을 검색해서 한국어 설명과 스크린샷을
  참고 자료로 덧붙입니다(`sources/blogs.py`). **`TAVILY_API_KEY`(무료, tavily.com)가 없으면 사실상
  동작하지 않습니다** — 키 없이 쓰는 DuckDuckGo 스크래핑은 봇으로 판단돼 결과를 못 받는 경우가
  많았습니다(`--diagnose`에서 0건). 블로그가 없어도 StackOverflow 자료만으로 글이 만들어지고,
  블로그를 참고한 글은 허가 전까지 자동 발행되지 않으니 처음엔 키 없이 시작해도 됩니다.
- **GitHub 이슈**는 기본 꺼짐입니다(`TROUBLESHOOTING_USE_GITHUB = True`로 켤 수 있음).
- **품질 검사(기계적)**: `현상`·`해결 방법`에 *실제 코드가 담긴* 코드블록이 있어야 통과합니다
  (주석만 있는 더미 블록 불인정). `해결 방법`에 "기다려야", "해결할 수 없" 같은 표현이 있으면
  재작성합니다. 코드블록이 문장 중간에 한 줄로 붙어 나오는 경우는 저장할 때 자동으로
  올바른 형태로 고칩니다.

## 알고리즘 소스 — LeetCode

백준(acmicpc.net)이 2026년 4월에 서비스를 종료해서 LeetCode로 바꿨습니다.
(이후 데이원컴퍼니가 인수해 재개를 발표했지만 안정적으로 쓸 수 있는 상태인지
불확실해서 의존하지 않습니다.)

- 공식 문서화된 API는 아니지만 널리 쓰이는 공개 GraphQL
  (`leetcode.com/graphql`)로 로그인 없이 문제 목록과 지문을 가져옵니다.
  유료 전용 문제는 제외합니다.
- 문제가 영어라서 Writer가 한국어로 번역/요약하고, 지문을 그대로 복사하지
  않습니다. 원문 링크는 노트 하단에 자동으로 붙습니다.
- 난이도는 `sources/registry.py`의 `ALGORITHM_DIFFICULTY`(기본 EASY, MEDIUM)로
  조정합니다.
- **LeetCode가 스크립트 접근을 막으면(예: Cloudflare 챌린지) 빈 결과가 나올 수
  있습니다.** 그 경우 `ALGORITHM_FALLBACK_SLUGS`의 문제 풀에서 대신 뽑습니다.
  제가 테스트한 환경에서는 leetcode.com에 접속이 안 돼서 이 폴백 경로만
  확인했고, 실제 GraphQL 응답 형식은 직접 돌려보셔야 확인됩니다.

## 이미지와 출처

- 에러 메시지를 코드블록으로 정리하는 것만으로 충분한 글이 많아서 **이미지는 선택 사항**입니다.
  StackOverflow 질문/답변이나 블로그 글에 실제 스크린샷이 있고 검증을 통과하면 `현상`·
  `해결 방법` 섹션에 원본 그대로 넣고, 없으면 이미지 없이 만듭니다.
- **깨진 이미지가 들어가지 않게** 내려받은 파일을 검증합니다: HTML/로그인 페이지 응답은 버리고,
  실제 형식(PNG/JPEG/GIF/WebP)을 확인해서 확장자를 맞추고, 아이콘/이모티콘 크기는 거릅니다.
- 이미지 파일은 mdx 옆 `public/blogs/`에 같이 저장됩니다(포트폴리오 레포와 같은 구조).
  mdx와 `public/` 폴더를 함께 레포에 복사하면 이미지가 깨지지 않습니다.
  `--publish-draft`도 이 파일들을 같이 커밋합니다.
- **출처는 글 맨 아래 `## 출처` 섹션에 한 번에** 모읍니다(StackOverflow 질문·답변 작성자,
  블로그 글 링크, 이미지를 가져온 글 포함). 본문 중간에는 캡션을 달지 않습니다.
- 다른 사람의 이미지나 블로그 글을 참고한 노트는 `HOLD_THIRD_PARTY=true`(기본값)면
  `AUTO_PUSH`와 무관하게 **자동 발행하지 않고** 초안으로만 남습니다. 허가를 받으신 뒤:

```bash
uv run pipeline/engine.py --publish-draft output_files/troubleshooting/xxx.mdx
```

  허가 절차가 정리돼서 자동 발행해도 괜찮으면 `.env`에서 `HOLD_THIRD_PARTY=false`로 바꾸세요.
  (그 전에는 블로그를 참고한 트러블슈팅 글이 초안으로 쌓이고, 알고리즘 글만 자동 발행됩니다.)

## 포트폴리오 쪽에서 확인해주실 것

- `tag: "Algorithm"`이라는 새 카테고리를 만들어서 쓰고 있습니다. 기존
  태그 체계에 없던 값이라, 사이트의 태그 필터 UI에 새로 추가해주셔야 할 수도
  있습니다. 다른 이름(`"PS"`, `"코딩테스트"` 등)을 원하시면
  `topics/algorithm.py`의 `tag="Algorithm"`만 바꾸면 됩니다.
- mdx 파일명은 제목에서 자동으로 영문 slug를 만듭니다. 한글 제목만 있어서
  slug를 못 만드는 경우엔 `troubleshooting-20260115-093000.mdx`처럼 날짜
  기반 파일명으로 대체됩니다.

## 후보가 안 나오거나 생성이 실패할 때 — `--diagnose`

```bash
uv run pipeline/engine.py --diagnose
```

소스별(GitHub, StackOverflow, LeetCode, 블로그 검색/본문)로 실제 접속을 시험해서
성공/실패와 **정확한 실패 원인**을 출력하고, 실패 원인별 안내(SSL, 프록시, 차단, 요청 한도)를
보여줍니다. 마지막의 "수집된 오류" 블록을 그대로 복사해서 알려주시면 원인을 바로 짚을 수 있습니다.

이전 버전은 네트워크 예외를 전부 삼키고 "후보를 하나도 못 찾았습니다"만 출력해서 원인을 알 수
없었습니다. 이제는 모든 요청이 `sources/net.py`를 거치고, 실패하면 `[네트워크 오류] 호스트: 이유`가
한 번씩 화면에 찍힙니다.

자주 나오는 원인:
- **StackOverflow 후보가 항상 0건**: StackExchange API는 항상 gzip으로 응답하는데 이전 코드가
  gzip을 못 풀어서 JSON 파싱이 실패했습니다(어느 PC에서나 발생). 이번 버전에서 수정됨.
- **GitHub 403**: 비로그인은 IP당 요청 한도가 작아서, 사내망처럼 같은 IP를 여럿이 쓰면 금방
  소진됩니다. `.env`에 `GITHUB_TOKEN`(무료, 권한 체크 없이 발급)을 넣으세요.
- **SSL 인증서 오류**: 회사 보안 프로그램이 HTTPS를 가로채는 환경. `uv add truststore` 후
  실행하면 Windows 인증서 저장소를 쓰게 됩니다(`USE_SYSTEM_CERTS`, 기본 true).
- **프록시**: `.env`에 `HTTPS_PROXY=http://주소:포트`.
- **LeetCode 403**: Cloudflare 차단일 수 있습니다. 브라우저처럼 쿠키(csrftoken)를 받아 요청하도록
  바꿨지만, 그래도 막히면 오류 문구를 알려주세요.

## 이전 버전과 달라진 점

- 범위를 좁혔습니다: IT뉴스/1년전 오늘/나무위키 랜덤 주제는 제외하고
  트러블슈팅·알고리즘 두 개만 다룹니다.
- 출력 형식을 블로그 narrative에서 고정 섹션형 노트로 바꿨습니다.
- 카드뉴스/표지 기능은 이번 범위에서 제외했습니다(필요해지면 다시 추가
  가능한 구조입니다).
- 포트폴리오 레포에 git으로 직접 커밋/푸시하는 배포 단계가 새로 추가됐습니다.
- 매일 자동 실행용 스케줄러가 추가됐습니다.
