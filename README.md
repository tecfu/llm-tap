# llm-tap

A mitmproxy-based capture tap for **any OpenAI-compatible inference server**
(vLLM, llama.cpp, ollama, …). It owns the port your clients already target,
forwards to the engine untouched, and appends one JSON line per completion —
prompt, full message context, reasoning, result — to a JSONL file.

```
agents ──► :TAP_PORT (llm-tap) ──► 127.0.0.1:$PORT (engine)
                     │
                     └──► $TAP_LOG (JSONL)
```

## Ubuntu APT installation

The project can publish signed `.deb` packages for Ubuntu 22.04 (Jammy),
24.04 (Noble), and 26.04 (Resolute) on `amd64`. Releases are built by GitHub
Actions and published as a static APT repository on GitHub Pages.

The repository signing key is published by the repository itself. Before the
first release is published, configure the `APT_GPG_PRIVATE_KEY` GitHub Actions
secret with the ASCII-armored private key used to sign the repository.

After the first package release is published, install the public key and APT
source:

```bash
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://tecfu.github.io/tap/apt-key.asc \
  | sudo gpg --dearmor -o /etc/apt/keyrings/llm-tap.gpg

. /etc/os-release
sudo tee /etc/apt/sources.list.d/llm-tap.sources >/dev/null <<EOF
Types: deb
URIs: https://tecfu.github.io/tap
Suites: ${VERSION_CODENAME}
Components: main
Architectures: amd64
Signed-By: /etc/apt/keyrings/llm-tap.gpg
EOF

sudo apt update
sudo apt install llm-tap
```

Then configure and start the service:

```bash
sudo install -d /etc/llm-tap
sudo tee /etc/llm-tap/llm-tap.env >/dev/null <<'EOF'
UPSTREAM=http://127.0.0.1:8000
TAP_PORT=8001
TAP_LOG=/var/log/llm-tap/8000.jsonl
EOF
sudo systemctl enable --now llm-tap
```

The package creates the `llm-tap` service account, log directory, CLI at
`/usr/bin/llm-tap`, and systemd unit. Python dependencies are bundled in the
package's application environment so installation does not run pip at install
time.

### Publishing releases

Create and push a version tag such as `v0.1.0`. The APT workflow builds one
package for each supported Ubuntu release and publishes signed repository
metadata to the `gh-pages` branch.

The first publication requires:

1. Add an `APT_GPG_PRIVATE_KEY` repository Actions secret containing the
   ASCII-armored private signing key.
2. Enable GitHub Pages for the repository using the `gh-pages` branch as the
   publishing source.
3. Push a `v*` tag to trigger the build and publication workflow.

Keep the private key outside the repository. Only the public key is published
at `apt-key.asc`.

## Native installation

The native distribution runs directly on Linux without Docker. Python 3.10+
and `mitmproxy` are required.

### Install from a checkout

```bash
git clone https://github.com/tecfu/tap.git
cd tap
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

Run it in the foreground with an engine on port 8000:

```bash
llm-tap --upstream http://127.0.0.1:8000 --listen-port 8001 \
  --log /var/log/llm-tap/8000.jsonl
```

For a system-wide install, use a virtual environment such as
`/opt/llm-tap` and point the systemd unit's `ExecStart` at that environment's
`llm-tap` executable.

### Environment configuration

The launcher accepts these environment variables:

- `UPSTREAM` — upstream inference server URL (default: `http://127.0.0.1:8000`)
- `TAP_PORT` — local listening port (default: `8001`)
- `TAP_LOG_DIR` — default directory for native JSONL logs (default:
  `/var/log/llm-tap`)
- `TAP_LOG` — complete JSONL path; overrides the generated log path

CLI arguments override the corresponding defaults. `--foreground` is
provided explicitly for service-manager deployments; the launcher already
runs in the foreground by default.

## systemd

The repository includes `packaging/llm-tap.service` as a starting point for
Linux daemon installation.

Create the service account and log directory, install the application, then
copy the unit into `/etc/systemd/system`:

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin llm-tap
sudo install -d -o llm-tap -g llm-tap /var/log/llm-tap
sudo install -d /etc/llm-tap
sudo install -m 0644 packaging/llm-tap.service /etc/systemd/system/llm-tap.service
sudo systemctl daemon-reload
sudo systemctl enable --now llm-tap
```

Configure the daemon in `/etc/llm-tap/llm-tap.env`:

```ini
UPSTREAM=http://127.0.0.1:8000
TAP_PORT=8001
TAP_LOG=/var/log/llm-tap/8000.jsonl
```

Check status and logs with:

```bash
systemctl status llm-tap
journalctl -u llm-tap -f
```

The service is deliberately supervised by systemd rather than daemonizing
itself. This makes restarts, failures, and process ownership predictable.

## Docker

Docker Compose remains supported:

```bash
docker compose up -d
PORT=8080 docker compose up -d
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
journalctl -u llm-tap -f
```

IN is printed the instant the request hits the proxy (its own timestamp);
THINK/OUT when the response completes (their own timestamp). The vertical
gap between the IN and OUT lines is real engine latency, and a dangling IN
with no OUT means the request is still queued/running or the client aborted.

Clear the JSONL for a native install:

```bash
sudo -u llm-tap sh -c 'rm -f /var/log/llm-tap/*.jsonl'
```

Ad-hoc analysis reads the JSONL directly (host jq): `… | jq -s 'group_by(.client) | map({client: .[0].client, reqs: length, prompt_toks: (map(.tokens.prompt_tokens // 0) | add)})'`

## Notes

- Native installs default to `/var/log/llm-tap/<engine-port>.jsonl`; Docker
  retains `/tmp/llm-tap/<engine-port>.jsonl` for compatibility. Native logs
  persist across reboots unless the host manages retention.
- Cleartext prompts/answers are written to the log. Protect the log directory
  appropriately because anyone with read access can see captured inference
  traffic.
- Bypass the tap by stopping the service/container; clients can then target
  the engine's localhost port directly.
