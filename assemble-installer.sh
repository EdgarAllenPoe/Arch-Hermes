#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PARTS_DIR="$SCRIPT_DIR/installer-parts"
OUT="$SCRIPT_DIR/hermes-install.sh"
EXPECTED_FILE="$SCRIPT_DIR/installer.sha256"

[[ -d "$PARTS_DIR" ]] || { echo "Missing $PARTS_DIR" >&2; exit 1; }
[[ -f "$EXPECTED_FILE" ]] || { echo "Missing $EXPECTED_FILE" >&2; exit 1; }
mapfile -t parts < <(find "$PARTS_DIR" -maxdepth 1 -type f -name 'part-*' -print | sort)
(( ${#parts[@]} > 0 )) || { echo "No installer parts found." >&2; exit 1; }

cat "${parts[@]}" > "$OUT"
chmod 755 "$OUT"

expected="$(awk '{print $1}' "$EXPECTED_FILE")"
actual="$(sha256sum "$OUT" | awk '{print $1}')"
if [[ "$actual" != "$expected" ]]; then
  echo "Installer assembly checksum FAILED." >&2
  echo "Expected: $expected" >&2
  echo "Actual:   $actual" >&2
  rm -f "$OUT"
  exit 1
fi

bash -n "$OUT"
echo "[OK] hermes-install.sh assembled and verified: $actual"
