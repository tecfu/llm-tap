"""LLM tap: mitmdump addon and native launcher for OpenAI-compatible inference servers."""
import argparse
import json
import os
import time
from pathlib import Path

from mitmproxy import http

UPSTREAM = os.environ.get("UPSTREAM", "http://127.0.0.1:8000")
DEFAULT_PORT = os.environ.get("TAP_PORT", "8001")
LOG_DIR = Path(os.environ.get("TAP_LOG_DIR", Path.home() / ".local/state/llm-tap"))
_port = UPSTREAM.rsplit(":", 1)[-1].split("/")[0]
LOG = Path(os.environ.get("TAP_LOG", str(LOG_DIR / f"{_port if _port.isdigit() else 'tap'}.jsonl")))
_last = None
_INJECTED = ("context-mode active.", "<session_state")
SKIP = ("/health", "/metrics", "/docs", "/redoc", "/openapi.json", "/version",
        "/tokenize", "/detokenize", "/v1/models", "/load", "/ping")


def _iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(epoch)) + f".{int(epoch * 1000) % 1000:03d}"


def _hms(epoch):
    return _iso(epoch)[11:]


def _cut(s, n):
    return (s or "").replace("\n", " ")[:n]


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


def _prompt_text(body):
    prompt = body.get("prompt")
    if prompt is None:
        prompt = next((m["text"] for m in reversed(_ctx(body))
                       if m["role"] == "user" and not m["text"].startswith(_INJECTED)), "")
    if isinstance(prompt, list):
        prompt = "".join(map(str, prompt))
    return prompt


def _echo_in(flow):
    print(f"\x1b[2m{_hms(flow.metadata['t0'])}\x1b[0m \x1b[36mIN    {_cut(flow.metadata['prompt'], 140)}\x1b[0m", flush=True)


def _echo_out(rec):
    ts = rec["ts"][11:23]
    if rec["reasoning"]:
        print(f"\x1b[2m{ts}\x1b[0m \x1b[35mTHINK {_cut(rec['reasoning'], 160)}\x1b[0m", flush=True)
    meta = f"\x1b[2m {rec['client']} {rec['model']}" + (f" +{rec['dt']}s" if rec.get("dt") is not None else "") + "\x1b[0m"
    print(f"\x1b[2m{ts}\x1b[0m \x1b[32mOUT   {_cut(rec['result'], 160)}\x1b[0m{meta}", flush=True)
    if rec["status"] != 200:
        print(f"\x1b[2m{ts}\x1b[0m \x1b[31mSTATUS {rec['status']}\x1b[0m", flush=True)


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
    flow.metadata["prompt"] = _prompt_text(flow.metadata["body"])
    _echo_in(flow)


def responseheaders(flow: http.HTTPFlow):
    if flow.metadata.get("skip"):
        return
    flow.metadata["raw"] = []

    def tee(data: bytes) -> bytes:
        flow.metadata["raw"].append(data)
        return data

    flow.response.stream = tee


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

    now = time.time()
    global _last
    dt = round(now - _last, 3) if _last is not None else None
    _last = now
    peer = getattr(flow.client_conn, "peername", None)
    client = peer[0] if peer else "unknown"
    rec = {"ts": _iso(now), "req_ts": _iso(flow.metadata.get("t0", now)), "dt": dt,
           "client": client, "model": model, "stream": bool(body.get("stream")),
           "status": flow.response.status_code, "prompt": flow.metadata.get("prompt", ""),
           "context": _ctx(body), "reasoning": reasoning, "result": result}
    if usage:
        rec["tokens"] = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens")}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    _echo_out(rec)


def main():
    parser = argparse.ArgumentParser(description="Capture an OpenAI-compatible inference proxy as JSONL")
    parser.add_argument("--upstream", default=UPSTREAM, help="Upstream URL (default: UPSTREAM or 127.0.0.1:8000)")
    parser.add_argument("--listen-port", type=int, default=int(DEFAULT_PORT), help="Local proxy port")
    parser.add_argument("--log", default=str(LOG), help="JSONL output path")
    parser.add_argument("--foreground", action="store_true", help="Run in foreground (the default; suitable for systemd)")
    args = parser.parse_args()
    os.environ["UPSTREAM"] = args.upstream
    os.environ["TAP_LOG"] = args.log
    import subprocess
    cmd = ["mitmdump", "--mode", f"reverse:{args.upstream}@{args.listen_port}", "-s", str(Path(__file__).resolve())]
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
