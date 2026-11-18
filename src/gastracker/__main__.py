"""Run the web service with python -m gastracker."""

import uvicorn

from gastracker.config import load_settings


def main() -> None:
    settings = load_settings()
    uvicorn.run(
        "gastracker.main:create_app",
        factory=True,
        host=settings.web_host,
        port=settings.web_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
