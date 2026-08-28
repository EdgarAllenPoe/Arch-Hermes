#!/usr/bin/env bash
set -Eeuo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "$root/target-files/usr/local/sbin/arch-ssh-firstboot"

journalctl() { printf '%s\n' 'sshd[123]: Accepted password for root from 192.0.2.10 port 55000 ssh2'; }
who() { :; }
accepted_root_login || { echo "Accepted SSH journal entry was not detected." >&2; exit 1; }

journalctl() { :; }
who() { printf '%s\n' 'root pts/0 2026-08-28 16:00 (192.0.2.10)'; }
accepted_root_login || { echo "Active root pts session was not detected." >&2; exit 1; }

ss() { printf '%s\n' 'LISTEN 0 128 0.0.0.0:22 0.0.0.0:*'; }
port_22_listening || { echo "IPv4 port 22 listener was not detected." >&2; exit 1; }

ss() { printf '%s\n' 'LISTEN 0 128 [::]:22 [::]:*'; }
port_22_listening || { echo "IPv6 port 22 listener was not detected." >&2; exit 1; }

systemctl() { return 0; }
ip() { return 0; }
getent() { return 0; }
curl() { return 0; }
network_ready || { echo "Healthy network stub was rejected." >&2; exit 1; }

echo "[OK] First-boot login and network detection functions passed."
