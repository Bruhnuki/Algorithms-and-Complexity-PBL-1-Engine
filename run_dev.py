"""Run the game server: python run_dev.py

  FIXIT_HOST   127.0.0.1 (default: this PC only) | tailscale (this PC's Tailscale address, so other people on your tailnet can play) | a specific address
  PORT         8000
  MODEL_URL    optional: live teammate chat through the AI server
It never listens on every interface (0.0.0.0) unless FIXIT_ALLOW_ANY_BIND=1.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.dirname(__file__))
import uvicorn  # noqa: E402

os.environ.setdefault("INSTRUCTOR_CODE", "dev-instructor")


def listen_address() -> str:
    host = os.environ.get("FIXIT_HOST", "127.0.0.1")
    if host == "tailscale":
        from ai_server.config import detect_tailscale_ip
        host = detect_tailscale_ip() or ""
        if not host:
            raise SystemExit("This PC has no Tailscale address: sign in to Tailscale first, or leave FIXIT_HOST unset to play on this PC only.")
    if host in ("0.0.0.0", "::") and os.environ.get("FIXIT_ALLOW_ANY_BIND") != "1":
        raise SystemExit("Refusing to listen on every interface. Use FIXIT_HOST=tailscale or 127.0.0.1.")
    return host


if __name__ == "__main__":
    host, port = listen_address(), int(os.environ.get("PORT", "8000"))
    print(f"Game server on http://{host}:{port}", flush=True)
    uvicorn.run("fixit.api.app:app_from_env", factory=True, host=host, port=port)
