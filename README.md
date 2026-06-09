# PiCar-X Unified

## Quick Installation

On a fresh Raspberry Pi 5, run this one command:

```bash
bash scripts/install_pi.sh
```

This will:
1. Install all required system packages (including aircrack-ng for WiFi features)
2. Install the SunFounder PiCar-X Python stack
3. Create a Python virtual environment
4. Set up the systemd service with all necessary permissions
5. Start the application

The service will be automatically enabled and started. Access the web interface at `http://<your-pi-ip>:8080`.

### Installation Options

```bash
# Install only (don't start the app)
bash scripts/install_pi.sh --install-only

# Start as systemd service instead of foreground
bash scripts/install_pi.sh --service

# Run in mock mode (no hardware required)
bash scripts/install_pi.sh --mock

# Skip SunFounder stack installation
bash scripts/install_pi.sh --skip-sunfounder
```

### Manual Service Management

```bash
# Check service status
sudo systemctl status picarx-unified.service

# Start/stop/restart service
sudo systemctl start picarx-unified.service
sudo systemctl stop picarx-unified.service
sudo systemctl restart picarx-unified.service

# View logs
sudo journalctl -u picarx-unified.service -f
```

## 1. Architecture overview

This project is a unified control stack for a SunFounder PiCar-X running on a Raspberry Pi 5. It stays compatible with the official `picarx.Picarx` hardware API while keeping the robot software sp[...]

### Core engineering decisions

- Motor and servo control stay on top of the official SunFounder PiCar-X Python library.
- The web backend is FastAPI, because it gives clean REST endpoints, MJPEG streaming, and a WebSocket for browser audio.
- Voice, safety, motion, camera, vision, and behaviors are separate modules so later Wi-Fi and cybersecurity features can slot in without rewriting the robot core.
- AI is intentionally fenced away from direct motor commands. The AI can answer questions and generate speech, but the drive API is still guarded as a manual control path.
- The person-aware behavior uses onboard face detection as a practical stand-in for generic person detection. That is the most reliable lightweight option on a Pi 5 without assuming an AI Camera.
- Browser voice uses chunked WebSocket audio plus browser speech recognition when available. That is a more practical starting point than full WebRTC while still enabling relay mode and AI reply m[...]
- Manual steering-only commands are supported. Left or right input can turn the front wheels without forcing forward or reverse motion, while combined forward/backward plus steering inputs still d[...]

### Layered design

```text
Browser UI / SSH curl
        |
        +--> REST API --------------------+
        |                                 |
        +--> WebSocket voice loop         |
                                          v
                              Runtime / Session Coordination
                                          |
                    +---------------------+---------------------+
                    |                     |                     |
                 Safety               Voice/Audio            Vision
                    |                     |                     |
                Hardware               AI Service         Person Behavior
                    |                     |                     |
             SunFounder Picarx       Local/Cloud AI       Camera pan/tilt greet
                    |
         Motors / steering / pan / tilt / ultrasonic
```

### Runtime responsibilities

- `RobotRuntime` is the orchestration boundary.
- `PicarxAdapter` is the only module that talks to the PiCar-X hardware API.
- `SafetyGuard` clamps speed, steering, pan, tilt, blocks AI motor control, and blocks forward motion when the ultrasonic sensor reports a close obstacle.
- `CameraService` owns frame capture and MJPEG streaming.
- `VisionService` owns scene analysis and summarizes what the camera currently sees.
- `PersonGreeterBehavior` tracks a detected face with the pan/tilt servos and greets only on a cooldown.
- `AudioRouter` decides whether sound goes to the car speaker, the browser speaker, or both.
- `VoiceConnection` handles browser microphone chunks, relay mode, AI reply mode, and transcript handoff.

## 2. What to take from the official PiCar-X project

Take these parts from the official [SunFounder PiCar-X repository](https://github.com/SunFounder/picar-x) and [SunFounder PiCar-X documentation](https://docs.sunfounder.com/projects/picar-x-v20/e[...]

- The `picarx.Picarx` class as the hardware control base.
- The official servo control methods and calibration conventions.
- Steering, forward/backward, camera pan, and camera tilt through the SunFounder abstraction rather than custom raw GPIO or PWM code.
- The official install path for the PiCar-X ecosystem and Robot HAT dependencies.
- The official ultrasonic distance reading path for forward-motion safety checks.

Do **not** replace these with scratch-built low-level drivers unless you are intentionally forking away from SunFounder compatibility.

## 3. Full project structure

```text
Picar-px/
├── .env.example
├── .gitignore
├── README.md
├── deploy/
│   └── picarx-unified.service
├── pyproject.toml
├── requirements.txt
├── scripts/
│   ├── install_pi.sh
│   └── run_pi.sh
└── src/
    └── picarx_unified/
        ├── __init__.py
        ├── __main__.py
        ├── ai.py
        ├── app.py
        ├── audio.py
        ├── behaviors.py
        ├── config.py
        ├── models.py
        ├── runtime.py
        ├── safety.py
        ├── state.py
        ├── vision.py
        ├── voice.py
        ├── attacks/
        │   ├── __init__.py
        │   └── wifi_jammer.py
        ├── hardware/
        │   ├── __init__.py
        │   ├── camera.py
        │   └── picarx_adapter.py
        └── static/
            ├── app.js
            ├── index.html
            ├── pcm-worklet.js
            └── styles.css
```

## 4. Full code for the current version

The full implementation is the checked-in code in this repository. The primary entry points are:

- [`src/picarx_unified/app.py`](src/picarx_unified/app.py): FastAPI app, REST routes, MJPEG stream, WebSocket voice endpoint.
- [`src/picarx_unified/runtime.py`](src/picarx_unified/runtime.py): system orchestration, browser session state, watchdog, emergency stop, AI turn handling.
- [`src/picarx_unified/hardware/picarx_adapter.py`](src/picarx_unified/hardware/picarx_adapter.py): official PiCar-X wrapper with a mock fallback for development.
- [`src/picarx_unified/hardware/camera.py`](src/picarx_unified/hardware/camera.py): Picamera2/OpenCV capture and MJPEG frame source.
- [`src/picarx_unified/safety.py`](src/picarx_unified/safety.py): motor and servo safety constraints.
- [`src/picarx_unified/vision.py`](src/picarx_unified/vision.py): onboard face detection and scene summary generation.
- [`src/picarx_unified/behaviors.py`](src/picarx_unified/behaviors.py): person-aware camera tracking and greeting loop.
- [`src/picarx_unified/audio.py`](src/picarx_unified/audio.py): car-speaker/browser-speaker routing.
- [`src/picarx_unified/voice.py`](src/picarx_unified/voice.py): relay mode and AI reply mode browser voice handling.
- [`src/picarx_unified/ai.py`](src/picarx_unified/ai.py): AI reply generation, optional Gemini Live vision/STT, local `espeak` TTS fallback.
- [`src/picarx_unified/static/index.html`](src/picarx_unified/static/index.html): browser dashboard.
- [`src/picarx_unified/static/app.js`](src/picarx_unified/static/app.js): browser controls, push-to-talk, playback, state refresh.
- [`src/picarx_unified/static/pcm-worklet.js`](src/picarx_unified/static/pcm-worklet.js): microphone PCM capture worklet.