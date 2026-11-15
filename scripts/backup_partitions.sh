#!/usr/bin/env bash
# Full partition backup for Moto G Power 2026 (XT2617V / vegas) via rooted adb (KernelSU).
# Usage: bash scripts/backup_partitions.sh [output_dir]
# Skips userdata and whole-disk nodes; dumps sda/sdb (UFS boot LUNs) and the GPT of sdc.
# Verifies every image against a sha256 computed on the phone.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ADB="${ADB:-adb}"
OUT="${1:-$REPO_ROOT/backups/stock_$(date +%Y%m%d_%H%M%S)}"

if ! command -v "$ADB" >/dev/null 2>&1; then
  echo "ERROR: adb not found in PATH. Install Platform Tools or set ADB=/path/to/adb." >&2
  exit 1
fi

STATE="$("$ADB" get-state 2>/dev/null | tr -d '\r')"
if [[ "$STATE" != "device" ]]; then
  echo "ERROR: No authorized adb device ready (state='$STATE'). Enable USB debugging and authorize PC." >&2
  exit 1
fi

if ! "$ADB" shell "su -c id" 2>/dev/null | grep -q "uid=0"; then
  echo "ERROR: adb shell is not rooted. Open KernelSU -> Superuser -> enable root for Shell." >&2
  exit 1
fi

mkdir -p "$OUT"
cd "$OUT" || exit 1

SKIP_RE='^(userdata|sdc)$'   # userdata = user files; sdc = whole 128GB disk
LOG="$OUT/backup.log"
: > "$LOG"
: > SHA256SUMS
: > FAILED

# Metadata
"$ADB" shell "su -c 'ls -l /dev/block/by-name/'" > partitions_by-name.txt
"$ADB" shell "su -c 'cat /proc/partitions'" > proc_partitions.txt
"$ADB" shell getprop > getprop.txt

# name -> real device, deduped by real device
"$ADB" shell "su -c 'cd /dev/block/by-name; for n in *; do echo \"\$n \$(readlink -f \$n)\"; done'" | tr -d '\r' > name_map.txt

declare -A seen
while read -r name dev <&3; do
  [[ -z "$name" ]] && continue
  [[ "$name" =~ $SKIP_RE ]] && { echo "skip $name" >> "$LOG"; continue; }
  if [[ -n "${seen[$dev]:-}" ]]; then
    echo "dup  $name -> $dev (same as ${seen[$dev]})" >> "$LOG"; continue
  fi
  seen[$dev]=$name
  printf '%-22s %-26s ' "$name" "$dev"
  "$ADB" exec-out "su -c 'dd if=$dev bs=4M 2>/dev/null'" > "$name.img"
  local_sum=$(sha256sum "$name.img" | cut -d' ' -f1)
  phone_sum=$("$ADB" shell "su -c 'sha256sum $dev'" | tr -d '\r' | cut -d' ' -f1)
  size=$(stat -c %s "$name.img")
  if [[ "$local_sum" == "$phone_sum" && "$size" -gt 0 ]]; then
    echo "OK   $size"
    echo "$local_sum  $name.img" >> SHA256SUMS
  else
    echo "FAIL $size"
    echo "$name $dev" >> FAILED
  fi
done 3< name_map.txt

# GPT of main LUN (primary header+entries in first 1MB; backup in last 1MB)
SECT=$("$ADB" shell "su -c 'blockdev --getsz /dev/block/sdc'" | tr -d '\r')   # 512-byte units
"$ADB" exec-out "su -c 'dd if=/dev/block/sdc bs=1M count=1 2>/dev/null'" > gpt_sdc_head_1M.bin
"$ADB" exec-out "su -c 'dd if=/dev/block/sdc bs=512 skip=$((SECT-2048)) count=2048 2>/dev/null'" > gpt_sdc_tail_1M.bin
sha256sum gpt_sdc_*.bin >> SHA256SUMS

echo
echo "Done. Output: $OUT"
if [[ -s FAILED ]]; then
  echo "FAILED partitions:" >&2
  cat FAILED >&2
  exit 1
else
  echo "All partitions verified."
  rm -f FAILED
fi
