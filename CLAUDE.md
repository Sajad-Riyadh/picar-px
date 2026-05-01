# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PiCar-X Unified is a comprehensive control stack for a SunFounder PiCar-X robot running on Raspberry Pi 5. The project combines robot control, computer vision, AI capabilities, and cybersecurity demonstrations in a unified web-based interface.

**Core Philosophy**: Safety-first orchestration with clear service boundaries. The robot hardware layer is isolated from AI, voice, vision, and cybersecurity modules to prevent unauthorized motor control while enabling advanced features.

## Architecture

### Layered Design

```
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

### Key Modules

- **`RobotRuntime`**: Central orchestration boundary, manages all services and lifecycle
- **`PicarxAdapter`**: Only module that communicates with PiCar-X hardware API
- **`SafetyGuard`**: Clamps speed/steering/pan/tilt, blocks AI motor control, prevents forward motion when obstacles detected
- **`CameraService`**: Frame capture and MJPEG streaming
- **`VisionService`**: Scene analysis and face detection
- **`PersonGreeterBehavior`**: Tracks faces with pan/tilt servos and greets on cooldown
- **`AudioRouter`**: Routes sound to car speaker, browser speaker, or both
- **`VoiceConnection`**: Handles browser microphone chunks, relay mode, AI reply mode
- **`WifiJammer`**: Educational WiFi deauthentication attack module with safety protections

## Common Development Commands

### Installation and Setup

```bash
# One-file install and run (recommended for Raspberry Pi)
cd /path/to/Picar-px
bash scripts/install_pi.sh

# Install only (don't start app)
bash scripts/install_pi.sh --install-only

# Start already-installed setup
bash scripts/install_pi.sh --run-only

# Force mock hardware mode
bash scripts/install_pi.sh --mock

# Install and enable systemd service
bash scripts/install_pi.sh --service
```

### Running the Application

```bash
# Start with default settings
bash scripts/run_pi.sh

# Start with custom host/port
bash scripts/install_pi.sh --run-only --host 0.0.0.0 --port 8080

# Direct Python execution
python -m picarx_unified

# Using virtual environment
source .venv/bin/activate
python -m picarx_unified
```

### Systemd Service Management

```bash
# Check service status
sudo systemctl status picarx-unified.service

# Start/stop/restart service
sudo systemctl start picarx-unified.service
sudo systemctl stop picarx-unified.service
sudo systemctl restart picarx-unified.service

# Enable/disable on boot
sudo systemctl enable picarx-unified.service
sudo systemctl disable picarx-unified.service

# View service logs
sudo journalctl -u picarx-unified.service -f
```

### Testing and Debugging

```bash
# Health check
curl http://127.0.0.1:8080/api/health

# Test drive control
curl -X POST http://127.0.0.1:8080/api/drive \
  -H "Content-Type: application/json" \
  -d '{"speed": 25, "steering": 0, "source": "ssh"}'

# Stop the robot
curl -X POST http://127.0.0.1:8080/api/drive/stop

# Test camera movement
curl -X POST http://127.0.0.1:8080/api/camera \
  -H "Content-Type: application/json" \
  -d '{"pan": 15, "tilt": -5}'

# Test WiFi jammer scan
curl "http://127.0.0.1:8080/api/jammer/scan?duration=10"

# Get current state
curl http://127.0.0.1:8080/api/state
```

## Configuration

### Environment Variables

Key configuration is managed through `.env` file (created from `.env.example`):

```bash
# Hardware settings
PICARX_USE_MOCK=false              # Use mock hardware (true for camera-only mode)
PICARX_HARDWARE_INIT_MODE=direct   # Hardware initialization: direct/auto/mock

# Camera settings
PICARX_CAMERA_WIDTH=640
PICARX_CAMERA_HEIGHT=480
PICARX_CAMERA_FPS=20
PICARX_CAMERA_FORCE_BACKEND=auto  # picamera2/opencv/auto
PICARX_CAMERA_FULL_FOV=true       # Disable digital zoom

# Safety limits
PICARX_MAX_SPEED=50
PICARX_STEERING_LIMIT=30
PICARX_PAN_LIMIT=70
PICARX_TILT_UP_LIMIT=35
PICARX_TILT_DOWN_LIMIT=-35
PICARX_OBSTACLE_STOP_CM=18.0

# Network settings
PICARX_HOST=0.0.0.0
PICARX_PORT=8080
PICARX_API_TOKEN=optional_token    # Bearer token for API protection

# AI settings (optional)
GEMINI_API_KEY=your_key_here
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
```

### Hardware Initialization Modes

- **`direct`**: Initializes SunFounder `Picarx()` at startup (default for real hardware)
- **`auto`**: Starts with mock and probes in background (safer for boot timing)
- **`mock`**: Uses mock hardware for camera/API/AI testing without motor control

## Important Technical Concepts

### Safety System

The safety system is multi-layered and **cannot be bypassed**:

1. **Speed Clamping**: All drive commands are clamped to `PICARX_MAX_SPEED`
2. **Steering Limits**: Front wheel steering limited to `PICARX_STEERING_LIMIT`
3. **Pan/Tilt Limits**: Camera movement constrained to configured limits
4. **Obstacle Detection**: Forward motion blocked when ultrasonic sensor detects objects within `PICARX_OBSTACLE_STOP_CM`
5. **Watchdog Timer**: Drive commands expire after `PICARX_DRIVE_WATCHDOG_SECONDS`
6. **Emergency Stop**: Explicit emergency stop blocks all motion until released
7. **AI Protection**: AI modules cannot directly control motors

**Never modify safety limits** without understanding the physical consequences.

### WiFi Jammer Module

The WiFi Jammer (`src/picarx_unified/attacks/wifi_jammer.py`) is an **educational cybersecurity module** with strict safety requirements:

#### Legal Requirements

⚠️ **CRITICAL**: This module is for educational and authorized security testing ONLY.

- Only use on networks you own or have explicit written permission
- Unauthorized use is illegal and unethical
- Users are solely responsible for their actions
- This demonstrates 802.11 vulnerabilities for research purposes

#### Technical Implementation

- **Attack Modes**: Mass (selected networks), Targeted (single BSSID), Client (specific devices)
- **Protection**: Automatically protects robot's management network (`wlan0`)
- **Isolation**: Runs in separate thread to avoid blocking robot control
- **Dependencies**: Scapy for packet crafting, Aircrack-ng for network scanning

#### Key Safety Features

1. **Network Protection**: Robot's own network cannot be attacked
2. **Input Validation**: BSSID format, channel ranges, packet rates validated
3. **Thread Safety**: Lock-based state management prevents concurrent attacks
4. **Error Handling**: Comprehensive error checking and logging
5. **Legal Warnings**: Requires user acknowledgment before attacks

#### Common Issues

- **PMF/802.11w**: Modern networks with Protected Management Frames cannot be attacked
- **Packet Rate**: Default 200 pps, max 1000 pps. Higher rates needed for stubborn connections
- **Monitor Mode**: Interface must be in monitor mode (`iw dev wlan1 set type monitor`)
- **Distance**: Attacks ineffective beyond 15 meters due to signal strength

### Camera System

The camera system supports multiple backends with automatic fallback:

1. **Picamera2** (preferred on Raspberry Pi): Native Pi camera support
2. **OpenCV**: Cross-platform camera capture
3. **Mock**: For testing without hardware

**Color Issues**: If browser video has wrong colors, check:
- Backend: `curl http://127.0.0.1:8080/api/health`
- Format: Set `PICARX_CAMERA_FORMAT=RGB888`
- Conversion: Set `PICARX_CAMERA_COLOR_FIX=auto`

**Zoom Issues**: If video looks cropped, ensure:
- `PICARX_CAMERA_FULL_FOV=true`
- `PICARX_CAMERA_DISABLE_SCALER_CROP=true`

### Voice and Audio

The voice system supports three modes:

1. **Relay Mode**: Browser microphone → car/browser speaker (real-time)
2. **AI Reply Mode**: Browser microphone → AI processing → speech synthesis
3. **Mute Mode**: Audio disabled

**Microphone Requirements**: Browser microphone requires HTTPS or localhost context:
- Use SSH tunnel: `ssh -L 8080:127.0.0.1:8080 car@192.168.2.249`
- Then access: `http://localhost:8080/`
- Or enable HTTPS with self-signed certificates

## Development Guidelines

### Adding New Features

1. **Hardware Changes**: Only modify `PicarxAdapter` for hardware access
2. **Safety Changes**: Never bypass safety limits without explicit justification
3. **API Changes**: Add endpoints to `app.py`, update models in `models.py`
4. **UI Changes**: Update `index.html`, `app.js`, and `styles.css` together
5. **Configuration**: Add new env vars to `config.py` and `.env.example`

### Testing New Features

1. **Mock Mode**: Test with `PICARX_USE_MOCK=true` first
2. **Safety Verification**: Ensure safety limits still apply
3. **API Testing**: Use curl to test endpoints before UI integration
4. **Hardware Testing**: Test on real hardware after mock validation
5. **Service Testing**: Verify systemd service works correctly

### Code Organization

- **Hardware Layer**: `src/picarx_unified/hardware/` - Only place for hardware access
- **Safety Layer**: `src/picarx_unified/safety.py` - All safety constraints
- **Business Logic**: `src/picarx_unified/*.py` - Application logic
- **Cybersecurity**: `src/picarx_unified/attacks/` - Security modules
- **Web Layer**: `src/picarx_unified/app.py` - API endpoints
- **UI Layer**: `src/picarx_unified/static/` - Browser interface

### Common Patterns

#### Dependency Injection

```python
# Use FastAPI dependency injection for runtime access
def _get_runtime(request: Request) -> RobotRuntime:
    return request.app.state.runtime

# Use in endpoints
@app.post("/api/drive")
async def drive(
    request: Request,
    command: DriveRequest,
    runtime: RobotRuntime = Depends(_get_runtime),
):
    return runtime.apply_drive(command)
```

#### Error Handling

```python
# Use SafetyViolation for safety-related errors
try:
    return runtime.apply_drive(command)
except SafetyViolation as exc:
    runtime.record_error(str(exc))
    raise HTTPException(status_code=409, detail=str(exc)) from exc
```

#### Configuration Access

```python
# Access config through runtime
config = runtime.config
max_speed = config.drive_max_speed

# Or use AppConfig directly
from .config import AppConfig
config = AppConfig.from_env()
```

## Troubleshooting

### Common Issues

**Camera not working**:
- Check backend: `curl http://127.0.0.1:8080/api/health`
- Verify Picamera2 installation: `pip list | grep picamera`
- Test with `rpicam-hello -t 3000`

**Motors not moving**:
- Check safety status: `curl http://127.0.0.1:8080/api/state`
- Verify not in emergency stop
- Check obstacle sensor readings
- Ensure not in mock mode

**WiFi Jammer not working**:
- Verify Scapy installed: `pip list | grep scapy`
- Check monitor mode: `iw dev wlan1 info | grep type`
- Test packet injection: `sudo aireplay-ng -9 wlan1`
- Review `DEAUTH_TROUBLESHOOTING.md`

**Microphone not working**:
- Check secure context: Browser DevTools → Console
- Use SSH localhost tunnel or enable HTTPS
- Verify browser permissions

### Debug Mode

Enable detailed logging by setting environment variable:

```bash
export PYTHONUNBUFFERED=1
export LOG_LEVEL=DEBUG
python -m picarx_unified
```

## Security Considerations

### API Protection

Enable bearer token authentication:

```bash
# Set in .env
PICARX_API_TOKEN=your_secure_token_here

# Use in requests
curl -X POST http://127.0.0.1:8080/api/drive \
  -H "Authorization: Bearer your_secure_token_here" \
  -H "Content-Type: application/json" \
  -d '{"speed": 25, "steering": 0}'
```

### Network Security

- **HTTPS**: Enable for production deployments
- **Firewall**: Restrict access to trusted networks
- **API Token**: Always use token authentication on exposed networks
- **WiFi Jammer**: Never use on unauthorized networks

### Legal Compliance

**WiFi Jammer Module**:
- Only test on networks you own
- Get explicit written permission before testing
- Document all authorized testing
- Stop immediately if unintended effects occur
- Comply with local laws and regulations

## Performance Optimization

### Camera Performance

- Use appropriate resolution: 640x480 is usually sufficient
- Adjust FPS based on processing needs: 20 FPS is default
- Enable full FOV to avoid digital zoom overhead
- Use Picamera2 backend on Raspberry Pi for best performance

### System Resources

- Monitor CPU usage: `top` or `htop`
- Check memory: `free -h`
- Monitor disk I/O: `iostat`
- Review service logs: `journalctl -u picarx-unified.service`

### Network Performance

- Use wired Ethernet when possible
- For WiFi, ensure strong signal strength
- Consider local network only (no internet exposure)
- Monitor bandwidth usage during camera streaming

## Future Development

### Planned Improvements

- Replace Haar face detection with MediaPipe or lightweight YOLO
- Upgrade WebSocket voice to WebRTC for lower latency
- Add offline STT with `faster-whisper`
- Implement capability registry for security modules
- Add audit logging and role-based permissions
- Create behavior policy engine for autonomy features
- Add vision memory layer for temporal questions
- Implement battery telemetry and IMU panels

### Extension Points

- **New Behaviors**: Add to `src/picarx_unified/behaviors.py`
- **New Security Modules**: Add to `src/picarx_unified/attacks/`
- **New AI Providers**: Extend `src/picarx_unified/ai.py`
- **New Camera Backends**: Extend `src/picarx_unified/hardware/camera.py`

## References

- **SunFounder PiCar-X**: https://github.com/SunFounder/picar-x
- **PiCar-X Documentation**: https://docs.sunfounder.com/projects/picar-x-v20/en/latest/
- **FastAPI**: https://fastapi.tiangolo.com/
- **Scapy**: https://scapy.net
- **Aircrack-ng**: https://www.aircrack-ng.org
- **IEEE 802.11**: Wireless LAN standards

## Support

For issues specific to this project:
- Check existing documentation in `README.md`
- Review troubleshooting guides in `DEAUTH_TROUBLESHOOTING.md`
- Examine service logs: `journalctl -u picarx-unified.service`
- Test with mock hardware first: `PICARX_USE_MOCK=true`

For SunFounder PiCar-X hardware issues:
- Refer to official SunFounder documentation
- Check hardware connections and calibration
- Verify Robot HAT installation
- Test with official SunFounder software