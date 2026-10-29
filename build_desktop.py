"""
Plotline Desktop Build Utility
Bundles the Plotline backend and web interface into a single standalone executable.
Requires: pip install pyinstaller
"""

import os
import subprocess
import sys

def build():
    print("==========================================")
    print("   Plotline Desktop Executable Builder   ")
    print("==========================================")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    web_dir = os.path.join(base_dir, "web")

    # Command to package with PyInstaller
    separator = ";" if sys.platform == "win32" else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=Plotline",
        "--onefile",
        f"--add-data={web_dir}{separator}web",
        "--icon=web/icon.png",
        "plotline.py"
    ]

    print(f"Running: {' '.join(cmd)}")
    try:
        subprocess.check_call(cmd)
        print("\n[SUCCESS] Standalone executable generated in dist/Plotline")
    except Exception as e:
        print(f"\n[INFO] PyInstaller not installed or build failed: {e}")
        print("To build manually, run: pip install pyinstaller && python build_desktop.py")

if __name__ == "__main__":
    build()
