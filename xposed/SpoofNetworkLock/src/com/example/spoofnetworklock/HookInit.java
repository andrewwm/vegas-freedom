package com.example.spoofnetworklock;

import android.content.Context;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;

import java.util.Map;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

public class HookInit implements IXposedHookLoadPackage {
    private static final String TAG = "SpoofNetworkLock";

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) throws Throwable {
        if (!"com.android.settings".equals(lpparam.packageName) &&
            !"com.motorola.carriersettingsext".equals(lpparam.packageName)) {
            return;
        }

        XposedBridge.log(TAG + ": Loaded in package: " + lpparam.packageName);
        Log.i(TAG, "Loaded in package: " + lpparam.packageName);

        if ("com.android.settings".equals(lpparam.packageName)) {
            hookSettings(lpparam);
        }

        if ("com.motorola.carriersettingsext".equals(lpparam.packageName)) {
            hookCarrierSettingsExt(lpparam);
        }
    }

    private void hookSettings(XC_LoadPackage.LoadPackageParam lpparam) {
        // Case A: AOSP TelephonyManager.getCarrierRestrictionStatus()
        try {
            XposedHelpers.findAndHookMethod(
                "android.telephony.TelephonyManager",
                lpparam.classLoader,
                "getCarrierRestrictionStatus",
                new XC_MethodHook() {
                    @Override
                    protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                        XposedBridge.log(TAG + ": Spoofing TelephonyManager.getCarrierRestrictionStatus() to NOT_RESTRICTED (1)");
                        param.setResult(1); // CARRIER_RESTRICTION_STATUS_NOT_RESTRICTED
                    }
                }
            );
            XposedBridge.log(TAG + ": Successfully hooked TelephonyManager.getCarrierRestrictionStatus");
        } catch (Throwable t) {
            XposedBridge.log(TAG + ": Error hooking TelephonyManager: " + t.getMessage());
        }

        // Case B1: Hook TileUtils.getTextFromUri which pulls injected tile summary from provider
        try {
            Class<?> tileUtilsClass = XposedHelpers.findClassIfExists("com.android.settingslib.drawer.TileUtils", lpparam.classLoader);
            if (tileUtilsClass != null) {
                XposedHelpers.findAndHookMethod(
                    tileUtilsClass,
                    "getTextFromUri",
                    Context.class,
                    Uri.class,
                    Map.class,
                    String.class,
                    new XC_MethodHook() {
                        @Override
                        protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                            Uri uri = (Uri) param.args[1];
                            String key = (String) param.args[3];
                            if (uri != null && "com.android.settings.summary".equals(key)) {
                                String uriStr = uri.toString();
                                if (uriStr.contains("networkunlockpreference") || uriStr.contains("unlock")) {
                                    XposedBridge.log(TAG + ": Intercepted TileUtils.getTextFromUri for " + uriStr + " -> spoofing to Unlocked");
                                    param.setResult("Unlocked");
                                }
                            }
                        }
                    }
                );
                XposedBridge.log(TAG + ": Successfully hooked TileUtils.getTextFromUri");
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + ": Error hooking TileUtils.getTextFromUri: " + t.getMessage());
        }

        // Case B2: Hook Preference.setSummary / getSummary in Settings UI
        try {
            Class<?> prefClass = XposedHelpers.findClassIfExists("androidx.preference.Preference", lpparam.classLoader);
            if (prefClass != null) {
                XposedHelpers.findAndHookMethod(
                    prefClass,
                    "setSummary",
                    CharSequence.class,
                    new XC_MethodHook() {
                        @Override
                        protected void beforeHookedMethod(MethodHookParam param) throws Throwable {
                            CharSequence summary = (CharSequence) param.args[0];
                            if (summary != null && "Locked".contentEquals(summary)) {
                                Object pref = param.thisObject;
                                CharSequence title = (CharSequence) XposedHelpers.callMethod(pref, "getTitle");
                                String key = (String) XposedHelpers.callMethod(pref, "getKey");
                                if ((title != null && title.toString().toLowerCase().contains("lock")) ||
                                    (key != null && key.toLowerCase().contains("unlock"))) {
                                    XposedBridge.log(TAG + ": Preference.setSummary('Locked') on " + key + "/" + title + " -> changing to Unlocked");
                                    param.args[0] = "Unlocked";
                                }
                            }
                        }
                    }
                );

                XposedHelpers.findAndHookMethod(
                    prefClass,
                    "getSummary",
                    new XC_MethodHook() {
                        @Override
                        protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                            CharSequence result = (CharSequence) param.getResult();
                            if (result != null && "Locked".contentEquals(result)) {
                                Object pref = param.thisObject;
                                CharSequence title = (CharSequence) XposedHelpers.callMethod(pref, "getTitle");
                                String key = (String) XposedHelpers.callMethod(pref, "getKey");
                                if ((title != null && title.toString().toLowerCase().contains("lock")) ||
                                    (key != null && key.toLowerCase().contains("unlock"))) {
                                    param.setResult("Unlocked");
                                }
                            }
                        }
                    }
                );
                XposedBridge.log(TAG + ": Successfully hooked Preference setSummary/getSummary");
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + ": Error hooking Preference: " + t.getMessage());
        }
    }

    private void hookCarrierSettingsExt(XC_LoadPackage.LoadPackageParam lpparam) {
        // Hook UnlockPrefUtils in com.motorola.carriersettingsext
        try {
            Class<?> unlockUtils = XposedHelpers.findClassIfExists("com.motorola.carriersettingsext.unlock.UnlockPrefUtils", lpparam.classLoader);
            if (unlockUtils != null) {
                XposedHelpers.findAndHookMethod(unlockUtils, "getSummary", Context.class, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) throws Throwable {
                        XposedBridge.log(TAG + ": UnlockPrefUtils.getSummary -> Unlocked");
                        param.setResult("Unlocked");
                    }
                });

                XposedHelpers.findAndHookMethod(unlockUtils, "isDeviceLocked", Context.class, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) throws Throwable {
                        XposedBridge.log(TAG + ": UnlockPrefUtils.isDeviceLocked -> false");
                        param.setResult(false);
                    }
                });
                XposedBridge.log(TAG + ": Successfully hooked UnlockPrefUtils");
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + ": Error hooking UnlockPrefUtils: " + t.getMessage());
        }

        // Hook SubsidyUtil.isSubsidyLocked
        try {
            Class<?> subsidyUtil = XposedHelpers.findClassIfExists("com.motorola.android.subsidyutils.SubsidyUtil", lpparam.classLoader);
            if (subsidyUtil != null) {
                XposedHelpers.findAndHookMethod(subsidyUtil, "isSubsidyLocked", Context.class, new XC_MethodHook() {
                    @Override
                    protected void beforeHookedMethod(MethodHookParam param) throws Throwable {
                        XposedBridge.log(TAG + ": SubsidyUtil.isSubsidyLocked -> false");
                        param.setResult(false);
                    }
                });
                XposedBridge.log(TAG + ": Successfully hooked SubsidyUtil.isSubsidyLocked");
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + ": Error hooking SubsidyUtil: " + t.getMessage());
        }

        // Hook NetworkUnlockPreferenceProvider.call
        try {
            Class<?> providerClass = XposedHelpers.findClassIfExists("com.motorola.carriersettingsext.unlock.NetworkUnlockPreferenceProvider", lpparam.classLoader);
            if (providerClass != null) {
                XposedHelpers.findAndHookMethod(
                    providerClass,
                    "call",
                    String.class,
                    String.class,
                    Bundle.class,
                    new XC_MethodHook() {
                        @Override
                        protected void beforeHookedMethod(MethodHookParam param) throws Throwable {
                            String method = (String) param.args[0];
                            if ("summary".equals(method)) {
                                Bundle b = new Bundle();
                                b.putString("com.android.settings.summary", "Unlocked");
                                XposedBridge.log(TAG + ": NetworkUnlockPreferenceProvider.call('summary') -> Unlocked");
                                param.setResult(b);
                            }
                        }
                    }
                );
                XposedBridge.log(TAG + ": Successfully hooked NetworkUnlockPreferenceProvider.call");
            }
        } catch (Throwable t) {
            XposedBridge.log(TAG + ": Error hooking NetworkUnlockPreferenceProvider: " + t.getMessage());
        }
    }
}
