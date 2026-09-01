"""LLM tap: mitmdump addon that logs prompts, context, reasoning and results
from any OpenAI-compatible inference server (vLLM, llama.cpp, ollama, …)
to tap.jsonl (one JSON line per completion).

Noise paths (health checks, model listings, docs) are skipped.
Responses are streamed through to the client untouched (SSE stays live);
chunks are teed for reassembly. Full prompts+answers land in the log —
treat tap.jsonl as sensitive.
"""
import json
import os
import time
from pathlib import Path

from mitmproxy import http

# host /tmp via bind mount — wiped on reboot, no pruning. One log file per
# engine port (taken from UPSTREAM), so several engines can share a tap host.
_port = os.environ.get("UPSTREAM", "").rsplit(":", 1)[-1].split("/")[0]
LOG = Path(f"/tmp/llm-tap/{_port if _port.isdigit() else 'tap'}.jsonl")
_last = None  # wall time of the previous record → dt field
SKIP = ("/health", "/metrics", "/docs", "/redoc", "/openapi.json", "/version",
        "/tokenize", "/detokenize", "/v1/models", "/load", "/ping")


def _texts(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def _ctx(body):
    out = []
    for m in body.get("messages") or []:
        if m.get("tool_calls"):
            out.append({"role": m.get("role"), "text": "[tool_calls: %d]" % len(m["tool_calls"])})
        else:
            out.append({"role": m.get("role"), "text": _texts(m.get("content"))})
    return out


def _sse(raw):
    reasoning, content, usage = [], [], None
    for line in raw.decode("utf-8", "replace").splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
        except Exception:
            continue
        if chunk.get("usage"):
            usage = chunk["usage"]
        for ch in chunk.get("choices") or []:
            d = ch.get("delta") or ch.get("message") or {}
            reasoning.append(d.get("reasoning_content") or "")
            content.append(d.get("content") or d.get("text") or "")
    return "".join(reasoning), "".join(content), usage


def request(flow: http.HTTPFlow):
    if flow.request.path.startswith(SKIP):
        flow.metadata["skip"] = True
        return
    try:
        flow.metadata["body"] = json.loads(flow.request.get_text(strict=False) or "{}")
    except Exception:
        flow.metadata["body"] = {}
    flow.metadata["t0"] = time.time()


def responseheaders(flow: http.HTTPFlow):
    if flow.metadata.get("skip"):
        return
    flow.metadata["raw"] = []

    def tee(data: bytes) -> bytes:  # pass chunks through live, keep a copy
        flow.metadata["raw"].append(data)
        return data

    flow.response.stream = tee  # streaming keeps SSE real-time for clients


def response(flow: http.HTTPFlow):
    if flow.metadata.get("skip"):
        return
    body = flow.metadata.get("body") or {}
    raw = b"".join(flow.metadata.get("raw") or [])
    model, usage = body.get("model", "?"), None
    if flow.response.headers.get("content-type", "").startswith("text/event-stream"):
        reasoning, result, usage = _sse(raw)
    else:
        try:
            r = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            r = {}
        choice = (r.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        reasoning = msg.get("reasoning_content") or ""
        result = msg.get("content") or choice.get("text") or ""
        usage, model = r.get("usage"), r.get("model", model)

    prompt = body.get("prompt")  # /v1/completions
    if prompt is None:
        prompt = next((m["text"] for m in reversed(_ctx(body)) if m["role"] == "user"), "")
    if isinstance(prompt, list):
        prompt = "".join(map(str, prompt))

    now = time.time()
    global _last
    dt = round(now - _last, 1) if _last is not None else None
    _last = now
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
           "req_ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(flow.metadata.get("t0", now))),
           "dt": dt,
           "client": flow.client_conn.peername[0],
           "model": model,
           "stream": bool(body.get("stream")),
           "status": flow.response.status_code,
           "prompt": prompt,
           "context": _ctx(body),
           "reasoning": reasoning,
           "result": result}
    if usage:
        rec["tokens"] = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens")}
    LOG.parent.mkdir(parents=True, exist_ok=True)  # self-heal after tmp cleaners
    with LOG.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
