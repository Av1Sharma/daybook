#!/usr/bin/env python3
"""Build a local Mac app with its Python dependencies bundled. No credentials included."""
from pathlib import Path
import os
import shutil
import plistlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT.parent / "Daybook.app"
RESOURCES = APP / "Contents/Resources"
BIN = APP / "Contents/MacOS"
BIN.mkdir(parents=True, exist_ok=True)
RESOURCES.mkdir(parents=True, exist_ok=True)
CACHE = ROOT.parents[1] / "work/DaybookModuleCache"
CACHE.mkdir(parents=True, exist_ok=True)
subprocess.run(
    [
        "swiftc",
        "-O",
        "-module-cache-path",
        str(CACHE),
        str(ROOT / "macos/Daybook.swift"),
        str(ROOT / "macos/DesktopCore.swift"),
        str(ROOT / "macos/DesktopCompanion.swift"),
        str(ROOT / "macos/Updates/Updater.swift"),
        *[
            str(ROOT / "macos/Updates" / name)
            for name in (
                "UpdateCore.swift",
                "UpdatePublicKey.swift",
                "InstallCore.swift",
            )
        ],
        "-o",
        str(BIN / "Daybook"),
    ],
    check=True,
)
subprocess.run(
    [
        "swiftc",
        "-O",
        "-module-cache-path",
        str(CACHE),
        *[
            str(ROOT / "macos/Updates" / name)
            for name in (
                "InstallerMain.swift",
                "UpdateCore.swift",
                "UpdatePublicKey.swift",
                "InstallCore.swift",
            )
        ],
        "-o",
        str(BIN / "DaybookInstaller"),
    ],
    check=True,
)
subprocess.run(
    ["codesign", "--force", "--sign", "-", str(BIN / "DaybookInstaller")], check=True
)
with (APP / "Contents/Info.plist").open("wb") as f:
    plistlib.dump(
        {
            "CFBundleExecutable": "Daybook",
            "CFBundleIdentifier": "com.avisharma.meridian",
            "CFBundleName": "Daybook",
            "CFBundleDisplayName": "Daybook",
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": "2.0.0",
            "CFBundleVersion": "200",
            "LSMinimumSystemVersion": "13.0",
            "NSHighResolutionCapable": True,
            "NSPrincipalClass": "NSApplication",
            "CFBundleIconFile": "Daybook.icns",
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        },
        f,
    )
icons = CACHE.parent / "Daybook.iconset"
subprocess.run(
    [
        "swift",
        "-module-cache-path",
        str(CACHE),
        str(ROOT / "scripts/Icon.swift"),
        str(icons),
    ],
    check=True,
)
subprocess.run(
    ["iconutil", "-c", "icns", str(icons), "-o", str(RESOURCES / "Daybook.icns")],
    check=True,
)
runtime = RESOURCES / "runtime"
if not (runtime / "bin/python3").exists():
    subprocess.run([sys.executable, "-m", "venv", "--copies", str(runtime)], check=True)
subprocess.run(
    [
        str(runtime / "bin/python3"),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        str(ROOT),
    ],
    check=True,
)
# macOS bundle verification rejects virtualenv symlinks that point outside the bundle.
for path in runtime.rglob("*"):
    if path.is_symlink():
        target = path.resolve()
        if not target.is_relative_to(APP) and target.is_file():
            path.unlink()
            shutil.copy2(target, path)
subprocess.run(
    [
        "codesign",
        "--force",
        "--sign",
        "-",
        "--identifier",
        "com.avisharma.meridian",
        str(APP),
    ],
    check=True,
)
subprocess.run(["codesign", "--verify", "--deep", "--strict", str(APP)], check=True)
print(APP)
