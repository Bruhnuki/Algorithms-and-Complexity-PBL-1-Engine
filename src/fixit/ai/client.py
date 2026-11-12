"""Client for the AI server (ai_server/). Never raises into the game: callers get AiError and fall back to authored content."""
from __future__ import annotations

import ipaddress
import os
import socket
import threading
import time
from urllib.parse import urlparse

import httpx

TAILNET = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))   # Tailscale's address ranges
LOOPBACK = (ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("::1/128"))


def tailnet_check(url: str, *, allow_local: bool | None = None) -> str:
    """Refuse any AI address that is not on the Tailscale network, so the access token never travels over the open Internet.
    The host may be a Tailscale IP (100.x.y.z) or a MagicDNS name; a name must RESOLVE to Tailscale addresses. Loopback is only for tests on one PC
    (FIXIT_AI_ALLOW_LOCAL=1). Returns the host; raises ValueError with the reason."""
    if allow_local is None:
        allow_local = os.environ.get("FIXIT_AI_ALLOW_LOCAL") == "1"
    u = urlparse(url)
    host = u.hostname or ""
    if u.scheme not in ("http", "https") or not host:
        raise ValueError(f"not a valid address: {url!r}")
    try:
        ips = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            ips = [ipaddress.ip_address(a[4][0]) for a in socket.getaddrinfo(host, u.port or 80, proto=socket.IPPROTO_TCP)]
        except OSError as e:
            raise ValueError(f"cannot resolve {host!r}: is Tailscale running on this PC?") from e
    allowed = TAILNET + (LOOPBACK if allow_local else ())
    bad = [str(i) for i in ips if not any(i in n for n in allowed)]
    if bad or not ips:
        raise ValueError(f"{host!r} is {', '.join(bad) or 'unresolved'}, which is not a Tailscale address (100.64.0.0/10). Use the AI PC's Tailscale IP or MagicDNS name.")
    return host


class AiError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code = code


class AiClient:
    """URL and token come from FIXIT_AI_URL / FIXIT_AI_TOKEN (the Tailscale address or MagicDNS name of the AI PC).
    A circuit breaker stops hammering a server that is down and probes it again after `cooldown_s`."""

    def __init__(self, url: str, token: str, *, timeout_s: float = 90.0, transport=None, fail_limit: int = 3, cooldown_s: float = 60.0, clock=time.monotonic,
                 check_address: bool = True):
        self.url, self.check_address, self.checked_at = url, check_address, 0.0
        if check_address:
            tailnet_check(url)
            self.checked_at = time.monotonic()
        self.http = httpx.Client(base_url=url.rstrip("/"), headers={"Authorization": f"Bearer {token}"}, timeout=httpx.Timeout(timeout_s, connect=5.0), transport=transport)
        self.fail_limit, self.cooldown_s, self.clock = fail_limit, cooldown_s, clock
        self.fails, self.open_until, self.last_error, self.last_ok = 0, 0.0, None, None
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "AiClient | None":
        url, token = os.environ.get("FIXIT_AI_URL", ""), os.environ.get("FIXIT_AI_TOKEN", "")
        if not (url and token):
            return None
        try:
            return cls(url, token)
        except ValueError as e:   # the game still runs, just without the AI
            print(f"AI disabled: {e}")
            return None

    @property
    def circuit_open(self) -> bool:
        return self.clock() < self.open_until

    def generate(self, messages: list[dict], schema: dict | None, *, priority: str = "background", max_tokens: int = 600,
                 temperature: float = 0.7, seed: int | None = None, model: str | None = None) -> dict:
        if self.circuit_open:
            raise AiError("circuit_open", "the AI server is marked down; retrying later")
        if self.check_address and time.monotonic() - self.checked_at > 300:   # a name could start pointing somewhere else: look again every 5 minutes
            try:
                tailnet_check(self.url)
                self.checked_at = time.monotonic()
            except ValueError as e:
                raise AiError("bad_address", str(e)) from e
        body = {"messages": messages, "schema": schema, "priority": priority, "max_tokens": max_tokens, "temperature": temperature, "seed": seed, "model": model}
        try:
            r = self.http.post("/v1/generate", json=body)
        except httpx.HTTPError as e:
            self._fail(f"{type(e).__name__}")
            raise AiError("unreachable", type(e).__name__) from e
        if r.status_code == 200:
            with self._lock:
                self.fails, self.last_error, self.last_ok = 0, None, time.time()
            return r.json()
        code = (r.json().get("code") if r.headers.get("content-type", "").startswith("application/json") else None) or f"http_{r.status_code}"
        if r.status_code not in (429, 422):   # busy or a bad request is not "the server is down"
            self._fail(code)
        raise AiError(code, r.text[:200])

    def _fail(self, why: str) -> None:
        with self._lock:
            self.fails += 1
            self.last_error = why
            if self.fails >= self.fail_limit:
                self.open_until = self.clock() + self.cooldown_s

    def status(self) -> dict:
        """Ask the server how it is. Safe to call any time."""
        try:
            r = self.http.get("/v1/status", timeout=5.0)
            return {"reachable": r.status_code == 200, **(r.json() if r.status_code == 200 else {"code": r.status_code})}
        except httpx.HTTPError as e:
            return {"reachable": False, "error": type(e).__name__}
