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
