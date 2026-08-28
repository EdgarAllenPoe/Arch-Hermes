#!/usr/bin/env bash
set -Eeuo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
installer="$root/arch-ssh-install.sh"
firstboot="$root/target-files/usr/local/sbin/arch-ssh-firstboot"
launcher="$root/overlay/usr/local/sbin/arch-ssh-installer-launch"

for file in "$installer" "$firstboot" "$launcher" "$root/build-iso.sh" "$root/verify-iso.sh"; do
    bash -n "$file"
done

require_text() {
    local text="$1" file="$2"
    grep -Fq -- "$text" "$file" || { echo "Missing required text '$text' in $file" >&2; exit 1; }
}

require_text 'networkmanager' "$installer"
require_text 'openssh' "$installer"
require_text 'systemctl enable NetworkManager.service sshd.service' "$installer"
require_text 'sshd -t' "$installer"
require_text 'journalctl -b -u sshd.service' "$firstboot"
require_text 'Remote root login: CONFIRMED' "$firstboot"
require_text '"/dev/tty1"' "$root/target-files/root/.bash_profile"
require_text 'dns=default' "$root/target-files/etc/NetworkManager/conf.d/10-arch-ssh-bootstrap.conf"
require_text 'rc-manager=file' "$root/target-files/etc/NetworkManager/conf.d/10-arch-ssh-bootstrap.conf"
require_text 'PermitRootLogin yes' "$root/target-files/etc/ssh/sshd_config.d/10-arch-ssh-bootstrap.conf"
require_text 'PasswordAuthentication yes' "$root/target-files/etc/ssh/sshd_config.d/10-arch-ssh-bootstrap.conf"

if grep -RqsE 'hermes-agent|openai-codex|OPENAI_API_KEY' \
    "$installer" "$root/target-files" "$launcher"; then
    echo "Hermes/provider setup must not be part of this installer." >&2
    exit 1
fi

last_chroot="$(grep -n 'arch-chroot ' "$installer" | tail -n1 | cut -d: -f1)"
final_resolver="$(grep -n 'rm -f "\$MOUNTPOINT/etc/resolv.conf"' "$installer" | tail -n1 | cut -d: -f1)"
[[ -n "$last_chroot" && -n "$final_resolver" && "$final_resolver" -gt "$last_chroot" ]] || {
    echo "The final target resolv.conf operation must occur after every arch-chroot call." >&2
    exit 1
}

if grep -Fq 'systemctl enable systemd-resolved' "$installer"; then
    echo "systemd-resolved must not be enabled; NetworkManager owns resolv.conf." >&2
    exit 1
fi

echo "[OK] Static installer invariants passed."
