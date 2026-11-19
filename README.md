# vegas-freedom-xposed

Comprehensive bootloader unlock, cellular SIM/modem unlock, and systemless "Network lock" UI spoofing toolchain for the **Motorola Moto G Power 2026 (`XT2617V` / `vegas`)**.

---

## Overview

This repository provides an all-in-one suite to liberate the Tracfone / Straight Talk variant of the Motorola Moto G Power 2026 across three core layers:

1. **Bootloader Unlock (`bootloader/`):** Dynamically disassembles, patches, and CERT-signs the Little Kernel (`lk`) bootloader image, and generates 20-character OEM unlock keys via the Val protocol.
2. **Cellular SIM / Carrier Unlock (`modem/`):** Patches verified microMIPS32 instruction offsets inside the MT6835 baseband firmware (`md1img_a`) to bypass subsidy and network lock checks, re-signing the image with CERT2 keys for Fastboot flashing.
3. **Systemless "Network lock" UI Spoofing (`xposed/` & `scripts/`):** Deploys a headless Xposed module (`SpoofNetworkLock`) running atop Zygisk Next and Vector to intercept IPC ContentProvider queries and preference summaries in memory. This permanently displays **"Unlocked"** under **Settings > About phone > Network lock** without modifying `/system` or breaking Android 16 platform signature verification.

---

## Table of Contents

- [Supported Device and Firmware Baseline](#supported-device-and-firmware-baseline)
- [Workflow and Root Lifecycle Overview](#workflow-and-root-lifecycle-overview)
- [Safety Warnings and Disclaimers](#safety-warnings-and-disclaimers)
- [PC Requirements and Setup](#pc-requirements-and-setup)
- [Step 1: Backup Stock Partitions](#step-1-backup-stock-partitions)
- [Step 2: Patch `lk` and Unlock Bootloader](#step-2-patch-lk-and-unlock-bootloader)
- [Step 3: Build and Flash Network-Unlocked Modem (`md1img_a`)](#step-3-build-and-flash-network-unlocked-modem-md1img_a)
- [Step 4: Systemless "Network lock" UI Spoofing](#step-4-systemless-network-lock-ui-spoofing)
- [Verification Checklist](#verification-checklist)
- [Reverting to Stock](#reverting-to-stock)
- [Compatibility with Newer OTA Builds](#compatibility-with-newer-ota-builds)
- [Repository Layout](#repository-layout)
- [Credits and Licenses](#credits-and-licenses)

---

## Supported Device and Firmware Baseline

Tested and validated on this exact Tracfone / Straight Talk firmware build:

| Property | Value |
| :--- | :--- |
| **Retail Device** | Motorola Moto G Power - 2026 (Straight Talk / Tracfone / Walmart) |
| **Hardware Model** | `XT2617V` |
| **Product Board (`ro.product.board`)** | `vegas` / `vegas26` |
| **Carrier Channel (`ro.carrier`)** | `tracfone` |
| **Android Version** | `16` |
| **Security Patch** | `2026-04-01` |
| **Build ID (`ro.build.display.id`)** | `W1WEOS36.48-22-3-3-4-2` |
| **Baseband (`gsm.version.baseband`)** | `MT6835O_NR17.RC.MP.V18.6.6.P107.02.309R` |
| **Stock Active Slot** | `_a` |

> [!NOTE]
> **Factory / Rescue Firmware Shortcut:** If you already have official factory/rescue firmware files (`lk.img`/`lk.bin` and `md1img.img`/`md1img.bin`) for build `W1WEOS36.48-22-3-3-4-2`, you can skip pre-unlock temporary root and Step 1 entirely, feeding the extracted images directly into Step 2 and Step 3.

---

## Workflow and Root Lifecycle Overview

To avoid confusion regarding root methods (KernelSU vs. Magisk), note the three distinct phases of this modification:

| Phase | Purpose | Root Method Required | Tooling |
| :--- | :--- | :--- | :--- |
| **Phase 1: Partition Dump** | Back up stock `lk_a`, `md1img_a`, and GPT tables. | **Temporary Root** (e.g. DFRoot / DirtyFrag + KernelSU) or stock factory firmware. | `scripts/backup_partitions.py` |
| **Phase 2: Bootloader & Modem Unlock** | Flash patched `lk`, unlock bootloader via OEM key, and flash patched modem. | **No Root Needed** (Fastboot mode). | `bootloader/patch_lk.py`<br>`modem/unlock_vegas.py` |
| **Phase 3: Persistent Root & UI Spoof** | Install permanent root and deploy the headless Xposed module. | **Persistent Magisk Root** (patched `init_boot`). | `scripts/deploy_network_lock_spoof.py` |

---

## Safety Warnings and Disclaimers

> [!CAUTION]
> **Your warranty is now void.** You are choosing to make these modifications at your own risk. The authors and contributors are not responsible for bricked devices, corrupted storage, carrier blacklist issues, or hardware damage.

> [!WARNING]
> - **Unlocking the bootloader erases all user data (`userdata`).** Always back up any critical personal files before running `fastboot oem unlock`.
> - **Flash ONLY `lk` (active slot `lk_a`) and `md1img_a`.** Never attempt to flash `md1img_b`, `preloader`, `seccfg`, `gpt`, `pgpt`, `efuse`, `nvram`, `nvdata`, `protect1`, `protect2`, or `persist`.
> - **Do not re-flash stock `lk` after unlocking.** Re-flashing stock `lk` while the bootloader is in an unlocked state can trigger secure boot validation mismatch and lead to boot loops. Keep your stock `lk_a.img` backup offline for emergency reference only.
> - **Leave files in `backups/` untouched.** Generated patched images and intermediate artifacts are written to `work/`. Never publish or share backups containing your serial number or IMEI.

---

## PC Requirements and Setup

Install and verify these prerequisites on your host computer:

1. **Python 3.10+** (tested on Python `3.10` through `3.14`).
2. **Python Dependencies** (required by `bootloader/` disassembler; `scripts/` and `modem/` use standard library):
   - `capstone>=5.0,<6.0`
   - `pyasn1>=0.5.0`
3. **Android SDK Platform Tools** (`adb` and `fastboot` added to your system `PATH`).
4. **Motorola USB Drivers** (Windows users: install official Motorola Mobile Drivers so both ADB and Fastboot interfaces are recognized in Device Manager).
5. **~13 GB free disk space** if creating a complete partition backup (including `super.img`).

Install required Python packages from the repository root:

```bash
pip install -r requirements.txt
```

Verify your environment:

```bash
python --version
adb version
fastboot --version
```

---

## Step 1: Backup Stock Partitions

Before flashing anything, obtain a clean, verifiable backup of all unique block partitions.

### 1. Configure USB Debugging & Shell Root

1. Enable Developer Options: **Settings > About phone > tap "Build number" 7 times**.
2. Enable USB Debugging: **Settings > System > Developer options > USB debugging** -> **ON**.
3. Connect your phone via USB and authorize the RSA computer fingerprint:
   ```bash
   adb devices
   ```
   Ensure the output lists `device` (not `unauthorized`).
4. Grant superuser permission to **`Shell`** in your temporary root app (e.g., KernelSU Superuser tab).
5. Confirm root shell access over ADB:
   ```bash
   adb shell su -c id
   ```
   *Expected output: Contains `uid=0(root)`.*

### 2. Run Partition Backup

Execute the cross-platform Python backup script:

```bash
python scripts/backup_partitions.py
```

> [!IMPORTANT]
> Do **NOT** use PowerShell output redirection (e.g. `adb exec-out ... > dump.img`). PowerShell treats binary output streams as text and corrupts image dumps with character encoding transforms. Always use `backup_partitions.py` (or Git Bash / Linux `backup_partitions.sh`).

**What this outputs in `backups/stock_YYYYMMDD_HHMMSS/`:**
- All unique partitions under `/dev/block/by-name/` verified against on-device `sha256sum`.
- `gpt_sdc_head_1M.bin` and `gpt_sdc_tail_1M.bin`.
- Metadata logs: `getprop.txt`, `partitions_by-name.txt`, `proc_partitions.txt`, `name_map.txt`, and `SHA256SUMS`.

Note your backup directory name (`<BACKUP_DIR>`, e.g. `stock_20261115_120000`) and ensure `lk_a.img` and `md1img_a.img` are present.

---

## Step 2: Patch `lk` and Unlock Bootloader

### 1. Patch the Little Kernel (`lk`) Image

Generate an unlock-capable `lk` image from your stock backup:

```bash
python bootloader/patch_lk.py backups/<BACKUP_DIR>/lk_a.img
```

- **Output:** `work/lk.unlock-serial.img` (`3,477,904` bytes).
- **Verification:** The script automatically validates CERT structures (`Result: VALID`).
- On stock `W1WEOS36.48-22-3-3-4-2`, SHA-256 is `914acfce78939c61a744294ecb686a0865424c36c397878ab6e919be9513eed1`.

### 2. Reboot to Bootloader & Flash Patched `lk`

Reboot to Fastboot mode:

```bash
adb reboot bootloader
fastboot devices
```

Flash the patched `lk` to active slot `lk` (`lk_a`) and reboot back into the bootloader so the patched Little Kernel initializes:

```bash
fastboot flash lk work/lk.unlock-serial.img
fastboot reboot bootloader
```

### 3. Generate Unlock Key & Execute Unlock

Retrieve your hardware serial number, compute the Val protocol unlock key, and issue the unlock command:

```bash
fastboot getvar serialno
python bootloader/lk_keygen.py --secret Valeria --serialno <SERIALNO> --count 1
fastboot oem unlock <KEY>
```

> [!NOTE]
> If a confirmation prompt appears on the phone screen, use the **Volume keys** to highlight the unlock option and the **Power key** to confirm. Unlocking erases all user data on the device.

### 4. Verify Bootloader Unlock State

Confirm the bootloader is officially unlocked:

```bash
fastboot getvar securestate
```

*Expected output:* `securestate: flashing_unlocked`

---

## Step 3: Build and Flash Network-Unlocked Modem (`md1img_a`)

### 1. Build and CERT2-Sign the Unlocked Modem

Run the automated modem builder against your dumped stock `md1img_a.img`:

```bash
python modem/unlock_vegas.py build backups/<BACKUP_DIR>/md1img_a.img
```

**Automated operations performed by the script:**
- Trims trailing `0x00` partition padding (`209,715,200` &rarr; `76,088,352` bytes) and saves `work/modem_work/md1img_stock_trimmed.img`.
- Validates stock trimmed SHA-256 (`dab9e69e3bbb009dd2a7907f3603df101e15b11c3f34e1461745b1699c7d4757`).
- Applies the 8 verified microMIPS32 unlock patches from `modem/profiles/vegas.json`.
- Updates internal CERT2 cryptographic signatures (`modem/sign_mtk_cert.py`).
- Audits all 23 MKIMG partition entries (`layout_ok=True integrity=True`).
- Writes final flashable image: `work/md1img_vegas_patched.signed.img` (`76,088,448` bytes, SHA-256 `f6bd718ffb5c734cdab9e3c9c8c83987bf8e7b71299adb372cf678940b27046a`).

### 2. Flash Patched Modem via Fastboot

Ensure the device is in bootloader mode (`fastboot devices`) with `securestate: flashing_unlocked`. Flash **only `md1img_a`** and reboot:

```bash
fastboot flash md1img_a work/md1img_vegas_patched.signed.img
fastboot reboot
```

### 3. Verify Cellular SIM Lock State

Insert a non-Tracfone SIM card (T-Mobile, AT&T, Verizon, etc.), re-enable USB Debugging, and query telephony properties over ADB:

```bash
adb shell getprop gsm.sim.state
adb shell getprop gsm.sim.operator.alpha
adb shell getprop vendor.gsm.sim.slot.lock.device.lock.remain.count
```

*Expected values with a foreign SIM:*
- `gsm.sim.state`: `LOADED` (or `LOADED,NOT_READY` if slot 2 is unpopulated; a locked modem displays `NETWORK_LOCKED`).
- `gsm.sim.operator.alpha`: Shows your active carrier name.
- `vendor.gsm.sim.slot.lock.device.lock.remain.count`: `5` (lock counter never decrements).

---

## Step 4: Systemless "Network lock" UI Spoofing

### Why This Is Required

On Android 16, **Settings > About phone > Network lock** does not query a static system property. Instead, it dynamically queries an IPC ContentProvider hosted by Motorola's privileged carrier package:
`content://com.motorola.carriersettingsext.unlock.networkunlockpreference/summary`

Because Android 16 strictly enforces OEM platform cryptographic signatures on `/product/priv-app/` packages, modifying or replacing `CarrierSettingsExt.apk` on disk causes signature verification failures.

### The Solution: Headless `SpoofNetworkLock`

We use **Vector** (an Android 15/16-compatible modern Xposed framework running via **Zygisk Next**) and the headless **`SpoofNetworkLock`** module (`xposed/SpoofNetworkLock.apk`) to intercept the UI summary and subsidy lock checks in memory:
- Hooks `TileUtils.getTextFromUri` to return `"Unlocked"`.
- Hooks `UnlockPrefUtils.getSummary` and `SubsidyUtil.isSubsidyLocked`.
- Declaratively intercepts `NetworkUnlockPreferenceProvider#call('summary')`.
- Declares **no launcher activity**, operating 100% headlessly in the background with zero app drawer clutter.

### Automated Deployment

> [!IMPORTANT]
> **Prerequisites for Step 4:** The phone must have persistent **Magisk root** installed (`su` working over ADB) and USB Debugging re-enabled after bootloader unlocking.

Run the all-in-one deploy script from your PC:

```bash
python scripts/deploy_network_lock_spoof.py
```

**What the deployment script handles automatically:**
1. Verifies ADB connectivity and Magisk root permissions.
2. Checks for Zygisk Next and Vector; automatically downloads official GitHub release packages if not present, and installs them via Magisk.
3. Installs `xposed/SpoofNetworkLock.apk` headlessly.
4. Ensures any standalone Vector manager app is uninstalled to keep the system completely clean of unwanted UI icons.
5. Provisions `/data/adb/lspd/config/modules_config.db` with proper scopes:
   - `com.android.settings`
   - `com.motorola.carriersettingsext`
   - `system`
6. Applies the unshare namespace isolation patch to `/data/adb/modules/zygisk_vector/service.sh`.
7. Triggers a reboot if modules were freshly installed, or restarts target applications and tests the live ContentProvider summary.

### Manual Source Compilation (Optional)

A pre-built, signed APK is included at `xposed/SpoofNetworkLock.apk`. If you wish to build from source using Android build tools (`aapt2`, `javac`, `d8`):

```bash
python xposed/build_module.py
```

---

## Verification Checklist

| Verification Target | Command | Expected Result |
| :--- | :--- | :--- |
| **Bootloader Unlock** | `fastboot getvar securestate` | `securestate: flashing_unlocked` |
| **Active Slot** | `fastboot getvar current-slot` | `current-slot: a` |
| **Baseband Firmware** | `adb shell getprop gsm.version.baseband` | `MT6835O_NR17.RC.MP.V18.6.6.P107.02.309R` |
| **SIM Status** | `adb shell getprop gsm.sim.state` | `LOADED` (with non-Tracfone SIM) |
| **Carrier Detection** | `adb shell getprop gsm.sim.operator.alpha` | Your carrier name (e.g., `T-Mobile`) |
| **Carrier Provider Query** | `adb shell content call --uri content://com.motorola.carriersettingsext.unlock.networkunlockpreference/summary --method summary` | `Bundle[{com.android.settings.summary=Unlocked}]` |
| **Settings UI** | Open **Settings > About phone** | **Network lock** displays **Unlocked** |

---

## Reverting to Stock

### 1. Revert Modem to Stock

To restore the original stock modem firmware, flash the trimmed stock backup generated in Step 3:

```bash
adb reboot bootloader
fastboot flash md1img_a work/modem_work/md1img_stock_trimmed.img
fastboot reboot
```

### 2. Revert Network Lock Spoof

To disable or remove the systemless UI spoof:
- Uninstall the module APK:
  ```bash
  adb uninstall com.example.spoofnetworklock
  ```
- Or disable/remove the Zygisk Next and Vector modules within the Magisk app.

---

## Compatibility with Newer OTA Builds

If your device is running a newer OTA firmware revision or is a related MediaTek Motorola device:

### 1. Check `lk` Compatibility

Run `patch_lk.py` in check-only mode (dynamic Capstone disassembly without writing to `work/`):

```bash
python bootloader/patch_lk.py --check <path_to_lk.img>
```

If the tool reports `COMPATIBLE` / `LIKELY COMPATIBLE` (`Result: VALID`), the dynamic pattern matcher has successfully located the required unlock routines.

### 2. Check `md1img` Compatibility

Run `unlock_vegas.py` in check mode:

```bash
python modem/unlock_vegas.py check <path_to_md1img.img>
```

- Scans the internal `md1_dbginfo` (CATI symbol table) and checks for unique matches of all 8 microMIPS32 instruction signatures (`custom_check_link_sml_legal_sim_rule`, `sml_sl_Check`, `smu_check_sml`).
- If `check` reports `CANDIDATE MATCH`, an experimental relocated image can be tested **at your own risk**:
  ```bash
  python modem/unlock_vegas.py build --experimental-relocate <path_to_md1img.img>
  ```
  If mismatches (`INCOMPATIBLE`) are reported, do not flash.

---

## Repository Layout

```text
vegas-freedom-xposed/
├── README.md                              # This comprehensive documentation
├── LICENSE                                # GNU Affero General Public License v3.0
├── LICENSE-NOTICE.md                      # Attribution and third-party notices
├── requirements.txt                       # Python dependencies (capstone, pyasn1)
├── scripts/
│   ├── backup_partitions.py               # Cross-platform full partition dump utility
│   ├── backup_partitions.sh               # Shell alternative for Linux/macOS
│   └── deploy_network_lock_spoof.py       # Automated Zygisk/Vector/Xposed deployer
├── xposed/
│   ├── README.md                          # Architecture and hook point documentation
│   ├── SpoofNetworkLock.apk               # Prebuilt signed headless Xposed module
│   ├── build_module.py                    # Standalone APK compiler script
│   └── SpoofNetworkLock/                  # Java source project
│       ├── AndroidManifest.xml
│       ├── assets/
│       │   └── xposed_init
│       ├── res/values/
│       │   ├── arrays.xml
│       │   └── strings.xml
│       └── src/com/example/spoofnetworklock/
│           └── HookInit.java              # ART hook definitions
├── bootloader/
│   ├── LICENSE                            # AGPL-3.0 / GPL-3.0
│   ├── ACKNOWLEDGEMENTS.md                # Valhalla / val-protocol attribution
│   ├── patch_lk.py                        # Main Little Kernel patcher & cert signer
│   ├── lk_auto_patch.py                   # Automated opcode relocation engine
│   ├── lk_keygen.py                       # Val protocol 20-char key generator
│   ├── lk_patch_partition.py              # Partition offset patching utility
│   ├── lk_repack_signed.py                # MediaTek image repack & signature utility
│   ├── lk_static_analyzer.py              # Disassembly & symbol analysis
│   ├── liblk/                             # Core Little Kernel parser & structures
│   └── tools/                             # MTK certificate parsing and signing tools
└── modem/
    ├── LICENSE                            # MIT License
    ├── unlock_vegas.py                    # MicroMIPS32 modem unlock & audit orchestrator
    ├── imageaudit.py                      # MKIMG partition header integrity auditor
    ├── sign_mtk_cert.py                   # MediaTek CERT2 signature utility
    ├── parse_mtk_certs.py                 # MediaTek certificate parser
    ├── verify_mtk_image.py                # Image validation utility
    └── profiles/
        └── vegas.json                     # Verified microMIPS32 opcode patch profile
```

---

## Credits and Licenses

- **Repository License ([LICENSE](LICENSE)):** GNU Affero General Public License v3.0 (**AGPL-3.0**).
- **Bootloader Unlock (`bootloader/`):** Adapted from [crabcakes97/Valhalla](https://github.com/crabcakes97/Valhalla) (built on [Maikyxd/val-protocol](https://github.com/Maikyxd/val-protocol), `AGPL-3.0`, and [R0rt1z2/liblk](https://github.com/R0rt1z2/liblk), `GPL-3.0-or-later`). See [bootloader/LICENSE](bootloader/LICENSE) and [bootloader/ACKNOWLEDGEMENTS.md](bootloader/ACKNOWLEDGEMENTS.md).
- **Modem Unlock (`modem/`):** Adapted from [Articfox291/kansas-modem-unlock](https://github.com/Articfox291/kansas-modem-unlock) with custom verified `vegas` microMIPS32 patch profile (`MIT`, see [modem/LICENSE](modem/LICENSE)).
- **Xposed Framework & Modules:** Powered by [Dr-TSNG/ZygiskNext](https://github.com/Dr-TSNG/ZygiskNext) and [JingMatrix/Vector](https://github.com/JingMatrix/Vector).
- See [LICENSE-NOTICE.md](LICENSE-NOTICE.md) for full licensing details.
