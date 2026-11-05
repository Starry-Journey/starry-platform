from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .config import settings
from .routers import auth, chat, comments, health


def create_app(database_url: Optional[str] = None) -> FastAPI:
    db.configure(database_url or settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        db.init_db()
        yield

    app = FastAPI(title="Starry Journey API", version="0.1.0", lifespan=lifespan)

    origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(comments.router)
    app.include_router(chat.router)

    return app


app = create_app()
