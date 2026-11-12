"""python -m ai_server            start the server
python -m ai_server token        print a new random access token
python -m ai_server check        say whether the engine and the model are ready
python -m ai_server address      print the address to give the game PC (this PC's Tailscale IP)"""
from __future__ import annotations

import secrets
import sys


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "serve"
    if cmd == "token":
        print(secrets.token_urlsafe(32))
        return 0
    from .config import Settings, detect_tailscale_ip
    if cmd == "address":
        ip = detect_tailscale_ip()
        if not ip:
            print("This PC has no Tailscale address yet: sign in to Tailscale first.")
            return 1
        port = __import__("os").environ.get("AI_PORT", "8765")
        print(f"FIXIT_AI_URL=http://{ip}:{port}   (or use this PC's MagicDNS name instead of {ip})")
        return 0
    s = Settings.from_env()
    if cmd == "check":
        import asyncio

        from .backend import OllamaBackend

        async def run():
            b = OllamaBackend(s.backend_url)
            v = await b.version()
            print(f"engine: {'up, version ' + v if v else 'NOT reachable at ' + s.backend_url}")
            print(f"model {s.model}: {'installed' if s.model in await b.installed() else 'NOT installed'}")
            print(f"listen address: {s.host}:{s.port}")
            await b.aclose()
        asyncio.run(run())
        return 0
    import uvicorn

    from .app import create_app
    print(f"AI server on http://{s.host}:{s.port}  model={s.model}  engine={s.backend_url}  (tailnet and this PC only)")
    uvicorn.run(create_app(s), host=s.host, port=s.port, log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
