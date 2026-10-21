"""Build script to compile LTC AutoClicker v2 into a standalone Windows .exe."""
import os
import subprocess
import sys
import shutil
import argparse


def install_application(exe_path, base_dir, icon_path):
    """Installs the compiled binary into %LOCALAPPDATA% and registers the Start Menu shortcut."""
    print("\n[*] Starting application installation...")
    # Stop running instances so binary files can be overwritten cleanly
    subprocess.run(["taskkill", "/F", "/IM", "LTC-AutoClicker.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        print("[!] Warning: LOCALAPPDATA environment variable not found; skipping installation.")
        return False

    installed_dir = os.path.join(local_appdata, "Programs", "LTC-AutoClicker")
    os.makedirs(installed_dir, exist_ok=True)
    installed_exe = os.path.join(installed_dir, "LTC-AutoClicker.exe")
    try:
        shutil.copy2(exe_path, installed_exe)
        print(f"[+] Installed App updated: {installed_exe}")
    except Exception as e:
        print(f"[!] Warning: Could not overwrite {installed_exe}: {e}")
        return False

    # Copy icon to installed folder for shortcuts
    installed_assets = os.path.join(installed_dir, "assets")
    os.makedirs(installed_assets, exist_ok=True)
    shutil.copy2(icon_path, os.path.join(installed_assets, "icon.ico"))

    # Create/Update canonical Start Menu shortcut ("LTC AutoClicker")
    try:
        from win32com.client import Dispatch
        shell = Dispatch("WScript.Shell")
        programs_dir = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")

        # Remove legacy duplicate shortcut if present
        legacy_lnk = os.path.join(programs_dir, "LTC Auto Clicker.lnk")
        if os.path.exists(legacy_lnk):
            try:
                os.remove(legacy_lnk)
            except Exception:
                pass

        canonical_lnk = os.path.join(programs_dir, "LTC AutoClicker.lnk")
        shortcut = shell.CreateShortcut(canonical_lnk)
        shortcut.TargetPath = installed_exe
        shortcut.WorkingDirectory = installed_dir
        shortcut.IconLocation = f"{os.path.join(installed_assets, 'icon.ico')},0"
        shortcut.Description = "LTC AutoClicker"
        shortcut.save()
        print(f"[+] Canonical Shortcut refreshed: {canonical_lnk}")
        return True
    except Exception as err:
        print(f"[!] Warning creating shortcut: {err}")
        return False


def build(install=False):
    base_dir = os.path.abspath(os.path.dirname(__file__))
    dist_dir = os.path.join(base_dir, "dist")
    icon_path = os.path.join(base_dir, "assets", "icon.ico")
    assets_dir = os.path.join(base_dir, "assets")

    print("[*] Starting LTC AutoClicker v2 standalone build...")

    spec_path = os.path.join(base_dir, "LTC-AutoClicker.spec")

    # PyInstaller arguments using portable spec
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconfirm",
        spec_path
    ]

    print(f"[*] Running PyInstaller command: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=base_dir)

    if res.returncode == 0:
        exe_path = os.path.join(dist_dir, "LTC-AutoClicker.exe")
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n[+] Build SUCCESSFUL!")
            print(f"[+] Output Executable: {exe_path}")
            print(f"[+] Size: {size_mb:.2f} MB")

            if install:
                install_application(exe_path, base_dir, icon_path)
            else:
                print("[i] Standalone build complete. To install to Start Menu & %LOCALAPPDATA%, re-run with: python build.py --install")
            return 0
        else:
            print("[-] Error: Executable file was not found in dist folder.")
            return 1
    else:
        print(f"[-] PyInstaller failed with exit code {res.returncode}")
        return res.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build standalone LTC AutoClicker Windows binary.")
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install compiled binary to %LOCALAPPDATA% and register Start Menu shortcut."
    )
    args = parser.parse_args()
    sys.exit(build(install=args.install))
