#!/usr/bin/env python3
"""Start isolated LongMuch frontend and backend for verification."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HELPERS = Path(__file__).resolve().parent
SKILL_DIR = HELPERS.parent
REPO_ROOT = SKILL_DIR.parent.parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
BACKEND_DIR = REPO_ROOT / "backend"
ARTIFACTS_DIR = SKILL_DIR / "artifacts"
CURRENT_RUN_FILE = SKILL_DIR / ".current-run"
DAEMONIZE = HELPERS / "daemonize.py"
FORBIDDEN_FE = {"3000"}
FORBIDDEN_BE = {"8000"}
FE_PORTS = list(range(3457, 3465))
BE_PORTS = list(range(8015, 8023))


def die(msg: str) -> None:
    sys.stderr.write(f"verify-haystack: {msg}\n")
    sys.exit(1)


def listen_pid(port: int) -> str:
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return ""
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if len(lines) < 2:
        return ""
    return lines[1].split()[1]


def listen_cmd(port: int) -> str:
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return ""
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if len(lines) < 2:
        return ""
    return lines[1].split()[0]


def snapshot(port: int) -> str:
    return f"port={port} pid={listen_pid(port) or 'none'} cmd={listen_cmd(port) or 'none'}"


def pick_port(candidates: list[int], forbidden: set[str], kind: str) -> int:
    for p in candidates:
        if str(p) in forbidden:
            continue
        if not listen_pid(p):
            return p
    die(f"no free {kind} isolation port in {candidates[0]}-{candidates[-1]}")
    raise SystemExit(1)


def pgid_of(pid: str) -> str:
    try:
        return subprocess.check_output(["ps", "-o", "pgid=", "-p", pid], text=True).strip()
    except subprocess.CalledProcessError:
        return ""


def descendant(child: str, ancestor: str) -> bool:
    if not child or not ancestor:
        return False
    walk = child
    for _ in range(12):
        if walk == ancestor:
            return True
        try:
            walk = subprocess.check_output(["ps", "-o", "ppid=", "-p", walk], text=True).strip()
        except subprocess.CalledProcessError:
            return False
        if not walk or walk in {"0", "1"}:
            return False
    return False


def curl_code(url: str, dest: Path, timeout: int = 3) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["curl", "-sS", "-o", str(dest), "-w", "%{http_code}", "--max-time", str(timeout), url],
            capture_output=True,
            text=True,
        )
        return (proc.stdout or "").strip() or "000"
    except Exception:
        return "000"


def kill_tree(pid: str) -> None:
    if not pid:
        return
    pgid = pgid_of(pid)
    if pgid:
        subprocess.run(["kill", "--", f"-{pgid}"], check=False)
    subprocess.run(["kill", pid], check=False)


def which(name: str) -> str:
    path = shutil.which(name)
    if not path:
        die(f"{name} not on PATH")
    return path


def wait_pidfile(path: Path, seconds: float = 2.0) -> str:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return path.read_text(encoding="utf-8").strip()
        time.sleep(0.2)
    die(f"pidfile not written: {path}")
    raise SystemExit(1)


def write_barrel() -> tuple[int, Path]:
    index = FRONTEND_DIR / "app" / "components" / "index.ts"
    if index.exists():
        return 0, index
    index.write_text(
        "// verify-haystack scaffolding (not product code).\n"
        "// page.tsx imports from './components'; App Router has no barrel file.\n"
        'export { Card } from "./card";\n'
        'export { DataTable } from "./data-table";\n'
        'export { Sparkline } from "./sparkline";\n',
        encoding="utf-8",
    )
    print(f"verify-haystack: wrote verification scaffolding {index}")
    return 1, index


def main() -> None:
    if not (FRONTEND_DIR / "package.json").is_file():
        die(f"not the haystack repo (missing frontend/package.json): {REPO_ROOT}")
    if not (BACKEND_DIR / "app" / "main.py").is_file():
        die(f"not the haystack repo (missing backend/app/main.py): {REPO_ROOT}")

    run_id = os.environ.get("RUN_ID") or time.strftime("%Y%m%d%H%M%S") + f"-{os.getpid()}"
    run_dir = Path(f"/tmp/haystack-verify-{run_id}")
    run_dir.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    fe_port = pick_port(FE_PORTS, FORBIDDEN_FE, "frontend")
    be_port = pick_port(BE_PORTS, FORBIDDEN_BE, "backend")
    fe_origin = f"http://127.0.0.1:{fe_port}"
    be_origin = f"http://127.0.0.1:{be_port}"

    iso_3000 = snapshot(3000)
    iso_8000 = snapshot(8000)
    pid_3000 = listen_pid(3000) or "none"
    pid_8000 = listen_pid(8000) or "none"
    (run_dir / "isolation-before.txt").write_text(iso_3000 + "\n" + iso_8000 + "\n", encoding="utf-8")

    os.chdir(REPO_ROOT)
    next_bin = FRONTEND_DIR / "node_modules" / ".bin" / "next"
    if not next_bin.exists():
        installer = HELPERS / "ensure-frontend"
        if installer.exists():
            print("verify-haystack: running helpers/ensure-frontend")
            subprocess.check_call([str(installer)], cwd=str(FRONTEND_DIR))
        if not next_bin.exists():
            die("frontend next binary missing; run helpers/ensure-frontend")

    scaffold, components_index = write_barrel()
    uv_bin = which("uv")
    subprocess.check_call([uv_bin, "sync"], cwd=str(BACKEND_DIR))

    env = os.environ.copy()
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    env["BACKEND_ORIGIN"] = be_origin
    env["HAYSTACK_BACKEND_ORIGIN"] = be_origin
    fe_pidfile = run_dir / "frontend.pid"
    fe_logfile = run_dir / "frontend.log"
    subprocess.check_call(
        [
            sys.executable,
            str(DAEMONIZE),
            str(fe_pidfile),
            str(fe_logfile),
            str(FRONTEND_DIR),
            str(next_bin),
            "dev",
            "--hostname",
            "127.0.0.1",
            "--port",
            str(fe_port),
        ],
        env=env,
    )
    fe_pid = wait_pidfile(fe_pidfile)

    be_pidfile = run_dir / "backend.pid"
    be_logfile = run_dir / "backend.log"
    be_env = os.environ.copy()
    subprocess.check_call(
        [
            sys.executable,
            str(DAEMONIZE),
            str(be_pidfile),
            str(be_logfile),
            str(BACKEND_DIR),
            uv_bin,
            "run",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(be_port),
        ],
        env=be_env,
    )
    be_pid = be_pidfile.read_text(encoding="utf-8").strip() if be_pidfile.exists() else ""

    print(f"verify-haystack: waiting for frontend {fe_origin} (pid {fe_pid})")
    body = run_dir / "ready-fe.html"
    fe_ready = False
    for _ in range(90):
        code = curl_code(fe_origin + "/", body)
        text = body.read_text(encoding="utf-8", errors="replace") if body.exists() else ""
        if code == "200" and "LongMuch" in text:
            fe_ready = True
            break
        time.sleep(1)
    if not fe_ready:
        sys.stderr.write("----- frontend.log -----\n")
        if fe_logfile.exists():
            sys.stderr.write("\n".join(fe_logfile.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]) + "\n")
        kill_tree(fe_pid)
        kill_tree(be_pid)
        die(f"isolated frontend did not become ready on {fe_origin}. See {fe_logfile}")

    fe_listen = listen_pid(fe_port)
    if not fe_listen:
        die(f"nothing listening on frontend port {fe_port} after ready check")
    if fe_listen != fe_pid and not descendant(fe_listen, fe_pid):
        die(f"frontend listen PID {fe_listen} on :{fe_port} is not a descendant of our PID {fe_pid}")
    fe_pgid = pgid_of(fe_pid)

    print(f"verify-haystack: waiting for backend {be_origin} (pid {be_pid or 'none'})")
    backend_ok = "0"
    be_listen = ""
    be_pgid = ""
    if be_pid:
        hz = run_dir / "ready-be.json"
        for _ in range(40):
            if curl_code(be_origin + "/health", hz) == "200":
                backend_ok = "1"
                break
            time.sleep(1)
        if backend_ok == "1":
            be_listen = listen_pid(be_port)
            if not be_listen:
                die(f"nothing listening on backend port {be_port} after health 200")
            if be_listen != be_pid and not descendant(be_listen, be_pid):
                die(f"backend listen PID {be_listen} on :{be_port} is not a descendant of our PID {be_pid}")
            be_pgid = pgid_of(be_pid)
        else:
            sys.stderr.write(
                f"verify-haystack: warning: backend did not become ready on {be_origin}; homepage proof can still run\n"
            )

    run_env = "\n".join(
        [
            f"RUN_ID={run_id}",
            f"RUN_DIR={run_dir}",
            f"REPO_ROOT={REPO_ROOT}",
            f"SKILL_DIR={SKILL_DIR}",
            f"FRONTEND_PORT={fe_port}",
            f"FRONTEND_ORIGIN={fe_origin}",
            f"FRONTEND_PID={fe_pid}",
            f"FRONTEND_LISTEN_PID={fe_listen}",
            f"FRONTEND_PGID={fe_pgid}",
            f"BACKEND_PORT={be_port}",
            f"BACKEND_ORIGIN={be_origin}",
            f"BACKEND_PID={be_pid}",
            f"BACKEND_LISTEN_PID={be_listen}",
            f"BACKEND_PGID={be_pgid}",
            f"BACKEND_OK={backend_ok}",
            f"SCAFFOLD_COMPONENTS_INDEX={scaffold}",
            f"COMPONENTS_INDEX={components_index}",
            f"USER_3000_PID_BEFORE={pid_3000}",
            f"USER_8000_PID_BEFORE={pid_8000}",
            "",
        ]
    )
    (run_dir / "run.env").write_text(run_env, encoding="utf-8")
    CURRENT_RUN_FILE.write_text(str(run_dir) + "\n", encoding="utf-8")
    (ARTIFACTS_DIR / "launch.env").write_text(run_env, encoding="utf-8")
    shutil.copy(run_dir / "isolation-before.txt", ARTIFACTS_DIR / "isolation-before.txt")

    print("verify-haystack launch ok")
    print(f"RUN_ID={run_id}")
    print(f"FRONTEND_ORIGIN={fe_origin}")
    print(f"FRONTEND_PORT={fe_port}")
    print(f"FRONTEND_PID={fe_pid}")
    print(f"FRONTEND_LISTEN_PID={fe_listen}")
    print(f"FRONTEND_PGID={fe_pgid}")
    print(f"BACKEND_ORIGIN={be_origin}")
    print(f"BACKEND_PORT={be_port}")
    print(f"BACKEND_PID={be_pid or 'none'}")
    print(f"BACKEND_LISTEN_PID={be_listen or 'none'}")
    print(f"BACKEND_PGID={be_pgid or 'none'}")
    print(f"BACKEND_OK={backend_ok}")
    print(f"SCAFFOLD_COMPONENTS_INDEX={scaffold}")
    print(f"RUN_DIR={run_dir}")
    print(f"3000_before={iso_3000}")
    print(f"8000_before={iso_8000}")


if __name__ == "__main__":
    main()
