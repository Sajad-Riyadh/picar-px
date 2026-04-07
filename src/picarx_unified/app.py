from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from .config import AppConfig
from .models import AudioTargetRequest, CameraRequest, DriveRequest, ModeRequest, VisionQuestionRequest
from .runtime import RobotRuntime
from .safety import SafetyViolation
from .voice import VoiceConnection


def _authorize(request: Request, authorization: Annotated[str | None, Header()] = None) -> None:
    token = request.app.state.runtime.config.api_token
    if not token:
        return
    supplied = ""
    if authorization:
        prefix = "bearer "
        if authorization.lower().startswith(prefix):
            supplied = authorization[len(prefix) :].strip()
    if supplied != token:
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token.")


def _get_runtime(request: Request) -> RobotRuntime:
    return request.app.state.runtime


def create_app() -> FastAPI:
    config = AppConfig.from_env()
    runtime = RobotRuntime(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime.start(asyncio.get_running_loop())
        app.state.runtime = runtime
        yield
        runtime.stop()

    app = FastAPI(title="PiCar-X Unified", lifespan=lifespan)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(config.static_dir / "index.html")

    @app.get("/static/{path:path}")
    async def static_file(path: str) -> FileResponse:
        static_root = config.static_dir.resolve()
        target = (config.static_dir / path).resolve()
        if static_root != target and static_root not in target.parents:
            raise HTTPException(status_code=404, detail="Static asset not found.")
        if not target.exists():
            raise HTTPException(status_code=404, detail="Static asset not found.")
        return FileResponse(target)

    @app.get("/api/health")
    async def health(request: Request):
        return _get_runtime(request).health()

    @app.get("/api/state")
    async def state(request: Request):
        return _get_runtime(request).current_session()

    @app.post("/api/drive")
    async def drive(
        request: Request,
        command: DriveRequest,
        _: None = Depends(_authorize),
    ):
        runtime = _get_runtime(request)
        try:
            return runtime.apply_drive(command)
        except SafetyViolation as exc:
            runtime.record_error(str(exc))
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/drive/stop")
    async def stop_drive(request: Request, _: None = Depends(_authorize)):
        return _get_runtime(request).stop_drive()

    @app.post("/api/camera")
    async def camera(request: Request, command: CameraRequest, _: None = Depends(_authorize)):
        return _get_runtime(request).set_camera(command)

    @app.post("/api/voice/mode")
    async def voice_mode(request: Request, body: ModeRequest, _: None = Depends(_authorize)):
        return _get_runtime(request).set_voice_mode(body.mode)

    @app.post("/api/audio/target")
    async def audio_target(request: Request, body: AudioTargetRequest, _: None = Depends(_authorize)):
        return _get_runtime(request).set_audio_target(body.target)

    @app.post("/api/emergency-stop")
    async def emergency_stop(request: Request, _: None = Depends(_authorize)):
        return _get_runtime(request).trigger_emergency_stop()

    @app.post("/api/emergency-reset")
    async def emergency_reset(request: Request, _: None = Depends(_authorize)):
        return _get_runtime(request).clear_emergency_stop()

    @app.get("/api/vision")
    async def vision_summary(request: Request):
        return _get_runtime(request).vision.get_snapshot()

    @app.post("/api/vision/question")
    async def vision_question(
        request: Request,
        body: VisionQuestionRequest,
        _: None = Depends(_authorize),
    ):
        answer = _get_runtime(request).answer_vision_question(body.question)
        return JSONResponse({"answer": answer})

    @app.get("/stream.mjpg")
    async def video_stream(request: Request):
        runtime = _get_runtime(request)
        return StreamingResponse(
            runtime.camera.stream_generator(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    @app.websocket("/ws/voice")
    async def voice_socket(websocket: WebSocket):
        token = runtime.config.api_token
        if token:
            supplied = websocket.query_params.get("token", "")
            if supplied != token:
                await websocket.close(code=4401)
                return
        connection = VoiceConnection(runtime, websocket)
        await connection.run()

    return app
