"""FastAPI-based REST API server for JARVIS.

Endpoints
---------
- ``POST /api/plan``           Accept text, return a structured plan.
- ``POST /api/execute``        Accept a plan, execute it and return the result.
- ``POST /api/command``        Combined plan+execute (text in, result out).
- ``GET  /api/health``         Health check.
- ``GET  /api/metrics``        Return a metrics snapshot.
- ``POST /api/memory/store``   Store a fact in memory.
- ``GET  /api/memory/recall``  Recall stored facts.
- ``POST /api/speak``          Text-to-speech endpoint.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import logging
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from jarvis.app import JarvisApplication
from jarvis.api.dependencies import get_app, set_app

logger = logging.getLogger("jarvis.api.server")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class PlanRequest(BaseModel):
    text: str = Field(..., description="Natural language command")


class PlanResponse(BaseModel):
    plan: Dict[str, Any]
    generated_at: str = Field(..., description="ISO timestamp")


class ExecuteRequest(BaseModel):
    plan: Dict[str, Any] = Field(..., description="Execution plan to run")


class ExecuteResponse(BaseModel):
    result: str
    duration_ms: float


class CommandRequest(BaseModel):
    text: str = Field(..., description="Natural language command")


class CommandResponse(BaseModel):
    plan: Dict[str, Any]
    result: str
    duration_ms: float


class HealthResponse(BaseModel):
    status: str = "ok"
    timestamp: str = Field(..., description="ISO timestamp")


class MemoryStoreRequest(BaseModel):
    key: str
    value: Any


class MemoryRecallRequest(BaseModel):
    key: str


class SpeakRequest(BaseModel):
    text: str


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


async def _run_in_thread(func, *args):
    """Run a blocking function in a thread pool."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args))


def _execute_plan(app: JarvisApplication, plan: dict) -> str:
    """Execute a plan using the app's executor (blocking)."""
    return app.execute_plan(plan)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(app_instance: JarvisApplication) -> FastAPI:
    """Build and return a configured FastAPI application wired to *app_instance*.

    Call ``set_app(app_instance)`` so that the :func:`get_app` dependency
    works without passing the instance through every route.
    """
    set_app(app_instance)

    api_app = FastAPI(
        title="JARVIS REST API",
        version="3.0.0",
        description="Voice-driven AI Operating System for Windows — REST interface",
    )

    # Allow cross-origin requests from local frontends / tools
    api_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    @api_app.post("/api/plan", response_model=PlanResponse)
    async def plan_endpoint(req: PlanRequest, app: JarvisApplication = Depends(get_app)) -> PlanResponse:
        """Accept natural-language text, return a structured plan."""
        try:
            plan = await _run_in_thread(app._plan, req.text)
            return PlanResponse(plan=plan, generated_at=_now())
        except Exception as exc:
            logger.exception("Plan endpoint failed")
            raise HTTPException(status_code=500, detail=str(exc))

    @api_app.post("/api/execute", response_model=ExecuteResponse)
    async def execute_endpoint(
        req: ExecuteRequest, app: JarvisApplication = Depends(get_app)
    ) -> ExecuteResponse:
        """Accept a plan dict, execute it and return the textual result."""
        import time

        t0 = time.perf_counter()
        try:
            result = await _run_in_thread(_execute_plan, app, req.plan)
            elapsed = (time.perf_counter() - t0) * 1000.0
            return ExecuteResponse(result=result, duration_ms=round(elapsed, 1))
        except Exception as exc:
            logger.exception("Execute endpoint failed")
            raise HTTPException(status_code=500, detail=str(exc))

    @api_app.post("/api/command", response_model=CommandResponse)
    async def command_endpoint(
        req: CommandRequest, app: JarvisApplication = Depends(get_app)
    ) -> CommandResponse:
        """Combined plan + execute: text in, result out."""
        import time

        t0 = time.perf_counter()
        try:
            plan = await _run_in_thread(app._plan, req.text)
            result = await _run_in_thread(_execute_plan, app, plan)
            await _run_in_thread(app.speak, result)
            elapsed = (time.perf_counter() - t0) * 1000.0
            return CommandResponse(
                plan=plan,
                result=result,
                duration_ms=round(elapsed, 1),
            )
        except Exception as exc:
            logger.exception("Command endpoint failed")
            raise HTTPException(status_code=500, detail=str(exc))

    @api_app.get("/api/health", response_model=HealthResponse)
    async def health_endpoint(app: JarvisApplication = Depends(get_app)) -> HealthResponse:
        """Health check."""
        # Delegate to app's health check
        health_dict = app.health_check()
        overall = all(v.healthy for v in health_dict.values())
        return HealthResponse(
            status="ok" if overall else "error", timestamp=_now()
        )

    @api_app.get("/api/metrics")
    async def metrics_endpoint(app: JarvisApplication = Depends(get_app)):
        """Return system metrics snapshot for live widgets."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=None)
            disk = psutil.disk_usage("/")
            net = psutil.net_io_counters()
            battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
            temps = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else None
            return {
                "cpu": round(cpu, 1),
                "ram": round(mem.percent, 1),
                "ram_used": round(mem.used / (1024 ** 3), 1),
                "ram_total": round(mem.total / (1024 ** 3), 1),
                "disk_used": round(disk.used / (1024 ** 3), 1),
                "disk_total": round(disk.total / (1024 ** 3), 1),
                "disk_pct": round(disk.percent, 1),
                "net_up": round(net.bytes_sent / (1024 ** 2), 1),
                "net_down": round(net.bytes_recv / (1024 ** 2), 1),
                "battery_pct": battery.percent if battery else None,
                "battery_charging": battery.power_plugged if battery else None,
                "temps": {k: v[0].current if v else None for k, v in temps.items()} if temps else {},
            }
        except Exception as exc:
            logger.warning("Metrics collection failed: %s", exc)
            return {"error": str(exc)}

    @api_app.get("/api/voice/state")
    async def voice_state_endpoint(app: JarvisApplication = Depends(get_app)):
        """Return current voice state for HUD status indicator."""
        try:
            from jarvis.voice_first import _voice_backend
            return {
                "active": _voice_backend.conversation_active,
                "state": _voice_backend.state,
                "last_active": _voice_backend.last_active_time,
            }
        except Exception:
            return {"active": False, "state": "passive"}

    @api_app.post("/api/voice/activate")
    async def voice_activate_endpoint(req: CommandRequest, app: JarvisApplication = Depends(get_app)):
        """Activate voice conversation mode."""
        try:
            from jarvis.voice_first import _voice_backend
            _voice_backend.conversation_active = True
            _voice_backend.state = "active"
            _voice_backend.last_active_time = time.time()
            return {"status": "active"}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @api_app.post("/api/voice/deactivate")
    async def voice_deactivate_endpoint(req: CommandRequest, app: JarvisApplication = Depends(get_app)):
        """Deactivate voice conversation mode."""
        try:
            from jarvis.voice_first import _voice_backend
            _voice_backend.conversation_active = False
            _voice_backend.state = "passive"
            return {"status": "passive"}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @api_app.post("/api/memory/store")
    async def memory_store_endpoint(
        req: MemoryStoreRequest, app: JarvisApplication = Depends(get_app)
    ):
        """Store a fact in memory."""
        try:
            # app.memory is a JsonMemoryStore instance?
            # We'll assume app.memory has set method
            app.memory.set(req.key, req.value)
            return {"status": "ok"}
        except Exception as exc:
            logger.exception("Memory store failed")
            raise HTTPException(status_code=500, detail=str(exc))

    @api_app.post("/api/memory/recall")
    async def memory_recall_endpoint(
        req: MemoryRecallRequest, app: JarvisApplication = Depends(get_app)
    ):
        """Recall a stored fact."""
        try:
            value = app.memory.get(req.key)
            return {"key": req.key, "value": value}
        except Exception as exc:
            logger.exception("Memory recall failed")
            raise HTTPException(status_code=500, detail=str(exc))

    @api_app.post("/api/speak")
    async def speak_endpoint(req: SpeakRequest, app: JarvisApplication = Depends(get_app)):
        """Text-to-speech endpoint."""
        try:
            # Use app's speak method (if exists) or fallback to logging
            if hasattr(app, "speak"):
                app.speak(req.text)
            else:
                logger.info("TTS: %s", req.text)
            return {"status": "ok"}
        except Exception as exc:
            logger.exception("Speak failed")
            raise HTTPException(status_code=500, detail=str(exc))

    @api_app.get("/api/media/status")
    async def media_status_endpoint():
        """Return current media session metadata from the Windows media pipeline.

        Uses the ``winsdk`` Windows.Media.Control API when available.
        Falls back to a graceful empty-state response if not running on
        Windows or if no media is currently playing.
        """
        _empty = {"playing": False, "track": None, "artist": None, "album": None}
        try:
            import platform
            if platform.system().lower() != "windows":
                return _empty

            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as Manager,
            )

            manager = await Manager.request_async()
            session = manager.get_current_session()
            if not session:
                return _empty

            info = await session.try_get_media_properties_async()
            pb = session.get_playback_info()
            playing = bool(
                pb and pb.playback_status and pb.playback_status.value == 3
            )
            return {
                "playing": playing,
                "track": info.title if info else None,
                "artist": info.artist if info else None,
                "album": info.album_title if info else None,
            }
        except ImportError:
            # winsdk not installed — return empty state rather than crashing
            return _empty
        except Exception as exc:
            logger.warning("Media status failed: %s", exc)
            return _empty

    @api_app.get("/api/context")
    async def context_endpoint():
        """Return a snapshot of the live session context store.

        Used by the frontend to display the current app, window, folder,
        and file that JARVIS is operating on.
        """
        try:
            import context_store as _cs
            return _cs.snapshot()
        except Exception as exc:
            logger.warning("Context snapshot failed: %s", exc)
            return {}

    @api_app.post("/api/command/stream")
    async def command_stream_endpoint(
        req: CommandRequest, app: JarvisApplication = Depends(get_app)
    ):
        """Combined plan + execute with streaming response.
        Returns NDJSON lines: {"type":"plan","data":...} then {"type":"result","data":...}"""
        import time

        def generate():
            t0 = time.perf_counter()
            try:
                # Phase 1: Plan
                plan = app._plan(req.text)
                yield json.dumps({"type": "plan", "data": plan}) + "\n"

                # Phase 2: Execute
                result = _execute_plan(app, plan)
                elapsed = (time.perf_counter() - t0) * 1000.0
                yield json.dumps({
                    "type": "result",
                    "data": result,
                    "duration_ms": round(elapsed, 1),
                }) + "\n"
            except Exception as exc:
                yield json.dumps({"type": "error", "data": str(exc)}) + "\n"

        return StreamingResponse(
            generate(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # ------------------------------------------------------------------
    # Serve JARVIS web UI at root (catch-all for non-API routes)
    # ------------------------------------------------------------------
    ui_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "opendesign", "mockups", "jarvis-interface")
    api_app.mount(
        "/", StaticFiles(directory=ui_dir, html=True), name="ui"
    )

    return api_app


def run_server(app_instance: "JarvisApplication", host: str = "127.0.0.1", port: int = 8000):
    """Run the FastAPI app with Uvicorn."""
    import uvicorn

    uvicorn.run(
        create_app(app_instance),
        host=host,
        port=port,
        log_level="info",
    )