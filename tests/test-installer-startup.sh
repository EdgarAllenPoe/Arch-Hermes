#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

INSTALLER="${1:-hermes-install.sh}"
[[ -f "$INSTALLER" ]] || { echo "Missing installer: $INSTALLER" >&2; exit 1; }

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

{
    cat <<'PRELUDE'
set -Eeuo pipefail
LIVE_BOOT_DISK=""
info() { :; }
warn() { :; }
findmnt() { return 1; }
readlink() { return 1; }
lsblk() { return 1; }
blkid() { return 1; }
losetup() { return 1; }
PRELUDE

    sed -n '/^parent_disk_for_device() {/,/^}/p' "$INSTALLER"
    sed -n '/^detect_live_boot_disk() {/,/^}/p' "$INSTALLER"

    cat <<'TEST'
detect_live_boot_disk
[[ -z "$LIVE_BOOT_DISK" ]]
TEST
} > "$tmp"

bash "$tmp"
echo "[OK] live installer disk detection is nonfatal when no source can be resolved."
