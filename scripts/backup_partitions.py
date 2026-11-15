#!/usr/bin/env python3
"""Full partition backup via rooted ADB (KernelSU) using binary stdout directly.

Mirrors backup_partitions.sh without requiring Git Bash or unix shell tools,
avoiding PowerShell '>' binary stream corruption on Windows.
Dumps /dev/block/by-name (excluding userdata and whole-disk sdc), deduplicates
shared block device symlinks, captures GPT head/tail for sdc, and verifies
every dumped image against an on-device sha256sum.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys


SKIP_NAMES = {"userdata", "sdc"}
CHUNK_SIZE = 4 * 1024 * 1024


def resolve_adb(explicit: str | None) -> str:
    """Resolve the adb executable path from --adb, ADB env var, or PATH."""
    candidate = explicit or os.environ.get("ADB")
    if candidate:
        return candidate
    found = shutil.which("adb")
    if not found:
        raise FileNotFoundError(
            "adb not found in PATH. Install Android Platform Tools and add it to PATH, or pass --adb <path>."
        )
    return found


def run_adb(adb: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    """Run an adb command and capture raw stdout/stderr bytes."""
    cmd = [adb, *args]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and res.returncode != 0:
        err = res.stderr.decode("utf-8", errors="replace").strip()
        out = res.stdout.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Command failed ({res.returncode}): {' '.join(cmd)}\n{err or out}")
    return res


def check_device_and_root(adb: str) -> None:
    """Verify an authorized device is connected and KernelSU grants root to Shell."""
    state = run_adb(adb, "get-state", check=False)
    state_txt = state.stdout.decode("utf-8", errors="replace").strip()
    if state.returncode != 0 or state_txt != "device":
        err = state.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"No authorized adb device ready (state='{state_txt}', {err}). "
            "Enable USB Debugging, check Motorola USB drivers, and accept the RSA prompt."
        )

    root_res = run_adb(adb, "shell", "su -c id", check=False)
    root_txt = root_res.stdout.decode("utf-8", errors="replace").strip()
    if root_res.returncode != 0 or "uid=0" not in root_txt:
        raise RuntimeError(
            f"ADB shell does not have root access (output='{root_txt}'). "
            "Open KernelSU -> Superuser tab -> enable root for 'Shell'."
        )


def sha256_file(path: Path) -> str:
    """Compute lowercase SHA-256 hex digest using bounded chunk reads."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def pull_block_device(adb: str, shell_cmd: str, dest: Path) -> int:
    """Stream raw bytes via adb exec-out directly into dest opened in binary mode."""
    cmd = [adb, "exec-out", f"su -c '{shell_cmd}'"]
    with dest.open("wb") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"adb exec-out failed for {dest.name}: {err}")
    return dest.stat().st_size


def parse_name_map(raw_text: str) -> list[tuple[str, str]]:
    """Parse '<name> <resolved_dev>' lines returned by the device."""
    pairs: list[tuple[str, str]] = []
    for line in raw_text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            pairs.append((parts[0], parts[1]))
    return pairs


def collect_metadata(adb: str, out_dir: Path) -> list[tuple[str, str]]:
    """Dump partition listings, getprop, and by-name symlink map."""
    by_name = run_adb(adb, "shell", "su -c 'ls -l /dev/block/by-name/'").stdout
    (out_dir / "partitions_by-name.txt").write_bytes(by_name)

    proc_part = run_adb(adb, "shell", "su -c 'cat /proc/partitions'").stdout
    (out_dir / "proc_partitions.txt").write_bytes(proc_part)

    props = run_adb(adb, "shell", "getprop").stdout
    (out_dir / "getprop.txt").write_bytes(props)

    map_cmd = "su -c 'cd /dev/block/by-name; for n in *; do echo \"$n $(readlink -f $n)\"; done'"
    name_map_bytes = run_adb(adb, "shell", map_cmd).stdout.replace(b"\r", b"")
    (out_dir / "name_map.txt").write_bytes(name_map_bytes)
    return parse_name_map(name_map_bytes.decode("utf-8", errors="replace"))


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = repo_root / "backups" / f"stock_{stamp}"

    parser = argparse.ArgumentParser(description="Back up all device partitions via rooted adb.")
    parser.add_argument("output_dir", nargs="?", type=Path, default=default_out,
                        help=f"Directory to store partition dumps (default: {default_out})")
    parser.add_argument("--adb", help="Path to adb executable (default: ADB env var or PATH)")
    args = parser.parse_args()

    try:
        adb = resolve_adb(args.adb)
        check_device_and_root(adb)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {out_dir}")

    pairs = collect_metadata(adb, out_dir)
    seen_devs: dict[str, str] = {}
    log_lines: list[str] = []
    sha_lines: list[str] = []
    failed: list[str] = []

    for name, dev in pairs:
        if name in SKIP_NAMES:
            log_lines.append(f"skip {name}")
            continue
        if dev in seen_devs:
            log_lines.append(f"dup  {name} -> {dev} (same as {seen_devs[dev]})")
            continue
        seen_devs[dev] = name

        dest = out_dir / f"{name}.img"
        print(f"{name:<22} {dev:<26} ", end="", flush=True)
        size = pull_block_device(adb, f"dd if={dev} bs=4M 2>/dev/null", dest)
        local_sum = sha256_file(dest)
        phone_out = run_adb(adb, "shell", f"su -c 'sha256sum {dev}'").stdout
        phone_sum = phone_out.decode("utf-8", errors="replace").strip().split()[0]

        if size > 0 and local_sum == phone_sum:
            print(f"OK   {size}")
            sha_lines.append(f"{local_sum}  {dest.name}")
        else:
            print(f"FAIL {size}")
            failed.append(f"{name} {dev}")

    # GPT of main UFS LUN (first 1 MB + last 1 MB)
    sect_out = run_adb(adb, "shell", "su -c 'blockdev --getsz /dev/block/sdc'").stdout
    sectors = int(sect_out.decode("utf-8", errors="replace").strip())

    gpt_head = out_dir / "gpt_sdc_head_1M.bin"
    pull_block_device(adb, "dd if=/dev/block/sdc bs=1M count=1 2>/dev/null", gpt_head)
    sha_lines.append(f"{sha256_file(gpt_head)}  {gpt_head.name}")

    gpt_tail = out_dir / "gpt_sdc_tail_1M.bin"
    skip_sectors = sectors - 2048
    pull_block_device(adb, f"dd if=/dev/block/sdc bs=512 skip={skip_sectors} count=2048 2>/dev/null", gpt_tail)
    sha_lines.append(f"{sha256_file(gpt_tail)}  {gpt_tail.name}")

    (out_dir / "backup.log").write_text("\n".join(log_lines) + ("\n" if log_lines else ""), encoding="utf-8")
    (out_dir / "SHA256SUMS").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")

    print()
    print(f"Done. Verified {len(sha_lines)} files -> {out_dir}")
    if failed:
        (out_dir / "FAILED").write_text("\n".join(failed) + "\n", encoding="utf-8")
        print("FAILED partitions:", file=sys.stderr)
        for item in failed:
            print(f"  {item}", file=sys.stderr)
        return 1

    for req in ("lk_a.img", "md1img_a.img"):
        p = out_dir / req
        if not p.is_file() or p.stat().st_size == 0:
            print(f"WARNING: expected {req} missing or empty in {out_dir}", file=sys.stderr)
            return 1

    print("All partitions verified (lk_a.img and md1img_a.img ready).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
