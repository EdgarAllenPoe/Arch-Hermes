#!/usr/bin/env bash
# UEFI-boot the completed ISO under QEMU and require the live installer service
# to reach its launcher. The VM has no Wi-Fi radio, so this intentionally stops
# after proving boot + systemd autostart, before interactive Wi-Fi setup.
set -Eeuo pipefail

iso="${1:-}"
[[ -n "$iso" && -f "$iso" ]] || { echo "Usage: $0 /path/to/image.iso" >&2; exit 2; }
command -v qemu-system-x86_64 >/dev/null 2>&1 || { echo "qemu-system-x86_64 is required." >&2; exit 1; }

ovmf="$(find /usr/share/edk2 -type f \( -name 'OVMF_CODE.4m.fd' -o -name 'OVMF_CODE.fd' \) 2>/dev/null | head -n1 || true)"
[[ -n "$ovmf" ]] || { echo "OVMF firmware was not found." >&2; exit 1; }

log="$(mktemp)"
trap 'rm -f "$log"' EXIT

set +e
timeout 150 qemu-system-x86_64 \
    -accel tcg \
    -machine q35 \
    -m 2048 \
    -smp 2 \
    -nographic \
    -monitor none \
    -no-reboot \
    -boot order=d \
    -drive if=pflash,format=raw,readonly=on,file="$ovmf" \
    -cdrom "$iso" \
    >"$log" 2>&1
rc=$?
set -e

if ! grep -Fq 'ARCH_SSH_INSTALLER_READY' "$log"; then
    tail -n 200 "$log" >&2 || true
    echo "ISO boot smoke test did not reach the installer launcher (QEMU exit $rc)." >&2
    exit 1
fi

echo "[OK] UEFI QEMU boot reached the live installer launcher."
