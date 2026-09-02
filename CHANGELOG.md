# Changelog

## 2026-09-01 — extracted from qwen38-27b-rtx3090

- Addon + logs moved out of the engine repo into this standalone repo so the
  tap can front any model/engine, not just qwen38-27b. Deployed at `~/llm-tap`
  on `epyc4000d4u`; container re-pointed to the new paths, ports unchanged
  (clients → :8000 tap → :8001 engine).
- Added `docker-compose.yml` + `.env` (UPSTREAM / TAP_PORT) so other engines
  are one env edit away; addon docstring generalized.
- Log moved to the host's `/tmp/llm-tap/tap.jsonl` (compose bind-mounts `/tmp`):
  wiped on reboot, addon recreates the dir on demand — no pruning, no
  root-owned-dir permission trap.
- Log renamed to `/tmp/llm-tap/<engine-port>.jsonl` (port parsed from
  `UPSTREAM`, passed to the addon as env) — one tap host can front several
  engines without mixing logs; `tail.sh` picks the file the same way.
- Timestamps: records carry `req_ts` (request arrival), `ts` (response done)
  and `dt` (gap since the previous record); `tail.sh` shows `HH:MM:SS → HH:MM:SS +gap`.
- Ports swapped: tap now listens on 8001 (where pi points), engine back on
  8000 (its native port). Engine compose `PORT` restored to 8000.
- Records echoed colorized to stdout — `docker logs -f llm-tap` is now a live
  view, no tail script needed.
- IN echoed the instant the request arrives (own timestamp); THINK/OUT at
  completion (own timestamp) — the IN→OUT gap in the log is real engine
  latency; dangling IN = request still running or client aborted.
- All timestamps carry milliseconds (`ts`, `req_ts`, log echoes; `dt` to 1 ms).
- `.prompt` skips context-mode's injected reminder messages (`context-mode
  active.` / `<session_state` prefixes) so the echo shows the user's typed
  prompt from round one, not the reminder.
- `tail.sh` deleted — every operation is a `docker compose` command: tail =
  `docker compose logs -f --no-log-prefix tap`, clear = `docker compose exec
  tap sh -c 'rm -f /tmp/llm-tap/*.jsonl'`.
- Localhost-only: `UPSTREAM` URL replaced by a port argument —
  `PORT=8080 docker compose up -d` re-points the tap at
  `http://127.0.0.1:8080` (log file follows the port); no remote-tail docs.

## 2026-09-01 — created (as part of qwen38-27b-rtx3090)

- mitmproxy reverse proxy owns the client-facing port; vLLM moved to a
  backend port so every OpenAI-API client is captured with zero client
  changes.
- Addon skips noise paths (`/health`, `/v1/models`, docs), streams responses
  through untouched (SSE chunks teed, not buffered — verified time-to-first-
  token 8 ms), reassembles chat-completions and completions (streaming SSE
  and plain JSON) into one JSONL line: ts, client IP, model, stream, status,
  prompt, context (messages, tool calls summarized), reasoning
  (reasoning_content), result, token counts when `include_usage` is set.
