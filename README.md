# llm-tap

A mitmproxy-based capture tap for **any OpenAI-compatible inference server**
(vLLM, llama.cpp, ollama, …). It owns the port your clients already target,
forwards to the engine untouched, and appends one JSON line per completion —
prompt, full message context, reasoning, result — to
`/tmp/llm-tap/<engine-port>.jsonl`.

```
agents ──► :TAP_PORT (llm-tap) ──► UPSTREAM (engine)
                     │
                     └──► /tmp/llm-tap/<engine-port>.jsonl
```

## Run

```bash
docker compose up -d          # reads .env: UPSTREAM, TAP_PORT
```

- Point clients at `:$TAP_PORT` — they never need to know the engine moved.
- Switch engines: edit `UPSTREAM` in `.env`, `docker compose up -d`. Anything
  speaking the OpenAI API works.
- Responses stream through chunk-by-chunk (SSE stays real-time); noise paths
  (`/health`, `/v1/models`, docs) are skipped.

## Records

One JSONL line per completion:

```json
{"ts": "2026-09-01T09:39:56", "req_ts": "2026-09-01T09:39:48", "dt": 4.2,
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
- `prompt` = last user message (or the raw `prompt` field for `/v1/completions`);
  `context` = the full messages array, tool calls summarized.
- `tokens` appears only when the client sends `stream_options.include_usage`.

## Tail

Colorized, live (IN = input prompt in cyan, THINK = reasoning in magenta,
OUT = result in green, meta dim, non-200 status red — prefixes make it
greppable too):

```bash
./tail.sh                      # log auto-derived from UPSTREAM in .env
```

Remote: `ssh box tail -F /tmp/llm-tap/8001.jsonl | ./tail.sh /dev/stdin`

Token spend by client: `… | jq -s 'group_by(.client) | map({client: .[0].client, reqs: length, prompt_toks: (map(.tokens.prompt_tokens // 0) | add)})'`

## Notes

- The log lives in `/tmp/llm-tap/<engine-port>.jsonl` — named for the port
  the engine listens on (from `UPSTREAM`), so several engines can share one
  tap host without mixing logs. Wiped on reboot (and by /tmp age cleaners),
  never needs pruning; the addon recreates the directory on demand. On
  tmpfs-backed /tmp it consumes RAM until reboot.
- Cleartext prompts/answers: anyone with read access to /tmp sees them.
- Bypass the tap: `docker compose stop tap` (clients must then target UPSTREAM
  directly); re-arm with `docker compose start tap`.
