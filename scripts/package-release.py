#!/usr/bin/env python3
"""Package the local Mac build and sign update metadata with a Keychain-only key."""
import hashlib
import json
import plistlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT.parent / "Daybook.app"
OUT = ROOT / "release"
OUT.mkdir(exist_ok=True)
with (APP / "Contents/Info.plist").open("rb") as file:
    version = plistlib.load(file)["CFBundleShortVersionString"]
subprocess.run(["codesign", "--verify", "--deep", "--strict", str(APP)], check=True)
archive = OUT / "Daybook-update.zip"
if archive.exists():
    archive.unlink()
subprocess.run(
    ["ditto", "-c", "-k", "--keepParent", str(APP), str(archive)], check=True
)
manifest = {
    "version": version,
    "minimumSystemVersion": "13.0.0",
    "archive": archive.name,
    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "size": archive.stat().st_size,
}
(OUT / "meridian-update.json").write_text(
    json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
)
helper = ROOT.parents[1] / "work/meridian-sign-update"
cache = ROOT.parents[1] / "work/DaybookModuleCache"
subprocess.run(
    [
        "swiftc",
        "-module-cache-path",
        str(cache),
        str(ROOT / "scripts/SignUpdate.swift"),
        "-o",
        str(helper),
    ],
    check=True,
)
subprocess.run(
    [
        str(helper),
        "sign",
        str(OUT / "meridian-update.json"),
        str(OUT / "meridian-update.sig"),
        str(ROOT / "macos/Updates/public-key.txt"),
    ],
    check=True,
)
(OUT / "SHA256SUMS.txt").write_text(
    "".join(
        hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n"
        for p in [archive, OUT / "meridian-update.json", OUT / "meridian-update.sig"]
    )
)
print("Signed local update assets for Daybook", version)
