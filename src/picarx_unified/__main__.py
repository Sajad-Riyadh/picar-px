from __future__ import annotations

import socket
import sys

import uvicorn

from .config import AppConfig


def _get_lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            return ip if ip not in ("127.0.0.1", "::1", "") else None
    except Exception:
        return None


def main() -> None:
    config = AppConfig.from_env()
    scheme = "https" if config.https_enabled else "http"
    hostname = socket.gethostname()
    lan_ip = _get_lan_ip()

    print("", flush=True)
    print("=" * 58, flush=True)
    print(" PiCar-X dashboard access URLs", flush=True)
    print("=" * 58, flush=True)
    if lan_ip:
        print(f"  {scheme}://{lan_ip}:{config.port}/", flush=True)
        print(f"    ^ use this IP if .local does not resolve", flush=True)
    print(f"  {scheme}://{hostname}.local:{config.port}/", flush=True)
    print("=" * 58, flush=True)
    print("", flush=True)

    ssl_kwargs = {}
    if config.https_enabled:
        ssl_kwargs = {
            "ssl_certfile": str(config.ssl_certfile),
            "ssl_keyfile": str(config.ssl_keyfile),
        }
    uvicorn.run(
        "picarx_unified.app:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        reload=False,
        loop="asyncio",
        **ssl_kwargs,
    )


if __name__ == "__main__":
    main()
