"""
build_ipa_remote.py — Assembles a signable IPA using GitHub Actions or
any remote Mac with Swift toolchain.

This script:
1. Generates a GitHub Actions workflow that compiles and packages the IPA
2. OR builds a local .ipa structure if a pre-compiled binary is provided

Usage (local with pre-built binary):
    python build_ipa_remote.py --binary path/to/TgWsProxy

Usage (generate GitHub Actions workflow):
    python build_ipa_remote.py --github-actions
"""

import argparse
import os
import sys
import zipfile
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BUNDLE_ID = "com.tgwsproxy.app"


def build_local_ipa(binary_path: str, output: str = "TgWsProxy.ipa"):
    """Build IPA from a pre-compiled arm64 binary."""
    binary = Path(binary_path)
    if not binary.exists():
        print(f"ERROR: Binary not found: {binary}")
        sys.exit(1)

    resources = SCRIPT_DIR / "TgWsProxy" / "Resources"
    info_plist = resources / "Info.plist"

    if not info_plist.exists():
        print(f"ERROR: Info.plist not found: {info_plist}")
        sys.exit(1)

    output_path = Path(output)

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        app_prefix = "Payload/TgWsProxy.app/"

        # Main executable
        with open(binary, 'rb') as f:
            data = f.read()
        info = zipfile.ZipInfo(app_prefix + "TgWsProxy")
        info.external_attr = 0o755 << 16  # executable
        zf.writestr(info, data)

        # Info.plist
        zf.write(info_plist, app_prefix + "Info.plist")

        # PkgInfo
        zf.writestr(app_prefix + "PkgInfo", "APPL????")

        # Entitlements (not embedded in IPA, used for signing)
        entitlements = resources / "TgWsProxy.entitlements"
        if entitlements.exists():
            zf.write(entitlements, app_prefix + "TgWsProxy.entitlements")

        # Provisioning profile
        profile = SCRIPT_DIR / "embedded.mobileprovision"
        if profile.exists():
            zf.write(profile, app_prefix + "embedded.mobileprovision")

    print(f"IPA created: {output_path}")
    print(f"Size: {output_path.stat().st_size / 1024:.1f} KB")
    print()
    print("Sign with your developer certificate before installing.")


def generate_github_actions():
    """Generate a GitHub Actions workflow that compiles and packages the IPA."""
    workflow = """\
name: Build TgWsProxy iOS IPA

on:
  workflow_dispatch:
  push:
    paths:
      - 'ios-app/**'

jobs:
  build:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4

      - name: Setup Xcode
        uses: maxim-lobanov/setup-xcode@v1
        with:
          xcode-version: latest-stable

      - name: Find iOS SDK
        run: |
          SDK=$(xcrun --sdk iphoneos --show-sdk-path)
          echo "SDK=$SDK" >> $GITHUB_ENV
          echo "Using SDK: $SDK"

      - name: Compile Swift sources
        working-directory: ios-app
        run: |
          mkdir -p build/Payload/TgWsProxy.app

          SOURCES=(
            TgWsProxy/Sources/TgWsProxyApp.swift
            TgWsProxy/Sources/ContentView.swift
            TgWsProxy/Sources/SettingsView.swift
            TgWsProxy/Sources/ProxyConfig.swift
            TgWsProxy/Sources/ProxyManager.swift
            TgWsProxy/Sources/Crypto.swift
            TgWsProxy/Sources/RawWebSocket.swift
            TgWsProxy/Sources/MTProtoHandshake.swift
            TgWsProxy/Sources/MTProtoProxyServer.swift
            TgWsProxy/Sources/LiveActivityManager.swift
          )

          swiftc \\
            -target arm64-apple-ios16.1 \\
            -sdk $SDK \\
            -O \\
            -whole-module-optimization \\
            -module-name TgWsProxy \\
            -emit-executable \\
            -o build/Payload/TgWsProxy.app/TgWsProxy \\
            -framework Foundation \\
            -framework SwiftUI \\
            -framework UIKit \\
            -framework Network \\
            -framework ActivityKit \\
            -framework WidgetKit \\
            "${SOURCES[@]}"

          strip -x build/Payload/TgWsProxy.app/TgWsProxy

      - name: Assemble app bundle
        working-directory: ios-app
        run: |
          cp TgWsProxy/Resources/Info.plist build/Payload/TgWsProxy.app/
          echo -n "APPL????" > build/Payload/TgWsProxy.app/PkgInfo

      - name: Create IPA
        working-directory: ios-app
        run: |
          cd build
          zip -r ../TgWsProxy-unsigned.ipa Payload/

      - name: Upload IPA
        uses: actions/upload-artifact@v4
        with:
          name: TgWsProxy-unsigned-ipa
          path: ios-app/TgWsProxy-unsigned.ipa
"""

    workflow_dir = SCRIPT_DIR.parent / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    workflow_path = workflow_dir / "build-ios.yml"
    workflow_path.write_text(workflow)
    print(f"GitHub Actions workflow created: {workflow_path}")
    print()
    print("Push to GitHub and run the workflow to get the unsigned IPA.")
    print("Then sign it locally with your developer certificate.")


def main():
    parser = argparse.ArgumentParser(description="Build TgWsProxy IPA")
    parser.add_argument("--binary", help="Path to pre-compiled arm64 binary")
    parser.add_argument("--output", default="TgWsProxy.ipa", help="Output IPA path")
    parser.add_argument("--github-actions", action="store_true",
                        help="Generate GitHub Actions workflow for CI build")
    args = parser.parse_args()

    if args.github_actions:
        generate_github_actions()
    elif args.binary:
        build_local_ipa(args.binary, args.output)
    else:
        print("Use --github-actions to generate a CI workflow,")
        print("or --binary path/to/compiled_binary to assemble IPA locally.")
        print()
        print("Quick start:")
        print("  python build_ipa_remote.py --github-actions")
        print("  # Push to GitHub, run Actions, download artifact")
        print("  # Sign with: codesign or ios-app-signer")


if __name__ == "__main__":
    main()
