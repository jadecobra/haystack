#!/usr/bin/env python3
from __future__ import annotations
import os, shutil, subprocess, sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent
SKILL_DIR = HELPERS.parent
REPO_ROOT = SKILL_DIR.parent.parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"

def die(msg):
    sys.stderr.write("verify-haystack: " + msg + "\n")
    sys.exit(1)

def main():
    os.chdir(FRONTEND_DIR)
    next_bin = FRONTEND_DIR / "node_modules" / ".bin" / "next"
    if next_bin.exists():
        print("verify-haystack: next already present")
        return
    env = os.environ.copy()
    env["npm_config_package_lock"] = "false"
    pkg = env.get("VERIFY_PKG")
    extra = env.get("VERIFY_PNPM")
    if extra:
        subprocess.run([extra, "i", "--ignore-scripts"], cwd=str(FRONTEND_DIR), env=env, check=False)
    if not pkg:
        die("VERIFY_PKG is not set")
    minimal = HELPERS / "minimal-package.json"
    orig = FRONTEND_DIR / "package.json"
    backup = FRONTEND_DIR / "package.json.verify-bak"
    if minimal.exists() and orig.exists():
        shutil.copy2(orig, backup)
        shutil.copy2(minimal, orig)
    try:
        if not next_bin.exists():
            subprocess.check_call([pkg, "i", "--ignore-scripts"], cwd=str(FRONTEND_DIR), env=env)
    finally:
        if backup.exists():
            shutil.move(str(backup), str(orig))
    if not next_bin.exists():
        die("next binary still missing after ensure-frontend")
    print("verify-haystack: frontend deps ready")

if __name__ == "__main__":
    main()
