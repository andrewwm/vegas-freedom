#!/usr/bin/env python3
"""
deploy_network_lock_spoof.py
Automates the complete systemless deployment of the "Network Lock -> Unlocked"
UI spoofing patch on the Motorola Moto G Power 2026 (XT2617V / Android 16).

Requirements:
  - Phone connected via USB with USB Debugging enabled.
  - Root access via Magisk (su working over ADB).
  - Python 3.10+ on PC.
"""

import os
import sys
import shutil
import sqlite3
import tempfile
import urllib.request
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
XPOSED_DIR = os.path.join(REPO_ROOT, "xposed")
MODULE_APK = os.path.join(XPOSED_DIR, "SpoofNetworkLock.apk")

ZYGISK_NEXT_URL = "https://github.com/Dr-TSNG/ZygiskNext/releases/download/v1.5.3/Zygisk-Next-1.5.3-880-22a1bf5-release.zip"
VECTOR_URL = "https://github.com/JingMatrix/Vector/releases/download/v2.2/Vector-v2.2-3080-Release.zip"

def run_adb(args, check=True):
    cmd = ["adb"] + args
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"ADB command failed: {' '.join(cmd)}\n{res.stderr.strip()}")
    return res.stdout.strip()

def run_adb_su(cmd_str, check=True):
    # Pass command via su stdin to avoid shell quote mangling across OSes
    proc = subprocess.Popen(["adb", "shell", "su"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = proc.communicate(input=cmd_str + "\nexit\n")
    if check and proc.returncode != 0:
        raise RuntimeError(f"ADB su command failed: {cmd_str}\n{stderr.strip()}")
    return stdout.strip()

def download_file(url, target_path):
    print(f"[*] Downloading: {url} -> {target_path}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp, open(target_path, "wb") as f:
        shutil.copyfileobj(resp, f)

def main():
    print("==================================================")
    print(" Moto G Power 2026 - Network Lock Spoof Deployer ")
    print("==================================================")

    if not shutil.which("adb"):
        print("[!] Error: 'adb' not found on PATH. Please install Android Platform Tools.")
        return 1

    if not os.path.isfile(MODULE_APK):
        print(f"[!] Error: {MODULE_APK} not found.")
        print("    Run 'python xposed/build_module.py' first.")
        return 1

    # 1. Verify ADB connection
    print("[*] Checking device connection...")
    devices_out = run_adb(["devices"])
    lines = [line.strip() for line in devices_out.splitlines() if line.strip() and not line.startswith("List of")]
    if not lines or "device" not in lines[0]:
        print(f"[!] No authorized device detected. ADB output:\n{devices_out}")
        print("    Ensure USB debugging is enabled and your device is unlocked.")
        return 1
    print(f"[+] Device connected: {lines[0]}")

    # 2. Verify Root access
    print("[*] Checking root access...")
    try:
        id_out = run_adb_su("id")
        if "uid=0(root)" not in id_out:
            print(f"[!] Root check failed. Output: {id_out}")
            return 1
    except Exception as e:
        print(f"[!] Root access error: {e}")
        return 1
    print("[+] Root verified (uid=0).")

    # 3. Check and install Zygisk Next & Vector Magisk modules
    installed_modules = run_adb_su("ls /data/adb/modules 2>/dev/null || true", check=False)
    needs_reboot = False
    cache_dir = os.path.join(REPO_ROOT, "work", "downloads")
    os.makedirs(cache_dir, exist_ok=True)

    # Check Zygisk Next
    if "zygisksu" not in installed_modules:
        print("[*] Zygisk Next not found in Magisk modules. Installing...")
        zn_zip = os.path.join(cache_dir, "ZygiskNext.zip")
        if not os.path.isfile(zn_zip):
            download_file(ZYGISK_NEXT_URL, zn_zip)
        run_adb(["push", zn_zip, "/data/local/tmp/ZygiskNext.zip"])
        run_adb_su("magisk --install-module /data/local/tmp/ZygiskNext.zip")
        needs_reboot = True
        print("[+] Zygisk Next installed.")
    else:
        print("[+] Zygisk Next is already installed.")

    # Check Vector
    if "zygisk_vector" not in installed_modules:
        print("[*] Vector (Xposed) not found in Magisk modules. Installing...")
        vector_zip = os.path.join(cache_dir, "Vector.zip")
        if not os.path.isfile(vector_zip):
            download_file(VECTOR_URL, vector_zip)
        run_adb(["push", vector_zip, "/data/local/tmp/Vector.zip"])
        run_adb_su("magisk --install-module /data/local/tmp/Vector.zip")
        needs_reboot = True
        print("[+] Vector framework installed.")
    else:
        print("[+] Vector framework is already installed.")

    # 4. Install SpoofNetworkLock headless APK
    print("[*] Installing SpoofNetworkLock APK...")
    run_adb(["push", MODULE_APK, "/data/local/tmp/SpoofNetworkLock.apk"])
    run_adb_su("pm install -r -d -g --bypass-low-target-sdk-block /data/local/tmp/SpoofNetworkLock.apk")
    apk_path_out = run_adb_su("pm path com.example.spoofnetworklock")
    if not apk_path_out.startswith("package:"):
        print(f"[!] Failed to get installed APK path: {apk_path_out}")
        return 1
    device_apk_path = apk_path_out.replace("package:", "").strip()
    print(f"[+] SpoofNetworkLock installed at: {device_apk_path}")

    # 5. Provision Vector configuration database
    print("[*] Provisioning Vector modules_config.db...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "modules_config.db")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS modules (
            mid integer PRIMARY KEY AUTOINCREMENT,
            module_pkg_name text NOT NULL UNIQUE,
            apk_path text NOT NULL,
            enabled BOOLEAN DEFAULT 0 CHECK (enabled IN (0, 1)),
            auto_include BOOLEAN DEFAULT 0 CHECK (auto_include IN (0, 1))
        );
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS scope (
            mid integer,
            app_pkg_name text NOT NULL,
            user_id integer NOT NULL,
            PRIMARY KEY (mid, app_pkg_name, user_id),
            CONSTRAINT scope_module_constraint FOREIGN KEY (mid) REFERENCES modules (mid) ON DELETE CASCADE
        );
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS configs (
            module_pkg_name text NOT NULL,
            user_id integer NOT NULL,
            `group` text NOT NULL,
            `key` text NOT NULL,
            data blob NOT NULL,
            PRIMARY KEY (module_pkg_name, user_id, `group`, `key`),
            CONSTRAINT config_module_constraint FOREIGN KEY (module_pkg_name) REFERENCES modules (module_pkg_name) ON DELETE CASCADE
        );
        """)
        c.execute("CREATE INDEX IF NOT EXISTS configs_idx ON configs (module_pkg_name, user_id);")
        c.execute("PRAGMA user_version = 4;")

        # Insert required internal lspd entry
        c.execute(
            "INSERT OR IGNORE INTO modules (module_pkg_name, apk_path, enabled, auto_include) VALUES ('lspd', '/data/adb/modules/zygisk_vector/manager.apk', 1, 0);"
        )

        # Insert SpoofNetworkLock module
        c.execute(
            "INSERT OR REPLACE INTO modules (module_pkg_name, apk_path, enabled, auto_include) VALUES (?, ?, 1, 0);",
            ("com.example.spoofnetworklock", device_apk_path)
        )
        c.execute("SELECT mid FROM modules WHERE module_pkg_name = 'com.example.spoofnetworklock';")
        mid = c.fetchone()[0]

        # Add target scopes
        c.execute("INSERT OR REPLACE INTO scope (mid, app_pkg_name, user_id) VALUES (?, 'com.android.settings', 0);", (mid,))
        c.execute("INSERT OR REPLACE INTO scope (mid, app_pkg_name, user_id) VALUES (?, 'com.motorola.carriersettingsext', 0);", (mid,))
        c.execute("INSERT OR REPLACE INTO scope (mid, app_pkg_name, user_id) VALUES (?, 'system', 0);", (mid,))

        conn.commit()
        conn.close()

        run_adb(["push", db_path, "/data/local/tmp/modules_config.db"])
        run_adb_su("""
        mkdir -p /data/adb/lspd/config
        rm -f /data/adb/lspd/config/modules_config.db-wal /data/adb/lspd/config/modules_config.db-shm
        cp /data/local/tmp/modules_config.db /data/adb/lspd/config/modules_config.db
        chmod 600 /data/adb/lspd/config/modules_config.db
        chown -R root:root /data/adb/lspd
        """)
    print("[+] Vector database configured and provisioned.")

    # 6. Apply service.sh Magisk busybox unshare patch
    print("[*] Patching Vector service.sh for bootloader namespace isolation...")
    run_adb_su("""
    cat << "EOF" > /data/adb/modules/zygisk_vector/service.sh
#!/system/bin/sh
MODDIR="${0%/*}"
cd "$MODDIR" || exit 1
export PATH="/data/adb/magisk:$(magisk --path 2>/dev/null):$PATH"
if [ -x /data/adb/magisk/busybox ]; then
    /data/adb/magisk/busybox unshare --propagation slave -m "$MODDIR/daemon" --system-server-max-retry=3 "$@" &
else
    unshare --propagation slave -m "$MODDIR/daemon" --system-server-max-retry=3 "$@" &
fi
EOF
    chmod 755 /data/adb/modules/zygisk_vector/service.sh
    """)
    print("[+] Vector service.sh patched.")

    # 7. Clean up scratch files
    run_adb_su("rm -f /data/local/tmp/SpoofNetworkLock.apk /data/local/tmp/modules_config.db /data/local/tmp/ZygiskNext.zip /data/local/tmp/Vector.zip")

    # 8. Check if reboot is required
    if needs_reboot:
        print("\n[!] Fresh Magisk modules were installed. A device reboot is required.")
        ans = input("[?] Would you like to reboot the device now? [Y/n]: ").strip().lower()
        if ans in ("", "y", "yes"):
            print("[*] Rebooting device...")
            run_adb(["reboot"])
            print("[+] Device rebooting. After unlock, Settings > About phone > Network lock will show 'Unlocked'.")
            return 0
        else:
            print("[*] Please reboot your phone manually to activate the framework.")
            return 0

    # If framework was already active, restart target packages and verify
    print("[*] Refreshing target applications...")
    run_adb_su("""
    am force-stop com.android.settings
    am force-stop com.motorola.carriersettingsext
    """)

    print("[*] Testing live summary query...")
    summary_out = run_adb_su("content call --uri content://com.motorola.carriersettingsext.unlock.networkunlockpreference/summary --method summary")
    print(f"    Provider output: {summary_out}")

    if "com.android.settings.summary=Unlocked" in summary_out:
        print("\n[✔] SUCCESS: 'Network lock' successfully spoofed to 'Unlocked'!")
        print("    Open Settings > About phone to confirm.")
    else:
        print("\n[!] Provider did not return Unlocked immediately. A reboot is recommended to refresh ART hooks.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
