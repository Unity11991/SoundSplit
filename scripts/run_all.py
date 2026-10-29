import sys
import os
import subprocess
import signal
import time
import socket
import webbrowser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

def get_local_ip() -> str:
    """Detect the active Wi-Fi or local network IPv4 address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def main():
    local_ip = get_local_ip()

    print("\n==================================================================")
    print("      SoundSplit — AI Voice & Music Isolator")
    print("==================================================================")

    # Detect python executable in .venv or system
    venv_python = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        venv_python = ROOT_DIR / ".venv" / "bin" / "python"
    python_cmd = str(venv_python) if venv_python.exists() else sys.executable

    # Check node / npm
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"

    # Set environment variables
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT_DIR / 'apps' / 'api'};{ROOT_DIR}"
    env["LOCAL_IP"] = local_ip

    print(f"\n[1/2] Starting AI Backend Server on port 8000...")
    api_process = subprocess.Popen(
        [python_cmd, "-m", "uvicorn", "app.main:app", "--app-dir", "apps/api", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=str(ROOT_DIR),
        env=env
    )


    print(f"[2/2] Starting Web Studio on port 3000...")
    web_process = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=str(ROOT_DIR / "apps" / "web"),
        env=env
    )

    # Wait 2.5 seconds for services to initialize
    time.sleep(2.5)

    print("\n" + "=" * 68)
    print("           SoundSplit is Live & Ready!")
    print("=" * 68)
    print(f"  -> ON THIS COMPUTER:  http://localhost:3000")
    if local_ip != "127.0.0.1":
        print(f"  -> ON YOUR MOBILE:    http://{local_ip}:3000")
        print("\n  [Mobile Tip] Connect your phone to the same Wi-Fi network")
        print(f"  and open Chrome or Safari:  http://{local_ip}:3000")
    print("=" * 68)
    print("  Press Ctrl+C anytime to stop all servers.\n")

    # Open browser on computer automatically
    try:
        webbrowser.open("http://localhost:3000")
    except Exception:
        pass

    def shutdown(sig, frame):
        print("\nStopping SoundSplit services...")
        try:
            api_process.terminate()
        except Exception:
            pass
        try:
            web_process.terminate()
        except Exception:
            pass
        print("All servers stopped successfully.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Keep alive while child processes run
    try:
        while True:
            time.sleep(1)
            if api_process.poll() is not None or web_process.poll() is not None:
                break
    except KeyboardInterrupt:
        shutdown(None, None)

if __name__ == "__main__":
    main()
