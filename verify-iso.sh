#!/usr/bin/env bash
# Verify the completed ISO contains the Wi-Fi/SSH installer and all target files.
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ISO="${1:-}"
if [[ -z "$ISO" ]]; then
    ISO="$(find "$SCRIPT_DIR/out" -maxdepth 1 -type f -name '*.iso' -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr | head -n1 | cut -d' ' -f2-)"
fi
[[ -n "$ISO" && -f "$ISO" ]] || { echo "Usage: $(basename "$0") /path/to/image.iso" >&2; exit 2; }

command -v bsdtar >/dev/null 2>&1 || { echo "bsdtar is required." >&2; exit 1; }
command -v unsquashfs >/dev/null 2>&1 || { echo "unsquashfs is required." >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

sfs_path="$(bsdtar -tf "$ISO" | grep -E '(^|/)x86_64/airootfs\.sfs$' | head -n1 || true)"
[[ -n "$sfs_path" ]] || { echo "Could not find x86_64/airootfs.sfs inside $ISO" >&2; exit 1; }

bsdtar -xOf "$ISO" "$sfs_path" > "$tmp/airootfs.sfs"
mkdir -p "$tmp/root"
unsquashfs -f -d "$tmp/root" "$tmp/airootfs.sfs" \
    usr/local/bin/arch-ssh-install \
    usr/local/sbin/arch-ssh-installer-launch \
    usr/local/share/arch-ssh-bootstrap/target-files \
    etc/NetworkManager/conf.d/10-arch-ssh-bootstrap.conf \
    etc/systemd/system/arch-ssh-installer.service \
    etc/systemd/system/multi-user.target.wants/arch-ssh-installer.service \
    etc/systemd/system/multi-user.target.wants/NetworkManager.service \
    etc/systemd/system/getty@tty1.service >/dev/null

installer="$tmp/root/usr/local/bin/arch-ssh-install"
launcher="$tmp/root/usr/local/sbin/arch-ssh-installer-launch"
share="$tmp/root/usr/local/share/arch-ssh-bootstrap/target-files"

[[ -x "$installer" ]] || { echo "Embedded installer missing or not executable." >&2; exit 1; }
[[ -x "$launcher" ]] || { echo "Embedded launcher missing or not executable." >&2; exit 1; }
[[ -x "$share/usr/local/sbin/arch-ssh-firstboot" ]] || { echo "First-boot verifier missing." >&2; exit 1; }
[[ -f "$share/etc/ssh/sshd_config.d/10-arch-ssh-bootstrap.conf" ]] || { echo "SSH config missing." >&2; exit 1; }
[[ -f "$share/etc/NetworkManager/conf.d/10-arch-ssh-bootstrap.conf" ]] || { echo "NetworkManager config missing." >&2; exit 1; }
[[ -f "$share/root/.bash_profile" ]] || { echo "Root first-login hook missing." >&2; exit 1; }

[[ -L "$tmp/root/etc/systemd/system/multi-user.target.wants/arch-ssh-installer.service" ]] \
    || { echo "Installer service is not enabled." >&2; exit 1; }
[[ "$(readlink "$tmp/root/etc/systemd/system/multi-user.target.wants/arch-ssh-installer.service")" == "../arch-ssh-installer.service" ]] \
    || { echo "Installer-service symlink target is unexpected." >&2; exit 1; }
[[ -L "$tmp/root/etc/systemd/system/multi-user.target.wants/NetworkManager.service" ]] \
    || { echo "Live NetworkManager service is not enabled." >&2; exit 1; }
[[ -L "$tmp/root/etc/systemd/system/getty@tty1.service" ]] \
    || { echo "tty1 getty is not masked." >&2; exit 1; }
[[ "$(readlink "$tmp/root/etc/systemd/system/getty@tty1.service")" == "/dev/null" ]] \
    || { echo "tty1 getty mask target is unexpected." >&2; exit 1; }

bash -n "$installer"
bash -n "$launcher"
bash -n "$share/usr/local/sbin/arch-ssh-firstboot"

grep -Fq 'networkmanager' "$installer" || { echo "Installer does not install NetworkManager." >&2; exit 1; }
grep -Fq 'openssh' "$installer" || { echo "Installer does not install OpenSSH." >&2; exit 1; }
grep -Fq 'PermitRootLogin yes' "$share/etc/ssh/sshd_config.d/10-arch-ssh-bootstrap.conf" \
    || { echo "Root SSH bootstrap setting missing." >&2; exit 1; }
grep -Fq 'PasswordAuthentication yes' "$share/etc/ssh/sshd_config.d/10-arch-ssh-bootstrap.conf" \
    || { echo "Password SSH bootstrap setting missing." >&2; exit 1; }
grep -Fq 'rc-manager=file' "$share/etc/NetworkManager/conf.d/10-arch-ssh-bootstrap.conf" \
    || { echo "Deterministic resolv.conf management setting missing." >&2; exit 1; }

if grep -RqsE 'hermes-agent|openai-codex|OPENAI_API_KEY' "$installer" "$share"; then
    echo "Hermes/provider setup leaked into the minimal Arch/SSH installer." >&2
    exit 1
fi

echo "[OK] ISO verification passed: $ISO"
echo "     Installer, NetworkManager, OpenSSH, first-boot verifier, and tty1 autostart are embedded."
