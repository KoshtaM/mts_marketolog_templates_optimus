"""Запуск веб-версии: uvicorn с фабрикой приложения."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    """Запустить локальный API и собранный веб-клиент."""
    host = os.environ.get("MTS_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("MTS_WEB_PORT", "8000"))
    reload = os.environ.get("MTS_WEB_RELOAD", "").lower() in {"1", "true", "yes"}
    uvicorn.run(
        "mts_templates.presentation.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
