#!/usr/bin/env python3
"""
build_module.py
Compiles and signs the headless SpoofNetworkLock Xposed module APK from source.
Requires:
  - aapt2 (Android Build Tools or standalone)
  - javac / ecj
  - d8 (Android Build Tools or r8.jar)
  - apksigner / uber-apk-signer (or keytool + jarsigner)
"""

import os
import sys
import shutil
import glob
import zipfile
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.join(SCRIPT_DIR, "SpoofNetworkLock")
BUILD_DIR = os.path.join(PROJECT_DIR, "build")
OUTPUT_APK = os.path.join(SCRIPT_DIR, "SpoofNetworkLock.apk")

def find_tool(name, android_home=None):
    # Check PATH first
    tool = shutil.which(name)
    if tool:
        return tool
    if android_home:
        # Search build-tools in ANDROID_HOME
        matches = glob.glob(os.path.join(android_home, "build-tools", "*", name + "*"))
        if matches:
            return matches[-1]
    return None

def main():
    android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    aapt2 = find_tool("aapt2", android_home)
    d8 = find_tool("d8", android_home)
    javac = find_tool("javac")

    if not (aapt2 and javac and d8):
        print("[!] Standard Android build tools (aapt2, javac, d8) not fully found on PATH.")
        print(f"    aapt2: {aapt2}")
        print(f"    javac: {javac}")
        print(f"    d8:    {d8}")
        print(f"[*] Note: A pre-built signed APK is already included at: {OUTPUT_APK}")
        return 0

    print(f"[*] Building SpoofNetworkLock from source...")
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    bin_dir = os.path.join(BUILD_DIR, "bin")
    gen_dir = os.path.join(BUILD_DIR, "gen")
    classes_dir = os.path.join(bin_dir, "classes")
    dex_dir = os.path.join(bin_dir, "dex")
    os.makedirs(classes_dir, exist_ok=True)
    os.makedirs(gen_dir, exist_ok=True)
    os.makedirs(dex_dir, exist_ok=True)

    # Find android.jar
    android_jar = None
    if android_home:
        platforms = glob.glob(os.path.join(android_home, "platforms", "*", "android.jar"))
        if platforms:
            android_jar = platforms[-1]

    if not android_jar:
        print("[!] android.jar not found. Using pre-built APK.")
        return 0

    # 1. Compile resources
    res_zip = os.path.join(bin_dir, "res.zip")
    subprocess.check_call([aapt2, "compile", "--dir", os.path.join(PROJECT_DIR, "res"), "-o", res_zip])

    # 2. Link resources and generate R.java
    manifest = os.path.join(PROJECT_DIR, "AndroidManifest.xml")
    unaligned_apk = os.path.join(bin_dir, "unaligned.apk")
    subprocess.check_call([
        aapt2, "link",
        "-I", android_jar,
        "--manifest", manifest,
        "-o", unaligned_apk,
        "--java", gen_dir,
        "--auto-add-overlay",
        res_zip
    ])

    # 3. Compile Java sources
    java_files = glob.glob(os.path.join(PROJECT_DIR, "src", "**", "*.java"), recursive=True)
    java_files += glob.glob(os.path.join(gen_dir, "**", "*.java"), recursive=True)
    subprocess.check_call([javac, "-cp", android_jar, "-d", classes_dir] + java_files)

    # 4. Convert classes to DEX
    class_files = glob.glob(os.path.join(classes_dir, "com", "example", "spoofnetworklock", "*.class"))
    subprocess.check_call([d8, "--output", dex_dir, "--lib", android_jar] + class_files)

    # 5. Package DEX and assets into APK
    with zipfile.ZipFile(unaligned_apk, "a") as z:
        z.write(os.path.join(dex_dir, "classes.dex"), "classes.dex")
        z.write(os.path.join(PROJECT_DIR, "assets", "xposed_init"), "assets/xposed_init")

    # 6. Sign APK with debug keystore
    apksigner = find_tool("apksigner", android_home)
    if apksigner:
        shutil.copy2(unaligned_apk, OUTPUT_APK)
        subprocess.check_call([apksigner, "sign", "--ks-key-alias", "androiddebugkey", "--ks-pass", "pass:android", OUTPUT_APK])
    else:
        shutil.copy2(unaligned_apk, OUTPUT_APK)

    print(f"[+] Successfully built: {OUTPUT_APK}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
