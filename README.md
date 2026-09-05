# llm-tap

A native Linux daemon for capturing **OpenAI-compatible inference traffic** from any compatible inference server (vLLM, llama.cpp, Ollama, …).

`llm-tap` sits between your clients and inference engine, forwards requests and streaming responses unchanged, and records one JSON line per completion — prompt, full message context, reasoning, result, timing, client, model, and token usage when available.

```text
agents ──► :8001 (llm-tap) ──► 127.0.0.1:8000 (engine)
                    │
                    └──► /var/log/llm-tap/8000.jsonl
```

## Install on Ubuntu

The recommended installation is the signed Ubuntu APT repository. Packages are available for Ubuntu 22.04 (Jammy), 24.04 (Noble), and 26.04 (Resolute) on `amd64`.

Install the repository signing key and APT source:

```bash
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://tecfu.github.io/llm-tap/apt-key.asc \
  | sudo gpg --dearmor -o /etc/apt/keyrings/llm-tap.gpg

. /etc/os-release
sudo tee /etc/apt/sources.list.d/llm-tap.sources >/dev/null <<EOF
Types: deb
URIs: https://tecfu.github.io/llm-tap
Suites: ${VERSION_CODENAME}
Components: main
Architectures: amd64
Signed-By: /etc/apt/keyrings/llm-tap.gpg
EOF

sudo apt update
sudo apt install llm-tap
```

The package includes the application and its Python runtime dependencies, so installing `llm-tap` does not require Docker or running `pip` on the host.

### Configure and start the daemon

Create `/etc/llm-tap/llm-tap.env`:

```bash
sudo install -d /etc/llm-tap
sudo tee /etc/llm-tap/llm-tap.env >/dev/null <<'EOF'
UPSTREAM=http://127.0.0.1:8000
TAP_PORT=8001
TAP_LOG=/var/log/llm-tap/8000.jsonl
EOF
```

Then start it with systemd:

```bash
sudo systemctl enable --now llm-tap
systemctl status llm-tap
journalctl -u llm-tap -f
```

The package creates the `llm-tap` service account, `/var/log/llm-tap` log directory, `/usr/bin/llm-tap` command, and systemd unit.

## Native installation from source

For development or installation outside the APT repository, install directly from a checkout. Python 3.10+ is required.

```bash
git clone https://github.com/tecfu/llm-tap.git
cd llm-tap
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

Run the daemon in the foreground:

```bash
llm-tap --upstream http://127.0.0.1:8000 --listen-port 8001 \
  --log /var/log/llm-tap/8000.jsonl
```

For production installations, prefer the Ubuntu package so systemd integration, the service account, log directory, and bundled dependencies are installed consistently.

## Configuration

The launcher accepts these environment variables:

- `UPSTREAM` — upstream inference server URL (default: `http://127.0.0.1:8000`)
- `TAP_PORT` — local listening port (default: `8001`)
- `TAP_LOG_DIR` — default directory for native JSONL logs (default: `/var/log/llm-tap`)
- `TAP_LOG` — complete JSONL path; overrides the generated log path

CLI arguments override the corresponding defaults. `--foreground` is available for service-manager deployments; the launcher already runs in the foreground by default.

## systemd

The repository includes `packaging/llm-tap.service`. The Ubuntu package installs and configures this unit automatically.

For a manual source installation, create a dedicated service account and log directory, install the application, then copy the unit:

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin llm-tap
sudo install -d -o llm-tap -g llm-tap /var/log/llm-tap
sudo install -d /etc/llm-tap
sudo install -m 0644 packaging/llm-tap.service /etc/systemd/system/llm-tap.service
sudo systemctl daemon-reload
sudo systemctl enable --now llm-tap
```

Configure `/etc/llm-tap/llm-tap.env`:

```ini
UPSTREAM=http://127.0.0.1:8000
TAP_PORT=8001
TAP_LOG=/var/log/llm-tap/8000.jsonl
```

The service is deliberately supervised by systemd rather than daemonizing itself. This makes restarts, failures, and process ownership predictable.

## Releases and APT repository

Releases are built by GitHub Actions and published as a signed static APT repository on GitHub Pages. To publish a release, push a version tag such as `v0.1.1`.

The publication workflow builds packages for each supported Ubuntu release, generates APT metadata, signs the repository, and publishes the generated repository contents to the `gh-pages` branch.

The first publication requires:

1. Add an `APT_GPG_PRIVATE_KEY` repository Actions secret containing the ASCII-armored private signing key.
2. Enable GitHub Pages for the repository using the `gh-pages` branch as the publishing source.
3. Push a `v*` tag to trigger the build and publication workflow.

Keep the private signing key outside the repository. Only the public key is published at `apt-key.asc`.

## Records

One JSONL line is written per completion:

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

- `req_ts` = request arrival, `ts` = response completed (both local time); `dt` = seconds since the previous record (null for the first).
- `prompt` = last real user message (context-mode's injected reminder is skipped; raw `prompt` field for `/v1/completions`); `context` = the full messages array, with tool calls summarized.
- `tokens` appears when the client sends `stream_options.include_usage`.

## Live output

The daemon also echoes captured traffic in a colorized, greppable format:

```bash
journalctl -u llm-tap -f
```

- `IN` — input prompt, printed when the request reaches the proxy.
- `THINK` — reasoning from the completed response.
- `OUT` — generated result.
- Meta information is dimmed; non-200 responses are highlighted.

The gap between `IN` and `OUT` represents real engine latency. A dangling `IN` with no `OUT` means the request is still queued/running or the client aborted.

Clear the JSONL for a native install:

```bash
sudo -u llm-tap sh -c 'rm -f /var/log/llm-tap/*.jsonl'
```

Ad-hoc analysis reads the JSONL directly with standard tools such as `jq`.

## Notes

- Native installs log to `/var/log/llm-tap/<engine-port>.jsonl` by default. Logs persist across reboots unless the host manages retention.
- Cleartext prompts and answers are written to the log. Protect the log directory appropriately because anyone with read access can see captured inference traffic.
- Bypass the tap by stopping the service; clients can then target the engine's localhost port directly.
