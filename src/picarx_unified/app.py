from __future__ import annotations

import asyncio
import hmac
import logging
import subprocess
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from .config import AppConfig
from .models import (
    AudioTargetRequest, CameraRequest, DriveRequest, ModeRequest,
    SettingsUpdateRequest, VisionQuestionRequest
)
from .runtime import RobotRuntime
from .safety import SafetyViolation
from .voice import VoiceConnection
from .attacks.wifi_jammer import WifiJammer, JammerMode

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple rate limiter to prevent API abuse and rapid-fire commands."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, client_id: str) -> bool:
        """Check if client is within rate limits (pure check, does not record)."""
        now = time.time()
        cutoff = now - self.window_seconds

        async with self._lock:
            # Clean old requests outside the window
            self._requests[client_id] = [
                req_time for req_time in self._requests[client_id]
                if req_time > cutoff
            ]

            return len(self._requests[client_id]) < self.max_requests

    async def record_request(self, client_id: str) -> None:
        """Record a request for rate limiting."""
        async with self._lock:
            self._requests[client_id].append(time.time())

    def get_client_id(self, request: Request) -> str:
        """Extract a client identifier from the request."""
        # Use X-Forwarded-For if available, otherwise use remote address
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host or "unknown"


# Global rate limiter for drive commands
_drive_rate_limiter = RateLimiter(max_requests=120, window_seconds=60)

def _authorize(request: Request, authorization: Annotated[str | None, Header()] = None) -> None:
    token = request.app.state.runtime.config.api_token
    if not token:
        return
    supplied = ""
    if authorization:
        prefix = "bearer "
        if authorization.lower().startswith(prefix):
            supplied = authorization[len(prefix) :].strip()
    if not hmac.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token.")


def _get_runtime(request: Request) -> RobotRuntime:
    return request.app.state.runtime


def _get_jammer(request: Request) -> "WifiJammer":
    jammer = request.app.state.wifi_jammer
    if jammer is None:
        raise HTTPException(status_code=503, detail="WiFi jammer is unavailable (Scapy not installed).")
    return jammer


def _is_static_path_allowed(static_root, target) -> bool:
    return static_root == target or static_root in target.parents


def create_app() -> FastAPI:
    config = AppConfig.from_env()
    runtime = RobotRuntime(config)
    try:
        wifi_jammer = WifiJammer(monitor_interface="wlan1")
    except Exception as exc:
        logger.warning("WiFi jammer is unavailable and will be disabled: %s", exc)
        wifi_jammer = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime.start(asyncio.get_running_loop())
        app.state.runtime = runtime
        app.state.wifi_jammer = wifi_jammer
        yield
        runtime.shutdown()
        if wifi_jammer is not None:
            wifi_jammer.cleanup()

    app = FastAPI(title="PiCar-X Unified", lifespan=lifespan)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(config.static_dir / "index.html")

    @app.get("/static/{path:path}")
    async def static_file(path: str) -> FileResponse:
        static_root = config.static_dir.resolve()
        target = (config.static_dir / path).resolve()
        if not _is_static_path_allowed(static_root, target):
            raise HTTPException(status_code=404, detail="Static asset not found.")
        if not target.exists():
            raise HTTPException(status_code=404, detail="Static asset not found.")
        return FileResponse(target)

    @app.get("/api/health")
    async def health(request: Request):
        return _get_runtime(request).health()

    @app.post("/api/camera/debug-frame")
    async def camera_debug_frame(request: Request, _: None = Depends(_authorize)):
        runtime = _get_runtime(request)
        return runtime.camera.save_stream_debug_frames()

    @app.get("/api/state")
    async def state(request: Request):
        return _get_runtime(request).current_session()

    @app.get("/api/settings")
    async def settings(request: Request):
        return _get_runtime(request).get_settings()

    @app.post("/api/drive")
    async def drive(
        request: Request,
        command: DriveRequest,
        _: None = Depends(_authorize),
    ):
        runtime = _get_runtime(request)
        client_id = _drive_rate_limiter.get_client_id(request)
        if not await _drive_rate_limiter.is_allowed(client_id):
            raise HTTPException(status_code=429, detail="Too many drive commands. Please slow down.")
        try:
            result = runtime.apply_drive(command)
        except SafetyViolation as exc:
            runtime.record_error(str(exc))
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await _drive_rate_limiter.record_request(client_id)
        return result

    @app.post("/api/drive/fast")
    async def drive_fast(
        request: Request,
        command: DriveRequest,
        _: None = Depends(_authorize),
    ):
        """Lightweight drive endpoint: skips disk fsync + WebSocket broadcast
        for smooth high-frequency command loops."""
        runtime = _get_runtime(request)
        client_id = _drive_rate_limiter.get_client_id(request)
        if not await _drive_rate_limiter.is_allowed(client_id):
            raise HTTPException(status_code=429, detail="Too many drive commands. Please slow down.")
        try:
            result = runtime.apply_drive_fast(command)
        except SafetyViolation as exc:
            runtime.record_error(str(exc))
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        await _drive_rate_limiter.record_request(client_id)
        return result

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

    @app.post("/api/settings")
    async def update_settings(
        request: Request,
        body: SettingsUpdateRequest,
        _: None = Depends(_authorize),
    ):
        return _get_runtime(request).update_settings(body)

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
        answer = await _get_runtime(request).answer_vision_question(body.question)
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
        token = websocket.app.state.runtime.config.api_token
        if token:
            supplied = websocket.query_params.get("token", "")
            if not hmac.compare_digest(supplied, token):
                await websocket.close(code=4401)
                return
        connection = VoiceConnection(websocket.app.state.runtime, websocket)
        await connection.run()

    # WiFi Jammer endpoints
    @app.get("/api/jammer/robot_network")
    async def jammer_robot_network(request: Request):
        """Get information about the robot's own network"""
        return _get_jammer(request).get_robot_network()

    @app.get("/api/jammer/scan")
    async def jammer_scan(request: Request, duration: int = 10):
        """Scan for nearby WiFi networks"""
        try:
            networks = _get_jammer(request).scan_networks(duration=duration)
            return {"networks": networks, "count": len(networks)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/jammer/discover_clients")
    async def jammer_discover_clients(request: Request, body: dict):
        """Discover clients on a specific network"""
        try:
            bssid = body.get("bssid")
            channel = body.get("channel")
            duration = body.get("duration", 25)

            if not bssid or not channel:
                raise HTTPException(status_code=400, detail="bssid and channel are required")

            clients = _get_jammer(request).discover_network_clients(bssid, channel, duration=duration)
            return {"clients": clients, "count": len(clients), "bssid": bssid}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error discovering clients: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/jammer/start")
    async def jammer_start(
        request: Request,
        body: dict,
        _: None = Depends(_authorize),
    ):
        """Start WiFi jammer in mass, targeted, or client mode"""
        try:
            jammer = _get_jammer(request)

            # Extract parameters
            mode = body.get("mode", "mass")
            target_bssids = body.get("target_bssids", [])
            target_macs = body.get("target_macs", [])
            channel = body.get("channel")
            pps = body.get("pps", 100)
            duration = body.get("duration")

            # Log the request for debugging
            logger.info("Jammer start request - Mode: %s, BSSIDs: %s, MACs: %s, Channel: %s, PPS: %s", mode, target_bssids, target_macs, channel, pps)

            # Validate mode
            if mode not in ["mass", "targeted", "client"]:
                raise HTTPException(status_code=400, detail="Invalid mode. Use 'mass', 'targeted', or 'client'")

            # Validate targets based on mode
            if mode == "client":
                if not target_macs:
                    raise HTTPException(status_code=400, detail="No target MACs provided for client mode")
                if not target_bssids:
                    raise HTTPException(status_code=400, detail="Network BSSID required for client mode")
            else:
                if not target_bssids:
                    raise HTTPException(status_code=400, detail="No target BSSIDs provided")

            # Start attack
            result = jammer.start_attack(
                mode=mode,
                target_bssids=target_bssids,
                target_macs=target_macs,
                channel=channel,
                packet_rate=pps,
                duration=duration
            )

            logger.info("Jammer start result: %s", result)

            if result.get("status") == "error":
                raise HTTPException(status_code=400, detail=result.get("message", "Unknown error"))

            return result

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Jammer start error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/jammer/stop")
    async def jammer_stop(request: Request, _: None = Depends(_authorize)):
        """Stop WiFi jammer"""
        try:
            return _get_jammer(request).stop_attack()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/jammer/status")
    async def jammer_status(request: Request):
        """Get WiFi jammer status"""
        try:
            return _get_jammer(request).get_status()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/jammer/test")
    async def jammer_test(request: Request):
        """Test WiFi jammer configuration"""
        try:
            jammer = _get_jammer(request)

            # Check if aircrack-ng is available
            aircrack_available = False
            try:
                result = subprocess.run(["which", "airodump-ng"], capture_output=True, text=True, timeout=2)
                aircrack_available = result.returncode == 0
            except Exception:
                pass

            # Check if Scapy is available
            scapy_available = jammer._check_scapy() if hasattr(jammer, '_check_scapy') else False

            # Get robot network info
            robot_network = jammer.get_robot_network()

            # Check monitor interface
            monitor_interface = jammer.monitor_interface
            management_interface = jammer.management_interface

            return {
                "status": "ok",
                "aircrack_available": aircrack_available,
                "scapy_available": scapy_available,
                "monitor_interface": monitor_interface,
                "management_interface": management_interface,
                "robot_network": robot_network
            }
        except Exception as e:
            logger.error("Jammer test error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    return app
