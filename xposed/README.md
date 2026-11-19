# SpoofNetworkLock Xposed Module

Systemless hook for **Motorola Moto G Power 2026 (`XT2617V` / `vegas`)** running Android 16 to spoof the dynamic **Settings > About phone > Network lock** tile from **"Locked"** to **"Unlocked"**.

## Architecture & Why This Is Required

On Android 16, **"Network lock"** is not a static preference or system property. It is an injected dashboard tile rendered via ContentProvider IPC from Motorola's OEM carrier package (`com.motorola.carriersettingsext`):

1. `com.android.settings` queries URI:  
   `content://com.motorola.carriersettingsext.unlock.networkunlockpreference/summary`
2. `com.motorola.carriersettingsext.unlock.NetworkUnlockPreferenceProvider` executes `UnlockPrefUtils.getSummary()` which calls `SubsidyUtil.isSubsidyLocked()`.
3. `SubsidyUtil` queries the baseband radio service (`motoexttelephony` binder).
4. Because Android 16 strictly enforces OEM platform cryptographic signatures on `/product/priv-app/` overlays, replacing `CarrierSettingsExt.apk` on disk causes PackageManager signature verification failures.
5. Therefore, the lock state must be modified systemlessly in memory while the app runs.

## Hook Points Implemented (`HookInit.java`)

1. **`com.android.settingslib.drawer.TileUtils#getTextFromUri`**  
   Intercepts the URI query for `networkunlockpreference` and returns `"Unlocked"`.
2. **`androidx.preference.Preference#setSummary` & `#getSummary`**  
   Catches any UI row whose title or key references network locking and sets the summary to `"Unlocked"`.
3. **`com.motorola.carriersettingsext.unlock.UnlockPrefUtils#getSummary`**  
   Forces summary string to `"Unlocked"`.
4. **`com.motorola.carriersettingsext.unlock.UnlockPrefUtils#isDeviceLocked`**  
   Forces return value to `false`.
5. **`com.motorola.android.subsidyutils.SubsidyUtil#isSubsidyLocked`**  
   Forces return value to `false`.
6. **`com.motorola.carriersettingsext.unlock.NetworkUnlockPreferenceProvider#call`**  
   Intercepts method `'summary'` and returns `Bundle[{com.android.settings.summary=Unlocked}]`.
7. **`android.telephony.TelephonyManager#getCarrierRestrictionStatus`**  
   Returns `1` (`CARRIER_RESTRICTION_STATUS_NOT_RESTRICTED`).

## Headless Design

The module declares **no launcher activity**. It runs 100% headlessly in the background via the Vector Xposed framework without placing any extra icons on your home screen or app drawer.

## Deployment

To deploy this module along with the required Zygisk Next and Vector frameworks, run:

```bash
python scripts/deploy_network_lock_spoof.py
```
