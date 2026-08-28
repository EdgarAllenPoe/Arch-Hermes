#!/usr/bin/env bash
# Build a disposable Arch root and prove that its configured sshd accepts a
# real remote root password login. This does not simulate Wi-Fi radio hardware.
set -Eeuo pipefail
IFS=$'\n\t'

[[ $(id -u) -eq 0 ]] || { echo "Run as root." >&2; exit 1; }
for cmd in arch-chroot pacstrap sshpass sshd; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "Missing command: $cmd" >&2; exit 1; }
done

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
target="$work/root"
port=$((22000 + RANDOM % 1000))
sshd_pid=""

cleanup() {
    set +e
    [[ -n "$sshd_pid" ]] && kill "$sshd_pid" 2>/dev/null || true
    [[ -n "$sshd_pid" ]] && wait "$sshd_pid" 2>/dev/null || true
    mountpoint -q "$target" 2>/dev/null && umount -R "$target" 2>/dev/null || true
    rm -rf "$work" 2>/dev/null || true
}
trap cleanup EXIT

mkdir -p "$target"

pacstrap -K "$target" base networkmanager openssh curl ca-certificates >/dev/null

install -Dm644 "$repo/target-files/etc/NetworkManager/conf.d/10-arch-ssh-bootstrap.conf" \
    "$target/etc/NetworkManager/conf.d/10-arch-ssh-bootstrap.conf"
install -Dm644 "$repo/target-files/etc/ssh/sshd_config.d/10-arch-ssh-bootstrap.conf" \
    "$target/etc/ssh/sshd_config.d/10-arch-ssh-bootstrap.conf"
install -Dm755 "$repo/target-files/usr/local/sbin/arch-ssh-firstboot" \
    "$target/usr/local/sbin/arch-ssh-firstboot"
install -Dm600 "$repo/target-files/root/.bash_profile" "$target/root/.bash_profile"

printf 'root:%s\n' 'TestRootPass123!' | arch-chroot "$target" chpasswd
arch-chroot "$target" ssh-keygen -A >/dev/null
arch-chroot "$target" systemctl enable NetworkManager.service sshd.service >/dev/null
mkdir -p /run/sshd "$target/run/sshd"
arch-chroot "$target" sshd -t

ssh_effective="$(arch-chroot "$target" sshd -T -C user=root,host=localhost,addr=127.0.0.1)"
printf '%s\n' "$ssh_effective" \
    | grep -iE '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication|usepam) ' >&2 || true
grep -iqx 'permitrootlogin yes' <<< "$ssh_effective" || { echo "Effective sshd policy does not permit root login." >&2; exit 1; }
grep -iqx 'passwordauthentication yes' <<< "$ssh_effective" || { echo "Effective sshd policy does not allow password authentication." >&2; exit 1; }

arch-chroot "$target" /bin/bash -c \
    'install -d -m 0755 /run/sshd; exec /usr/bin/sshd -D -e -p "$1" -o ListenAddress=127.0.0.1' \
    bash "$port" >"$work/sshd.log" 2>&1 &
sshd_pid=$!

for _ in {1..30}; do
    ss -H -ltn 2>/dev/null | grep -Eq "127\\.0\\.0\\.1:$port([[:space:]]|$)" && break
    sleep 1
done
ss -H -ltn 2>/dev/null | grep -Eq "127\\.0\\.0\\.1:$port([[:space:]]|$)" || {
    cat "$work/sshd.log" >&2
    echo "Disposable target sshd did not listen." >&2
    exit 1
}

result="$(sshpass -p 'TestRootPass123!' ssh -4 -p "$port" \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o PreferredAuthentications=password -o PubkeyAuthentication=no \
    root@127.0.0.1 'printf SSH_LOGIN_OK')"
[[ "$result" == "SSH_LOGIN_OK" ]] || { echo "Real SSH login test failed: $result" >&2; exit 1; }

[[ -L "$target/etc/systemd/system/multi-user.target.wants/NetworkManager.service" ]]
[[ -L "$target/etc/systemd/system/multi-user.target.wants/sshd.service" ]]

echo "[OK] Disposable Arch target accepted a real root password SSH login."
