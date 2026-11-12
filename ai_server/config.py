"""Settings come from environment variables only, so nothing secret or machine-specific lives in code."""
from __future__ import annotations

import ipaddress
import os
import re
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

TAILNET_V4 = ipaddress.ip_network("100.64.0.0/10")
DEFAULT_ALLOW = ("100.64.0.0/10", "127.0.0.0/8", "fd7a:115c:a1e0::/48", "::1/128")


def detect_tailscale_ip() -> str | None:
    """This PC's Tailscale IPv4 address (100.x), or None when Tailscale is not signed in."""
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5).stdout
        for line in out.split():
            if ipaddress.ip_address(line) in TAILNET_V4:
                return line
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    try:   # fall back to the addresses of this machine
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ipaddress.ip_address(ip) in TAILNET_V4:
                return ip
    except (OSError, ValueError):
        pass
    return None


def _tokens() -> tuple[str, ...]:
    toks = [t.strip() for t in os.environ.get("AI_TOKEN", "").split(",") if t.strip()]
    f = os.environ.get("AI_TOKENS_FILE")
    if f and Path(f).exists():
        toks += [ln.strip() for ln in Path(f).read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    return tuple(dict.fromkeys(toks))


@dataclass(frozen=True)
class Settings:
    backend_url: str = "http://127.0.0.1:11434"      # Ollama, localhost only
    engine: str = "ollama"                           # "ollama" or "llamacpp" (llama-server)
    model: str = "qwen3.5:9b"
    allowed_models: tuple[str, ...] = ()             # empty: only `model`
    tokens: tuple[str, ...] = ()                     # bearer tokens; none means the server refuses to start
    host: str = "127.0.0.1"
    port: int = 8765
    max_concurrency: int = 1                         # one request on the GPU at a time
    queue_wait_s: float = 20.0                       # how long an interactive request may wait for its turn
    background_wait_s: float = 600.0                 # how long a pre-generation request may wait
    request_timeout_s: float = 120.0
    keep_alive: str = "10m"                          # the model leaves VRAM after this idle time
    num_ctx: int = 3072
    max_tokens_cap: int = 1000
    max_queue_interactive: int = 16
    max_queue_background: int = 8
    rate_per_min: int = 240                          # per token
    allow_networks: tuple[str, ...] = field(default=DEFAULT_ALLOW)
    require_schema: bool = True                      # every request must say what shape the answer has: no free-form chat through this server
    validate_output: bool = True                     # check the answer against that schema; retry once, then refuse
    max_prompt_chars: int = 14000
    max_output_chars: int = 12000
    think: bool = False                              # reasoning models: skip the hidden thinking (it breaks strict JSON and wastes time)

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ.get
        host = e("AI_BIND", "tailscale")
        if host == "tailscale":
            host = detect_tailscale_ip() or ""
        if host in ("0.0.0.0", "::") and e("AI_ALLOW_ANY_BIND") != "1":
            raise SystemExit("Refusing to listen on every interface. Use AI_BIND=tailscale (default), or 127.0.0.1.")
        if not host:
            raise SystemExit("No Tailscale address found: sign in to Tailscale, or set AI_BIND=127.0.0.1 for local testing.")
        model = e("AI_MODEL", cls.model)
        extra = tuple(m.strip() for m in e("AI_ALLOWED_MODELS", "").split(",") if m.strip())
        s = cls(backend_url=e("AI_BACKEND_URL", cls.backend_url), engine=e("AI_ENGINE", cls.engine), model=model, allowed_models=extra or (model,), tokens=_tokens(), host=host,
                port=int(e("AI_PORT", cls.port)), max_concurrency=int(e("AI_CONCURRENCY", cls.max_concurrency)), keep_alive=e("AI_KEEP_ALIVE", cls.keep_alive),
                num_ctx=int(e("AI_NUM_CTX", cls.num_ctx)), request_timeout_s=float(e("AI_REQUEST_TIMEOUT", cls.request_timeout_s)),
                think=e("AI_THINK", "0") == "1")
        if s.engine not in ("ollama", "llamacpp"):
            raise SystemExit("AI_ENGINE must be ollama or llamacpp")
        if not s.tokens:
            raise SystemExit("No access token. Set AI_TOKEN (or AI_TOKENS_FILE). Generate one with: python -m ai_server token")
        if any(len(t) < 24 for t in s.tokens):
            raise SystemExit("Access tokens must be at least 24 characters. Generate one with: python -m ai_server token")
        return s

    def networks(self):
        return [ipaddress.ip_network(n) for n in self.allow_networks]


_VALID_MODEL = re.compile(r"^[A-Za-z0-9._:/-]{1,80}$")


def valid_model_name(name: str) -> bool:
    return bool(_VALID_MODEL.match(name))
