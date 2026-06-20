"""One-window development launcher for backend and frontend."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"


def _npm_cmd() -> str:
    return "npm.cmd" if sys.platform.startswith("win") else "npm"


def _spawn(
    name: str,
    argv: list[str],
    cwd: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    thread = threading.Thread(target=_pipe_output, args=(name, proc), daemon=True)
    thread.start()
    return proc


def _port_available(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
    except OSError:
        return False
    return True


def _choose_backend_port(host: str, requested: int) -> int:
    if _port_available(host, requested):
        return requested
    for candidate in range(8200, 8300):
        if _port_available(host, candidate):
            return candidate
    raise RuntimeError(f"No available backend port for {host}; tried {requested}, 8200-8299.")


def _pipe_output(name: str, proc: subprocess.Popen[str]) -> None:
    if proc.stdout is None:
        return
    for line in proc.stdout:
        print(f"[{name}] {line.rstrip()}", flush=True)


def _terminate(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except OSError:
        pass


def main() -> int:
    processes: list[subprocess.Popen[str]] = []
    backend_host = os.environ.get("BACKEND_HOST", "127.0.0.1")
    requested_backend_port = int(os.environ.get("BACKEND_PORT", "8000"))
    backend_port = _choose_backend_port(backend_host, requested_backend_port)
    backend_base_url = f"http://{backend_host}:{backend_port}"

    commands = [
        (
            f"backend:{backend_port}",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.app:app",
                "--host",
                backend_host,
                "--port",
                str(backend_port),
                "--reload",
                "--reload-dir",
                "backend",
                "--reload-include=*.py",
            ],
            ROOT,
        ),
        (
            "frontend",
            [
                _npm_cmd(),
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                "5173",
                "--strictPort",
                "--open",
            ],
            FRONTEND_DIR,
        ),
    ]

    stop = False

    def _request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True
        for proc in processes:
            _terminate(proc)

    signal.signal(signal.SIGINT, _request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _request_stop)

    try:
        for command in commands:
            name, argv, cwd = command[:3]
            extra_env = command[3] if len(command) > 3 else None
            print(f"==> Starting {name}", flush=True)
            processes.append(_spawn(name, argv, cwd, extra_env=extra_env))

        print("", flush=True)
        if backend_port != requested_backend_port:
            print(f"Requested backend port {requested_backend_port} is unavailable; using {backend_port}.", flush=True)
        print("不平 (Buping) is starting:", flush=True)
        print(f"  Backend:  {backend_base_url}", flush=True)
        print("  Frontend: http://127.0.0.1:5173", flush=True)
        print("Press Ctrl+C to stop all processes.", flush=True)

        while not stop:
            for proc in processes:
                code = proc.poll()
                if code is not None:
                    print(f"process exited with code {code}; stopping dev stack", flush=True)
                    stop = True
                    break
            if stop:
                break
            threading.Event().wait(0.5)
    finally:
        for proc in processes:
            _terminate(proc)
        for proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("Dev stack stopped.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
