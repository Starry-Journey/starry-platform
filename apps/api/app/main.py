from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from . import db
from .config import settings
from .routers import auth, charts, chat, comments, health

REQUESTS = Counter("starry_http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("starry_http_request_seconds", "HTTP latency", ["method", "path"])
access_log = logging.getLogger("starry.access")
if not access_log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    access_log.addHandler(_handler)
    access_log.setLevel(logging.INFO)
    access_log.propagate = False


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
    app.include_router(health.router, prefix="/v1")
    app.include_router(auth.router)
    app.include_router(comments.router)
    app.include_router(chat.router)
    app.include_router(charts.router)

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        LATENCY.labels(request.method, path).observe(elapsed)
        access_log.info(
            json.dumps(
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round(elapsed * 1000, 1),
                },
                ensure_ascii=False,
            )
        )
        return response

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
