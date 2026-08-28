#!/usr/bin/env bash
set -Eeuo pipefail

installer="${1:-hermes-install.sh}"
[[ -f "$installer" ]] || { echo "Missing installer: $installer" >&2; exit 1; }

require_line() {
    local expected="$1"
    grep -F -- "$expected" "$installer" >/dev/null || {
        echo "Missing required Hermes bootstrap line:" >&2
        echo "  $expected" >&2
        exit 1
    }
}

require_line 'local installer_rel="/root/hermes-agent-install.sh"'
require_line 'curl -fsSL "$HERMES_INSTALL_URL" -o "$MOUNTPOINT$installer_rel"'
require_line 'arch-chroot "$MOUNTPOINT" /bin/bash "$installer_rel" \\'
require_line 'rm -f "$MOUNTPOINT$installer_rel"'

if grep -F -- '$MOUNTPOINT/tmp/hermes-agent-install.sh' "$installer" >/dev/null; then
    echo "Hermes bootstrap must not be staged under target /tmp; arch-chroot hides it." >&2
    exit 1
fi

if grep -F -- "'/tmp/hermes-agent-install.sh" "$installer" >/dev/null; then
    echo "Hermes bootstrap must not be invoked from /tmp inside arch-chroot." >&2
    exit 1
fi

echo "[OK] Hermes bootstrap is staged outside arch-chroot's private /tmp."
