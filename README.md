# PiCar-X Unified

## 1. Architecture overview

This project is a unified control stack for a SunFounder PiCar-X running on a Raspberry Pi 5. It is designed to stay compatible with the official `picarx.Picarx` hardware API while borrowing the good architectural ideas from [SPARK](https://github.com/adrianwedd/spark): strong separation of concerns, stateful services, safety-first orchestration, a browser-accessible API, and a voice loop that is distinct from low-level hardware control.

### Core engineering decisions

- Motor and servo control stay on top of the official SunFounder PiCar-X Python library.
- The web backend is FastAPI, because it gives clean REST endpoints, MJPEG streaming, and a WebSocket for browser audio.
- Voice, safety, motion, camera, vision, and behaviors are separate modules so later Wi-Fi and cybersecurity features can slot in without rewriting the robot core.
- AI is intentionally fenced away from direct motor commands. The AI can answer questions and generate speech, but the drive API is still guarded as a manual control path.
- The person-aware behavior in v1 uses onboard face detection as a practical stand-in for generic person detection. That is the most reliable lightweight option on a Pi 5 without assuming an AI Camera.
- Browser voice uses chunked WebSocket audio plus browser speech recognition when available. That is a much more practical first version than full WebRTC while still enabling relay mode and AI reply mode.

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

## 2. What to take from SPARK

Take these ideas from [SPARK](https://github.com/adrianwedd/spark):

- The overall layering: hardware adapters, state/session handling, API surface, voice loop, and higher-level behaviors should be separate.
- File-backed session state with locking, so browser state survives restarts and service modules do not stomp on one another.
- A safety-first attitude: validate commands before execution, keep a watchdog, and make emergency stop a first-class concept.
- Environment-driven configuration instead of scattering constants across the codebase.
- A clean API boundary where high-level commands go through one orchestration layer instead of every module talking to every other module.
- The separation between a reactive voice path and background robot behaviors.

Do **not** take these parts directly from SPARK:

- Persona-specific prompts, child-companion behavior, and model-specific launch scripts.
- The exact tool runner model, CLI wrappers, or Codex/Claude-specific voice bridge details.
- SPARK-specific robot affordances that are unrelated to your PiCar-X use case.

In other words: keep the architecture, not the product identity.

## 3. What to take from the official PiCar-X project

Take these parts from the official [SunFounder PiCar-X repository](https://github.com/SunFounder/picar-x) and [SunFounder PiCar-X documentation](https://docs.sunfounder.com/projects/picar-x-v20/en/latest/):

- The `picarx.Picarx` class as the hardware control base.
- The official servo control methods and calibration conventions.
- Steering, forward/backward, camera pan, and camera tilt through the SunFounder abstraction rather than custom raw GPIO or PWM code.
- The official install path for the PiCar-X ecosystem and Robot HAT dependencies.
- The official ultrasonic distance reading path for forward-motion safety checks.

Do **not** replace these with scratch-built low-level drivers unless you are intentionally forking away from SunFounder compatibility.

## 4. Full project structure

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

## 5. Full code for the first version

The full first-version implementation is the checked-in code in this repository. The primary entry points are:

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

### Features included in v1

- Drive control
- Camera pan/tilt control
- Camera streaming to the browser
- Relay mode
- AI reply mode
- Mute mode
- Audio output selection: car, browser, or both
- Vision question endpoint
- Greeting behavior when a person-like face is detected
- Emergency stop
- Ultrasonic and watchdog safety limits
- Optional bearer-token protection

## 6. Explanation of each file

- `pyproject.toml`: Python packaging and install metadata.
- `requirements.txt`: direct dependency list.
- `.env.example`: configurable runtime defaults and optional AI/API settings.
- `scripts/install_pi.sh`: one-file Raspberry Pi bootstrapper that installs dependencies, prepares `.env`, and can launch the app.
- `scripts/run_pi.sh`: compatibility wrapper that forwards to `install_pi.sh --run-only`.
- `deploy/picarx-unified.service`: `systemd` unit file for boot-time startup.
- `src/picarx_unified/config.py`: central environment-backed configuration object.
- `src/picarx_unified/models.py`: Pydantic request/response/session models.
- `src/picarx_unified/state.py`: locked JSON session persistence inspired by SPARK’s state separation.
- `src/picarx_unified/safety.py`: speed/steering/pan/tilt clamping and motion blocking rules.
- `src/picarx_unified/hardware/picarx_adapter.py`: official PiCar-X wrapper plus mock backend.
- `src/picarx_unified/hardware/camera.py`: camera source abstraction with Picamera2, OpenCV, or mock fallback.
- `src/picarx_unified/audio.py`: local speaker playback and browser audio event routing.
- `src/picarx_unified/ai.py`: optional Gemini Live-backed AI plus local rule-based fallback and `espeak` TTS.
- `src/picarx_unified/vision.py`: face detection and natural-language scene summary.
- `src/picarx_unified/behaviors.py`: autonomous but non-driving behavior loop for greeting/tracking.
- `src/picarx_unified/runtime.py`: the main coordination layer that keeps modules decoupled.
- `src/picarx_unified/voice.py`: browser audio session logic for relay and AI reply.
- `src/picarx_unified/app.py`: HTTP and WebSocket application surface.
- `src/picarx_unified/__main__.py`: `python -m picarx_unified` entry point.
- `src/picarx_unified/static/index.html`: browser UI markup.
- `src/picarx_unified/static/styles.css`: responsive dashboard styling.
- `src/picarx_unified/static/app.js`: frontend control logic.
- `src/picarx_unified/static/pcm-worklet.js`: raw microphone capture worklet for low-latency chunking.

## 7. Installation and run steps

### One-file install and run

The fastest Raspberry Pi setup is a single command:

```bash
cd /path/to/Picar-px
bash scripts/install_pi.sh
```

That one file will:

1. Install Raspberry Pi OS packages with `apt`
2. Install the official SunFounder PiCar-X Python stack when needed
3. Create or reuse `.venv`
4. Install this project in editable mode
5. Create `.env` from `.env.example` on first run
6. Start the web app

Open the dashboard at `http://<pi-ip-address>:8080/` when startup finishes.

### Useful options

```bash
# install everything, but do not start the app
bash scripts/install_pi.sh --install-only

# start an already-installed setup
bash scripts/install_pi.sh --run-only

# force mock hardware and mock camera mode
bash scripts/install_pi.sh --mock

# override bind host and port for the current run
bash scripts/install_pi.sh --run-only --host 0.0.0.0 --port 8080
```

The script auto-loads `.env` if it exists, so optional settings such as `GEMINI_API_KEY` and `PICARX_API_TOKEN` can live there.

### Full install on Raspberry Pi 5

```bash
cd /path/to/Picar-px
bash scripts/install_pi.sh
```

If you want optional cloud AI features:

```bash
cp .env.example .env
nano .env
```

If you want API protection:

```bash
nano .env
```

### Run over SSH

```bash
cd /path/to/Picar-px
bash scripts/install_pi.sh --run-only
```

Or:

```bash
bash scripts/run_pi.sh
```

If your PiCar-X library or Robot HAT access requires elevated permissions on your setup, run the service with the same privilege level you normally use for official SunFounder motor-control scripts.

### Access from the browser

Open:

```text
http://<pi-ip-address>:8080/
```

Example:

```text
http://192.168.1.42:8080/
```

### SSH control examples

Drive forward:

```bash
curl -X POST http://127.0.0.1:8080/api/drive \
  -H "Content-Type: application/json" \
  -d '{"speed": 25, "steering": 0, "source": "ssh"}'
```

Stop:

```bash
curl -X POST http://127.0.0.1:8080/api/drive/stop
```

Move camera:

```bash
curl -X POST http://127.0.0.1:8080/api/camera \
  -H "Content-Type: application/json" \
  -d '{"pan": 15, "tilt": -5}'
```

Ask a vision question:

```bash
curl -X POST http://127.0.0.1:8080/api/vision/question \
  -H "Content-Type: application/json" \
  -d '{"question": "What do you see right now?"}'
```

Set voice mode:

```bash
curl -X POST http://127.0.0.1:8080/api/voice/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "relay"}'
```

If you enable `PICARX_API_TOKEN`, add:

```bash
-H "Authorization: Bearer your-token"
```

### Step-by-step test plan

1. Start the service and confirm `GET /api/health` returns `ok: true`.
2. Open the browser UI and confirm the MJPEG stream loads.
3. Move the pan/tilt sliders and confirm the camera servos respond.
4. Tap each drive button briefly and confirm motion starts and stops cleanly.
5. Put an object close in front of the ultrasonic sensor and verify forward motion is blocked.
6. Trigger emergency stop and verify all motion commands are rejected until reset.
7. Set `Relay` mode, choose `car`, press and hold the talk button, and confirm your browser mic audio plays through the car speaker.
8. Set `Relay` mode, choose `browser`, press and hold the talk button, and confirm you hear the relayed audio in your computer speakers.
9. Set `AI Reply` mode, speak a short phrase, and confirm the transcript appears and the reply is spoken to the selected target.
10. Ask a vision question from the browser or `curl` and confirm the answer matches the live scene summary.
11. Stand in front of the camera and confirm the pan/tilt tries to center your face and greets on cooldown.

### Systemd startup

Copy the service file, then enable it:

```bash
sudo cp deploy/picarx-unified.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now picarx-unified.service
sudo systemctl status picarx-unified.service
```

The service runs the same bootstrap script in `--run-only` mode, so the manual flow and boot flow stay aligned.

## 8. Future improvements

- Replace Haar face detection with a Pi-friendly detector such as MediaPipe or a lightweight YOLO model once you confirm performance on your Pi 5.
- Upgrade the chunked WebSocket voice path to WebRTC if you need lower latency and built-in echo cancellation.
- Add a local offline STT provider such as `faster-whisper` for AI reply mode when browser speech recognition is unavailable.
- Add a capability registry for future Wi-Fi scanning and cybersecurity modules without letting those modules touch the motor layer directly.
- Add audit logging and role-based API permissions if the robot will be exposed beyond a trusted LAN.
- Add a behavior policy engine so greetings, tracking, and future autonomy features can be toggled independently.
- Add a richer vision memory layer so the AI can answer temporal questions such as "who was just here?" or "what changed?".
- Add optional battery telemetry, IMU, and network health panels to the browser UI.
