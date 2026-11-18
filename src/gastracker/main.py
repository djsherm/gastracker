"""FastAPI application factory."""

from fastapi import FastAPI

from gastracker.config import load_settings


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(title=settings.name)
    app.state.settings = settings

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "timezone": settings.timezone.key}

    return app
