#!/usr/bin/env bash
set -euo pipefail

: "${VERSION:?VERSION is required}"
: "${CODENAME:?CODENAME is required}"
: "${ARCH:?ARCH is required}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${ROOT}/build/deb"
STAGE="${BUILD_DIR}/stage"
PACKAGE="${BUILD_DIR}/llm-tap_${VERSION}_${ARCH}.deb"

rm -rf "${BUILD_DIR}"
mkdir -p "${STAGE}/DEBIAN" "${STAGE}/opt/llm-tap" \
  "${STAGE}/usr/bin" "${STAGE}/lib/systemd/system"

python3 -m venv --copies "${STAGE}/opt/llm-tap/venv"
"${STAGE}/opt/llm-tap/venv/bin/python" -m pip install --upgrade pip
"${STAGE}/opt/llm-tap/venv/bin/pip" install --no-cache-dir "${ROOT}"

cat > "${STAGE}/usr/bin/llm-tap" <<'EOF'
#!/bin/sh
exec /opt/llm-tap/venv/bin/llm-tap "$@"
EOF
chmod 0755 "${STAGE}/usr/bin/llm-tap"

install -m 0644 "${ROOT}/packaging/llm-tap.service" \
  "${STAGE}/lib/systemd/system/llm-tap.service"

cat > "${STAGE}/DEBIAN/control" <<EOF
Package: llm-tap
Version: ${VERSION}
Section: net
Priority: optional
Architecture: ${ARCH}
Maintainer: Tec Fu <help@tecfu.com>
Depends: python3 (>= 3.10), adduser
Description: OpenAI-compatible inference traffic capture tap
 mitmproxy-based reverse proxy that captures OpenAI-compatible inference
 requests and completions as JSONL while streaming responses unchanged.
 .
 This package includes its Python runtime dependencies and a systemd unit.
EOF

cat > "${STAGE}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e

if ! getent group llm-tap >/dev/null; then
    addgroup --system llm-tap >/dev/null
fi
if ! id llm-tap >/dev/null 2>&1; then
    adduser --system --ingroup llm-tap --no-create-home \
      --home /nonexistent --shell /usr/sbin/nologin llm-tap >/dev/null
fi
install -d -o llm-tap -g llm-tap -m 0750 /var/log/llm-tap

if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload || true
fi
exit 0
EOF
chmod 0755 "${STAGE}/DEBIAN/postinst"

cat > "${STAGE}/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e

if [ "$1" = remove ] || [ "$1" = deconfigure ]; then
    if command -v systemctl >/dev/null 2>&1; then
        systemctl stop llm-tap.service >/dev/null 2>&1 || true
    fi
fi
exit 0
EOF
chmod 0755 "${STAGE}/DEBIAN/prerm"

cat > "${STAGE}/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e

if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload || true
fi

if [ "$1" = purge ]; then
    deluser --system llm-tap >/dev/null 2>&1 || true
    delgroup --system llm-tap >/dev/null 2>&1 || true
fi
exit 0
EOF
chmod 0755 "${STAGE}/DEBIAN/postrm"

dpkg-deb --build --root-owner-group "${STAGE}" "${PACKAGE}" >/dev/null
printf '%s\n' "${PACKAGE}"
