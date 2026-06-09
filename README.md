# PiCar-X Unified

## Installation
Run the following on a fresh Raspberry Pi:
```bash
bash scripts/install_pi.sh
```

## Overview
PiCar-X Unified is a control stack for the SunFounder PiCar-X. It provides:
- A FastAPI backend with REST endpoints, MJPEG streaming, and WebSocket audio.
- Decoupled modules for voice, safety, vision, and behavior features.
- Compatibility with the official SunFounder PiCar-X hardware API.

### Architecture
The design layers include:
- **Browser UI**:
  - REST API
  - WebSocket voice loop.
- **Runtime Coordination**:
  - Safety guard, voice/audio, and vision modules.
- **Hardware Integration**:
  - Motors, camera pan/tilt, ultrasonic sensors through the SunFounder API.

For detailed usage, please consult the documentation in respective files.

## Quick Start
Start the API interface and dashboard:
```bash
docker-compose up
```
Access the dashboard at `http://<raspberry-pi-ip>:8080`.

For systemd integration, advanced configurations, or troubleshooting, refer to expanded documentation in the `/docs` directory if available.