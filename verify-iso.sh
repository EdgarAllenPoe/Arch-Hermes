#!/usr/bin/env bash
# Verify that the built ISO contains the custom Hermes installer and autostart wiring.
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ISO="${1:-}"
if [[ -z "$ISO" ]]; then
    ISO="$(find "$SCRIPT_DIR/out" -maxdepth 1 -type f -name '*.iso' -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr | head -n1 | cut -d' ' -f2-)"
fi
[[ -n "$ISO" && -f "$ISO" ]] || { echo "Usage: $(basename "$0") /path/to/image.iso" >&2; exit 2; }

command -v bsdtar >/dev/null 2>&1 || { echo "bsdtar is required (libarchive)." >&2; exit 1; }
command -v unsquashfs >/dev/null 2>&1 || { echo "unsquashfs is required (squashfs-tools)." >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

sfs_path="$(bsdtar -tf "$ISO" | grep -E '(^|/)x86_64/airootfs\.sfs$' | head -n1 || true)"
[[ -n "$sfs_path" ]] || { echo "Could not find x86_64/airootfs.sfs inside $ISO" >&2; exit 1; }

bsdtar -xOf "$ISO" "$sfs_path" > "$tmp/airootfs.sfs"
mkdir -p "$tmp/root"
unsquashfs -f -d "$tmp/root" "$tmp/airootfs.sfs" \
    usr/local/bin/hermes-install \
    usr/local/sbin/hermes-installer-launch \
    etc/systemd/system/hermes-installer.service \
    etc/systemd/system/multi-user.target.wants/hermes-installer.service \
    etc/systemd/system/getty@tty1.service >/dev/null

[[ -x "$tmp/root/usr/local/bin/hermes-install" ]] || { echo "Embedded hermes-install is missing or not executable." >&2; exit 1; }
[[ -x "$tmp/root/usr/local/sbin/hermes-installer-launch" ]] || { echo "Embedded launcher is missing or not executable." >&2; exit 1; }
[[ -f "$tmp/root/etc/systemd/system/hermes-installer.service" ]] || { echo "Installer service is missing." >&2; exit 1; }
[[ -L "$tmp/root/etc/systemd/system/multi-user.target.wants/hermes-installer.service" ]] \
    || { echo "Installer service is not enabled." >&2; exit 1; }
[[ "$(readlink "$tmp/root/etc/systemd/system/multi-user.target.wants/hermes-installer.service")" == "../hermes-installer.service" ]] \
    || { echo "Installer service symlink target is unexpected." >&2; exit 1; }
[[ -L "$tmp/root/etc/systemd/system/getty@tty1.service" ]] \
    || { echo "tty1 getty is not masked." >&2; exit 1; }
[[ "$(readlink "$tmp/root/etc/systemd/system/getty@tty1.service")" == "/dev/null" ]] \
    || { echo "tty1 getty mask has unexpected target." >&2; exit 1; }

bash -n "$tmp/root/usr/local/bin/hermes-install"
bash -n "$tmp/root/usr/local/sbin/hermes-installer-launch"

echo "[OK] ISO verification passed: $ISO"
echo "     Embedded installer, launcher, autostart service, and tty1 ownership are correct."
