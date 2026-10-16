"""Boot the FastAPI server as a subprocess and check the /health endpoint.

Run directly:

    .venv/bin/python tests/test_api/test_health.py

It launches `python -m uvicorn api.main:app` (with src/ on PYTHONPATH),
polls /health until it responds, asserts 200 {"status": "ok"}, then shuts
the server down.
"""

import os
import sys
import time
import subprocess
import urllib.request
import urllib.error

# --- paths ---------------------------------------------------------------
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
SRC = os.path.join(ROOT, "src")

HOST = "127.0.0.1"
PORT = 8123
BASE_URL = f"http://{HOST}:{PORT}"


def _start_server() -> subprocess.Popen:
    """Launch uvicorn via `python -m uvicorn` so it works even when the
    .venv console scripts have a broken shebang."""
    env = os.environ.copy()
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=env,
    )


def _wait_for_health(timeout: float = 20.0):
    """Poll /health until it returns, or raise after `timeout` seconds."""
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as resp:
                return resp.status, resp.read().decode()
        except (urllib.error.URLError, ConnectionError) as e:
            last_err = e
            time.sleep(0.4)
    raise RuntimeError(f"server not healthy within {timeout}s (last error: {last_err})")


def test_health():
    print(f"Starting server: {sys.executable} -m uvicorn api.main:app --port {PORT}")
    proc = _start_server()
    try:
        status, body = _wait_for_health()
        assert status == 200, f"unexpected status: {status}"
        assert "ok" in body, f"unexpected body: {body}"
        print(f"GET /health -> {status} {body}")
        print("Health check PASSED ✅")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Server stopped.")


if __name__ == "__main__":
    test_health()
