import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "VideoDownloader"


def main():
    try:
        import PyInstaller
    except ImportError:
        sys.exit("PyInstaller is missing. Install it with: pip install pyinstaller")

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name", APP_NAME,
        "--collect-all", "customtkinter",
        "--collect-all", "yt_dlp",
        "--collect-all", "yt_dlp_ejs",
        "--hidden-import", "PIL._tkinter_finder",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ]
    if sys.platform != "darwin":
        command.append("--onefile")

    ffmpeg = ROOT / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if ffmpeg.is_file():
        command += ["--add-binary", f"{ffmpeg}{os.pathsep}."]
    else:
        print("Note: no ffmpeg next to build.py, so it will not be bundled.")

    icon_name = {"win32": "icon.ico", "darwin": "icon.icns"}.get(sys.platform)
    if icon_name and (ROOT / icon_name).is_file():
        command += ["--icon", str(ROOT / icon_name)]

    command.append(str(ROOT / "main.py"))
    subprocess.run(command, check=True, cwd=ROOT)
    print(f"Done. Look in {ROOT / 'dist'}")


if __name__ == "__main__":
    main()
