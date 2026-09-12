"""Proves this machine's Blender can round-trip a USDZ.

Do not check `filter_glob` instead. It reads `*.usd` on 4.0.2, which cannot
import USDZ, and also on 5.2.1, which can. The only reliable test is to write
a file and read it back.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
"""Where the macOS app installs it. `$BLENDER` and `blender` on `PATH` come first."""

SCRIPT = """
import bpy
p = {path!r}
bpy.ops.wm.usd_export(filepath=p)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.usd_import(filepath=p)
print("USDZ_ROUNDTRIP", "OK" if "Cube" in bpy.data.objects else "BROKEN")
"""


def blender_path() -> str:
    """`$BLENDER`, then `blender` on `PATH`, then the macOS app bundle."""
    for candidate in (os.environ.get("BLENDER"), shutil.which("blender"), BLENDER):
        if candidate and pathlib.Path(candidate).exists():
            return candidate
    raise FileNotFoundError(
        f"No Blender in $BLENDER, on PATH, or at {BLENDER}. Install it with:\n"
        "    brew install --cask --force blender"
    )


def check() -> tuple[bool, str]:
    exe = blender_path()
    version = subprocess.run(
        [exe, "--version"], capture_output=True, text=True, timeout=120
    ).stdout.splitlines()[0].strip()

    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / "roundtrip.usdz"
        result = subprocess.run(
            [exe, "--background", "--python-expr", SCRIPT.format(path=str(target))],
            capture_output=True,
            text=True,
            timeout=300,
        )
    ok = "USDZ_ROUNDTRIP OK" in result.stdout
    return ok, version


def main() -> int:
    try:
        ok, version = check()
    except FileNotFoundError as exc:
        print(exc)
        return 1
    print(f"{version}: USDZ import {'works' if ok else 'is broken'}")
    if not ok:
        print("Upgrade with: brew install --cask --force blender")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
