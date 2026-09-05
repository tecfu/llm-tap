# llm-tap

A native Linux daemon for capturing **OpenAI-compatible inference traffic** from any compatible inference server (vLLM, llama.cpp, Ollama, …).

`llm-tap` sits between your clients and inference engine, forwards requests and streaming responses unchanged, and records one JSON line per completion — prompt, full message context, reasoning, result, timing, client, model, and token usage when available.

```text
agents ──► :8001 (llm-tap) ──► 127.0.0.1:8000 (engine)
                    │
                    └──► ~/.local/state/llm-tap/8000.jsonl
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

The package includes the application and its Python runtime dependencies. Installation method does not change the `llm-tap` command or its configuration.

## Run

The same command works whether `llm-tap` came from APT, pip, or a source checkout:

```bash
llm-tap --upstream http://127.0.0.1:8000 --listen-port 8001
```

Then point your OpenAI-compatible client at `http://127.0.0.1:8001`.

Configuration is available through the same CLI flags or environment variables everywhere:

- `--upstream` / `UPSTREAM` — upstream inference server (default: `http://127.0.0.1:8000`)
- `--listen-port` / `TAP_PORT` — local listening port (default: `8001`)
- `--log` / `TAP_LOG` — JSONL output path
- `TAP_LOG_DIR` — directory used when `TAP_LOG` is not set

The default log is written beneath `~/.local/state/llm-tap`, so an ordinary user can run the command without special filesystem permissions. Set `--log` when you want another location.

## Run with systemd

For a machine-wide daemon, systemd is optional process supervision around the same `llm-tap` command. The Ubuntu package includes the unit and creates the `llm-tap` service account and `/var/log/llm-tap` directory.

Configure `/etc/llm-tap/llm-tap.env` only if you want to run it as a system service:

```text
UPSTREAM=http://127.0.0.1:8000
TAP_PORT=8001
TAP_LOG=/var/log/llm-tap/8000.jsonl
```

Then:

```bash
sudo systemctl enable --now llm-tap
```

The service uses the same executable and configuration interface as an interactive invocation.

## Install from source / pip

For development or installation outside the APT repository:

```bash
git clone https://github.com/tecfu/llm-tap.git
cd llm-tap
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

Then run it exactly as shown above:

```bash
llm-tap --upstream http://127.0.0.1:8000 --listen-port 8001
```

## Releases and APT repository

Releases are built by GitHub Actions and published as a signed static APT repository on GitHub Pages. Push a version tag such as `v0.1.1` to publish a release.

The first publication requires an `APT_GPG_PRIVATE_KEY` repository Actions secret containing the ASCII-armored private signing key and GitHub Pages configured to publish the `gh-pages` branch.

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

- `req_ts` = request arrival, `ts` = response completed; `dt` = seconds since the previous record (null for the first).
- `prompt` = last real user message; `context` = the full messages array, with tool calls summarized.
- `tokens` appears when the client sends `stream_options.include_usage`.

## Live output

The daemon also echoes captured traffic in a colorized, greppable format. When running under systemd:

```bash
journalctl -u llm-tap -f
```

- `IN` — input prompt.
- `THINK` — reasoning from the completed response.
- `OUT` — generated result.

The gap between `IN` and `OUT` represents engine latency. A dangling `IN` with no `OUT` means the request is still queued/running or the client aborted.

Ad-hoc analysis reads the JSONL directly with standard tools such as `jq`.

## Notes

- The default log location is `~/.local/state/llm-tap/<engine-port>.jsonl` for normal interactive runs. Systemd deployments should set `TAP_LOG` to `/var/log/llm-tap/<engine-port>.jsonl`.
- Cleartext prompts and answers are written to the log. Protect the log appropriately because anyone with read access can see captured inference traffic.
- Bypass the tap by stopping the service; clients can then target the engine's localhost port directly.
