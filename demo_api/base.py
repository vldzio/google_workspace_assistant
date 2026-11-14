"""Shared FastAPI scaffolding for every demo API: CORS, gateway bootstrap,
admission control (per-IP/global limits or BYO key) and LangSmith-traced handlers."""
from __future__ import annotations

import contextvars
import os
import threading
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import gateway, guard, llm


def create_app(title: str, *, on_startup: Callable[[], None] | None = None) -> FastAPI:
    if os.environ.get("LANGSMITH_API_KEY"):
        os.environ.setdefault("LANGSMITH_TRACING", "true")

    app = FastAPI(title=title, docs_url="/docs")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup() -> None:
        if on_startup:
            on_startup()
        threading.Thread(target=gateway.connect, daemon=True, name="gateway-connect").start()

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "service": title,
            "llmReady": bool(os.environ.get("LLM_BASE_URL")),
            "tracing": llm.tracing_enabled(),
            "langsmithProject": os.environ.get("LANGSMITH_PROJECT"),
        }

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def client_ip(req: Request) -> str:
    # The platform proxy appends the real client IP as the LAST entry; earlier entries are client-supplied
    # and spoofable, so never use them for rate limiting.
    fwd = req.headers.get("x-forwarded-for")
    return fwd.split(",")[-1].strip() if fwd else (req.client.host if req.client else "unknown")


async def guarded(req: Request, cost: int, fn: Callable[[], Any], *, name: str) -> JSONResponse:
    """Admit the request (limits / BYO key), run ``fn`` in a worker thread under a LangSmith trace.

    ``fn`` must be a sync callable returning something JSON-serialisable.
    """
    import anyio

    try:
        byo = guard.validate_byo(req.headers.get("x-llm-api-key"), req.headers.get("x-llm-base-url"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    decision = guard.check(client_ip(req), cost, byo=bool(byo))
    if not decision.allowed:
        return JSONResponse({"error": decision.message, "rateLimited": True}, status_code=429)

    def run() -> Any:
        traced = fn
        if llm.tracing_enabled():
            try:
                from langsmith import traceable

                traced = traceable(name=name, run_type="chain", metadata={"byo_key": bool(byo), "project": guard.PROJECT})(fn)
            except Exception:  # noqa: BLE001
                traced = fn
        with llm.byo(byo[0] if byo else None, byo[1] if byo else None):
            return traced()

    ctx = contextvars.copy_context()
    try:
        result = await anyio.to_thread.run_sync(lambda: ctx.run(run))
        return JSONResponse(result)
    except llm.LLMUnavailable as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    except ValueError as exc:  # bad input detected by handlers
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        # make sure short-lived traces reach LangSmith before the worker idles
        if llm.tracing_enabled():
            try:
                from langsmith import Client

                Client().flush()
            except Exception:  # noqa: BLE001
                pass
