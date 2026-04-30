from __future__ import annotations

import uvicorn

from .config import AppConfig


def main() -> None:
    config = AppConfig.from_env()
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
        **ssl_kwargs,
    )


if __name__ == "__main__":
    main()
