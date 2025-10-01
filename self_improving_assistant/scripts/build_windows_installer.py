"""
Builds a Windows installer EXE that bundles the project and runs the PowerShell installer.
Requires: pyinstaller (run this on Windows).

Usage:
  py -3 -m pip install pyinstaller
  py -3 scripts/build_windows_installer.py
  -> dist/SIA-Installer.exe
"""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
STUB = SCRIPTS / "_bootstrap_installer.py"

# Write a bootstrap that copies bundled payload to install dir, then runs the PowerShell installer there
STUB.write_text(
    (
        "import subprocess, sys, os, shutil\n"
        "base = getattr(sys, '_MEIPASS', os.path.dirname(sys.argv[0]))\n"
        "payload = os.path.join(base, 'payload')\n"
        "inst_root = os.path.join(os.environ.get('USERPROFILE') or os.path.expanduser('~'), 'SIA', 'self_improving_assistant')\n"
        "os.makedirs(inst_root, exist_ok=True)\n"
        "# Copy payload -> install dir (overwrite)\n"
        "for root, dirs, files in os.walk(payload):\n"
        "    rel = os.path.relpath(root, payload)\n"
        "    dst_root = os.path.join(inst_root, rel) if rel != '.' else inst_root\n"
        "    os.makedirs(dst_root, exist_ok=True)\n"
        "    for f in files:\n"
        "        src = os.path.join(root, f)\n"
        "        dst = os.path.join(dst_root, f)\n"
        "        try:\n"
        "            shutil.copy2(src, dst)\n"
        "        except Exception:\n"
        "            pass\n"
        "# Run installer PS1 from installed location\n"
        "ps1 = os.path.join(inst_root, 'scripts', 'install_and_setup.ps1')\n"
        "p = 'powershell.exe'\n"
        "subprocess.run([p, '-ExecutionPolicy', 'Bypass', '-File', ps1], check=True)\n"
    ),
    encoding="utf-8",
)

# Collect add-data entries for all project files except venv/git/build artifacts
EXCLUDES = {'.venv', '.git', 'build', 'dist', '__pycache__', '.vscode'}
add_data = []
for path in ROOT.rglob('*'):
    rel = path.relative_to(ROOT)
    parts = set(rel.parts)
    if parts & EXCLUDES:
        continue
    if path.is_dir():
        continue
    # Destination inside package under 'payload/<relpath with forward slashes>'
    dest = f"payload/{rel.as_posix()}"
    # PyInstaller expects Windows-style separator ';' between src and dest
    spec = f"{path};{dest}"
    add_data.append(spec)

cmd = [
    "py", "-3", "-m", "PyInstaller",
    "--noconfirm",
    "--onefile",
    "--name", "SIA-Installer",
]

for spec in add_data:
    cmd.extend(["--add-data", spec])

cmd.append(str(STUB))

print("Running:", " ".join(cmd))
subprocess.check_call(cmd, cwd=str(ROOT))
print("Done. Check dist/SIA-Installer.exe")
