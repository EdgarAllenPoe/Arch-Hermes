#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OUT="$ROOT/arch-ssh-install.sh"
EXPECTED_FILE="$ROOT/installer.sha256"

mapfile -t parts < <(find "$ROOT/installer-parts" -maxdepth 1 -type f -name 'part-*' | sort)
(( ${#parts[@]} > 0 )) || { echo "No installer parts found." >&2; exit 1; }

cat "${parts[@]}" > "$OUT"
chmod 755 "$OUT"
bash -n "$OUT"

expected="$(awk 'NR == 1 {print $1}' "$EXPECTED_FILE")"
actual="$(sha256sum "$OUT" | awk '{print $1}')"
if [[ -z "$expected" || "$actual" != "$expected" ]]; then
    echo "Installer assembly checksum FAILED." >&2
    echo "Expected: $expected" >&2
    echo "Actual:   $actual" >&2
    exit 1
fi

echo "[OK] Assembled arch-ssh-install.sh ($actual)"
