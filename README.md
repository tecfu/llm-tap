# llm-tap

A mitmproxy-based capture tap for **any OpenAI-compatible inference server**
(vLLM, llama.cpp, ollama, …). It owns the port your clients already target,
forwards to the engine untouched, and appends one JSON line per completion —
prompt, full message context, reasoning, result — to
`/tmp/llm-tap/<engine-port>.jsonl`.

```
agents ──► :TAP_PORT (llm-tap) ──► 127.0.0.1:$PORT (engine)
                     │
                     └──► /tmp/llm-tap/<engine-port>.jsonl
```

## Run

```bash
docker compose up -d              # taps localhost:$PORT (defaults from .env)
PORT=8080 docker compose up -d    # engine port as an argument
```

- Localhost-only: the tap forwards to `http://127.0.0.1:$PORT` and listens
  on `$TAP_PORT` (defaults in `docker-compose.yml`, pinned in `.env`).
- Point clients at `:$TAP_PORT` — they never need to know the engine moved.
- Switch engines: `PORT=8080 docker compose up -d`. Anything speaking the
  OpenAI API works.
- Responses stream through chunk-by-chunk (SSE stays real-time); noise paths
  (`/health`, `/v1/models`, docs) are skipped.

## Records

One JSONL line per completion:

```json
{"ts": "2026-09-01T09:39:56.412", "req_ts": "2026-09-01T09:39:48.107", "dt": 4.2,
 "client": "192.168.0.37", "model": "qwen3.8-27b",
 "stream": true, "status": 200,
 "prompt": "Current local time: …",
 "context": [{"role": "developer", "text": "You are…"},
             {"role": "assistant", "text": "[tool_calls: 1]"}],
 "reasoning": "…", "result": "This chunk contained…",
 "tokens": {"prompt_tokens": 3556, "completion_tokens": 93}}
```

- `req_ts` = request arrival, `ts` = response completed (both local time);
  `dt` = seconds since the previous record (null for the first).
- `prompt` = last real user message (context-mode's injected reminder is
  skipped; raw `prompt` field for `/v1/completions`);
  `context` = the full messages array, tool calls summarized.
- `tokens` appears only when the client sends `stream_options.include_usage`.

## Tail

Colorized, live — the addon echoes the same stream it logs (IN = input prompt
in cyan, THINK = reasoning in magenta, OUT = result in green, meta dim,
non-200 status red — prefixes make it greppable too):

```bash
docker compose logs -f --no-log-prefix tap
```

IN is printed the instant the request hits the proxy (its own timestamp);
THINK/OUT when the response completes (their own timestamp). The vertical
gap between the IN and OUT lines is real engine latency, and a dangling IN
with no OUT means the request is still queued/running or the client aborted.

Clear the JSONL: `docker compose exec tap sh -c 'rm -f /tmp/llm-tap/*.jsonl'`

Ad-hoc analysis reads the JSONL directly (host jq): `… | jq -s 'group_by(.client) | map({client: .[0].client, reqs: length, prompt_toks: (map(.tokens.prompt_tokens // 0) | add)})'`

## Notes

- The log lives in `/tmp/llm-tap/<engine-port>.jsonl` — named for the port
  the engine listens on (from `PORT`), so several engines can share one
  tap host without mixing logs. Wiped on reboot (and by /tmp age cleaners),
  never needs pruning; the addon recreates the directory on demand. On
  tmpfs-backed /tmp it consumes RAM until reboot.
- Cleartext prompts/answers: anyone with read access to /tmp sees them.
- Bypass the tap: `docker compose stop tap` (clients must then target the
  engine's localhost port directly); re-arm with `docker compose start tap`.
