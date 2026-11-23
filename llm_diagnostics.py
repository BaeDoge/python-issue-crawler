"""OmniRoute OpenAI-compatible endpoint diagnostics.

The probe stores only status/latency/token metadata. It never stores prompts,
generated text, API keys, or full provider responses.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

from config import LOG_DIR, OMNIROUTE_API_KEY, OMNIROUTE_BASE_URL
from config import SCOUT_MODEL, VERIFIER_MODEL, WRITER_MODEL


def classify_http_status(status_code: int) -> str:
    if 200 <= status_code < 300:
        return "ok"
    if status_code in (401, 403):
        return "authentication_or_permission"
    if status_code == 404:
        return "endpoint_or_model_not_found"
    if status_code == 429:
        return "rate_limit_or_quota"
    if status_code in (408, 425, 500, 502, 503, 504):
        return "temporary_upstream_failure"
    if 400 <= status_code < 500:
        return "request_rejected"
    return "server_error"


def _safe_base_url() -> str:
    parsed = urlsplit(OMNIROUTE_BASE_URL)
    host = parsed.hostname or "unknown-host"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme or 'http'}://{host}{parsed.path.rstrip('/')}"


def _models_to_probe() -> list[dict]:
    grouped: dict[str, list[str]] = {}
    for role, model in (
        ("scout", SCOUT_MODEL),
        ("writer", WRITER_MODEL),
        ("verifier", VERIFIER_MODEL),
    ):
        name = str(model or "").strip()
        if name:
            grouped.setdefault(name, []).append(role)

    # Use exact IDs from GET /v1/models or the OmniRoute dashboard.
    for name in (part.strip() for part in os.getenv("OMNIROUTE_DIAG_MODELS", "").split(",")):
        if name:
            grouped.setdefault(name, []).append("custom")

    return [{"model": model, "roles": roles} for model, roles in grouped.items()]


def _redact(value: object) -> str:
    message = str(value or "")
    if OMNIROUTE_API_KEY:
        message = message.replace(OMNIROUTE_API_KEY, "[REDACTED]")
    message = re.sub(r"(?i)bearer\s+[^\s,;]+", "Bearer [REDACTED]", message)
    message = re.sub(r"(?i)(sk|nvapi|AIza)[-_][A-Za-z0-9_-]{12,}", "[REDACTED_TOKEN]", message)
    return re.sub(r"\s+", " ", message).strip()[:280]


def _response_error(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = response.text
    if isinstance(payload, dict):
        error = payload.get("error", payload)
        if isinstance(error, dict):
            message = error.get("message") or error.get("detail") or error.get("type") or error
        else:
            message = error
    else:
        message = payload
    return _redact(message)


def _probe_model(model: str, roles: list[str]) -> dict:
    endpoint = f"{OMNIROUTE_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OMNIROUTE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: BLOG_API_OK"}],
        "temperature": 0,
        "max_tokens": 24,
        "stream": False,
    }
    started = time.perf_counter()
    result = {
        "model": model, "roles": roles, "status": "unknown",
        "http_status": None, "latency_ms": None, "response_model": None,
        "finish_reason": None, "prompt_tokens": None, "completion_tokens": None,
        "request_id": None, "error": None,
    }

    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=(10, 60))
        result["latency_ms"] = round((time.perf_counter() - started) * 1000)
        result["http_status"] = response.status_code
        result["request_id"] = response.headers.get("x-request-id")
        if not response.ok:
            result["status"] = classify_http_status(response.status_code)
            result["error"] = _response_error(response)
            return result

        try:
            data = response.json()
        except ValueError:
            result["status"] = "invalid_json_response"
            result["error"] = "HTTP 2xx 응답이지만 JSON으로 해석할 수 없습니다."
            return result

        choices = data.get("choices") or []
        first = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            result["status"] = "empty_model_response"
            result["error"] = "HTTP 2xx 응답에 choices[0].message.content가 없습니다."
            return result

        usage = data.get("usage") or {}
        result.update({
            "status": "ok",
            "response_model": data.get("model"),
            "finish_reason": first.get("finish_reason"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        })
        return result

    except requests.Timeout as exc:
        result["latency_ms"] = round((time.perf_counter() - started) * 1000)
        result["status"] = "timeout"
        result["error"] = _redact(exc)
        return result
    except requests.RequestException as exc:
        result["latency_ms"] = round((time.perf_counter() - started) * 1000)
        result["status"] = "connection_error"
        result["error"] = _redact(exc)
        return result


def _check_model_catalog() -> dict:
    endpoint = f"{OMNIROUTE_BASE_URL.rstrip('/')}/models"
    try:
        response = requests.get(
            endpoint,
            headers={"Authorization": f"Bearer {OMNIROUTE_API_KEY}"},
            timeout=(5, 15),
        )
        if not response.ok:
            return {
                "status": classify_http_status(response.status_code),
                "http_status": response.status_code,
                "model_count": None, "sample": [],
                "error": _response_error(response),
            }
        payload = response.json()
        models = payload.get("data", []) if isinstance(payload, dict) else []
        names = [
            str(item.get("id")) for item in models
            if isinstance(item, dict) and item.get("id")
        ]
        return {
            "status": "ok", "http_status": response.status_code,
            "model_count": len(names), "sample": names[:12], "error": None,
        }
    except (requests.RequestException, ValueError) as exc:
        return {
            "status": "catalog_unavailable", "http_status": None,
            "model_count": None, "sample": [], "error": _redact(exc),
        }


def run_llm_diagnose() -> bool:
    specs = _models_to_probe()
    print("=" * 64)
    print("OmniRoute LLM 연결 진단")
    print(f"Endpoint: {_safe_base_url()}")
    print("저장: 모델 ID, 역할, HTTP 상태, 지연 시간, 토큰 수, 축약된 오류")
    print("미저장: API 키, 프롬프트, 생성 응답 본문")
    print("-" * 64)

    catalog = _check_model_catalog()
    if catalog["status"] == "ok":
        print(f"모델 목록: 정상 ({catalog['model_count']}개 모델 확인)")
    else:
        print(f"모델 목록: {catalog['status']} / {catalog.get('error') or '상세 오류 없음'}")
        print("모델 목록 API가 비활성화되어도 지정한 모델별 테스트는 계속합니다.")

    if not specs:
        print("테스트할 모델이 없습니다. OMNIROUTE_MODEL_* 또는 OMNIROUTE_DIAG_MODELS를 확인하세요.")
        return False

    results = []
    for spec in specs:
        result = _probe_model(spec["model"], spec["roles"])
        results.append(result)
        label = ", ".join(spec["roles"])
        latency = f"{result['latency_ms']} ms" if result["latency_ms"] is not None else "시간 미측정"
        code = f"HTTP {result['http_status']}" if result["http_status"] is not None else result["status"]
        print(f"{'✅' if result['status'] == 'ok' else '❌'} {spec['model']} [{label}] — {code}, {latency}")
        if result.get("error"):
            print(f"   원인: {result['error']}")

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": _safe_base_url(),
        "catalog": catalog,
        "results": results,
        "summary": {
            "passed": sum(item["status"] == "ok" for item in results),
            "total": len(results),
        },
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    report_path = LOG_DIR / "llm_diagnostics_latest.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    passed = report["summary"]["passed"]
    print("-" * 64)
    print(f"결과: {passed}/{len(results)}개 모델 호출 성공")
    print(f"진단 리포트: {report_path}")
    print("실제 백엔드 제공사, 재시도, 폴백 경로는 OmniRoute Request Logs에서도 확인하세요.")
    return passed == len(results)


if __name__ == "__main__":
    raise SystemExit(0 if run_llm_diagnose() else 1)
