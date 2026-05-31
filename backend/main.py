"""CyberMirror FastAPI entry point."""

import uvicorn

from app.api.routes import create_app
from app.config import settings

app = create_app()


def main() -> None:
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
