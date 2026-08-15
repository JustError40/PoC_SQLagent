#!/usr/bin/env python3
"""Optional LLM-as-judge for campaign results.

Scores each answered question against the agent's SQL and a sample of result
rows. Reporting-only: verdicts land in Results.md and are never sent back to
the agent API — there is no feedback path by construction.

Only stdlib is used, like the campaign script itself. Disabled unless
CAMPAIGN_JUDGE_MODEL is set.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

JUDGE_MODEL = os.getenv("CAMPAIGN_JUDGE_MODEL", "").strip()
JUDGE_BASE_URL = os.getenv("CAMPAIGN_JUDGE_BASE_URL", "").strip().rstrip("/")
JUDGE_API_KEY = os.getenv("CAMPAIGN_JUDGE_API_KEY", "").strip()
JUDGE_TIMEOUT_SEC = float(os.getenv("CAMPAIGN_JUDGE_TIMEOUT_SEC", "120"))
JUDGE_RETRIES = max(0, int(os.getenv("CAMPAIGN_JUDGE_RETRIES", "1")))

VERDICTS = ("correct", "partially_correct", "incorrect", "inconclusive")

SYSTEM_PROMPT = (
    "You are a strict evaluator of a text-to-SQL analytics agent. You are given "
    "a user question (possibly in Russian), the SQL the agent produced, the "
    "number of result rows and a sample of them. Judge whether the SQL answers "
    "the question correctly: right tables, joins, filters, aggregations and "
    "plausible result shape. Reply with JSON only: "
    '{"verdict": "correct" | "partially_correct" | "incorrect" | "inconclusive", '
    '"reason": "<one short sentence>"}. Use "inconclusive" when the sample is '
    "not enough to decide (e.g. empty result that may be legitimate)."
)


def enabled() -> bool:
    return bool(JUDGE_MODEL)


def _extract_json(text: str) -> dict:
    """Salvage the first complete JSON object embedded in arbitrary text."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", cleaned):
        try:
            result, _ = decoder.raw_decode(cleaned, match.start())
        except ValueError:
            continue
        if isinstance(result, dict):
            return result
    raise ValueError("judge response did not contain a JSON object")


def _content(body: dict) -> str:
    choices = body.get("choices") or []
    message = choices[0].get("message", {}) if choices and isinstance(choices[0], dict) else {}
    content = message.get("content") or ""
    if isinstance(content, str) and content.strip():
        return content
    # Reasoning-style judges may leave content empty and answer in reasoning_content.
    reasoning = message.get("reasoning_content") or ""
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning
    raise ValueError("judge response did not contain message content")


def judge_answer(question: str, sql: str, row_count: int, row_sample: list, base_url: str = "") -> dict:
    """Score one answered question. Never raises: failures become inconclusive."""
    # Explicit CAMPAIGN_JUDGE_BASE_URL wins over the discovered one: the agent
    # may report a container-only address (host.docker.internal) that does not
    # resolve on the host running this script.
    target_base = (JUDGE_BASE_URL or base_url).rstrip("/")
    if not enabled() or not target_base:
        return {"verdict": "inconclusive", "reason": "judge disabled"}
    user = (
        f"Question: {question}\n\nSQL:\n{sql or '(none captured)'}\n\n"
        f"Result rows: {row_count}\nSample (first {len(row_sample)} rows):\n"
        + json.dumps(row_sample, ensure_ascii=False, default=str)
    )
    payload = {
        "model": JUDGE_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
        "max_tokens": 4096,
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if JUDGE_API_KEY:
        headers["Authorization"] = f"Bearer {JUDGE_API_KEY}"

    last_error = ""
    for _ in range(JUDGE_RETRIES + 1):
        try:
            request = urllib.request.Request(
                f"{target_base}/chat/completions",
                data=json.dumps(payload).encode(),
                method="POST",
                headers=headers,
            )
            with urllib.request.urlopen(request, timeout=JUDGE_TIMEOUT_SEC) as response:
                body = json.loads(response.read().decode())
            parsed = _extract_json(_content(body))
            verdict = str(parsed.get("verdict") or "").strip().lower()
            if verdict not in VERDICTS:
                verdict = "inconclusive"
            return {"verdict": verdict, "reason": str(parsed.get("reason") or "")[:300]}
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:200]}"
        except Exception as exc:  # timeouts, bad JSON — the campaign must go on
            last_error = str(exc)[:300]
    return {"verdict": "inconclusive", "reason": f"judge error: {last_error}"}
