# Installation Guide

## Quick Start

On a fresh Raspberry Pi 5, run:

```bash
bash scripts/install_pi.sh
```

That's it! The installer will:
- Install all system dependencies (including aircrack-ng for WiFi features)
- Install the SunFounder PiCar-X Python stack
- Create a Python virtual environment
- Set up the systemd service with all necessary permissions
- Start the application

Access the web interface at `http://<your-pi-ip>:8080`

## What Gets Installed

### System Packages
- `python3`, `python3-venv`, `python3-pip`
- `libcamera`, `python3-libcamera`, `python3-picamera2`
- `python3-opencv`
- `espeak-ng`, `alsa-utils` (for audio)
- `avahi-daemon` (for mDNS/bonjour)
- `aircrack-ng` (for WiFi scanning and client discovery)

### Python Packages
- `fastapi`, `uvicorn` (web server)
- `google-genai` (AI integration)
- `picarx` (SunFounder PiCar-X hardware control)

### Systemd Service
The service is configured with:
- Network capabilities (CAP_NET_RAW, CAP_NET_ADMIN) for WiFi monitor mode
- Hardware access (I2C, GPIO, SPI) for motor control
- Write permissions to `/root/picar-px` and `/opt/picar-x`
- Automatic restart on failure

## Manual Installation

If you prefer to install manually:

```bash
# 1. Install system packages
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip \
  libcamera-ipa libcamera0.3 python3-libcamera python3-opencv \
  python3-picamera2 espeak-ng alsa-utils avahi-daemon aircrack-ng

# 2. Install SunFounder PiCar-X stack
git clone --depth 1 -b v2.0 https://github.com/SunFounder/picar-x.git /tmp/picarx
cd /tmp/picarx
sudo python3 setup.py install
cd -
rm -rf /tmp/picarx

# 3. Create virtual environment
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install fastapi uvicorn[standard] filelock pydantic google-genai

# 4. Create PiCar-X config directory
sudo mkdir -p /opt/picar-x
sudo chown -R root:root /opt/picar-x
sudo chmod -R 777 /opt/picar-x

# 5. Install the package
pip install -e .

# 6. Copy and enable the service
sudo cp deploy/picarx-unified.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable picarx-unified.service
sudo systemctl start picarx-unified.service
```

## Troubleshooting

### Service won't start

Check the logs:
```bash
sudo journalctl -u picarx-unified.service -f
```

### Car doesn't move

Make sure the service has hardware permissions:
```bash
# Check service file has these lines:
# ProtectSystem=false
# ProtectHome=false
# ReadWritePaths=/root/picar-px /opt/picar-x
# CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_SYS_RAWIO
# DeviceAllow=/dev/i2c-* rw
# DeviceAllow=/dev/spidev*.* rw
# DeviceAllow=/dev/gpiochip* rw
# DeviceAllow=/dev/mem rw
```

### WiFi client discovery not working

Make sure aircrack-ng is installed:
```bash
which airodump-ng
# Should show: /usr/sbin/airodump-ng
```

Check monitor mode:
```bash
iw dev wlan1 info | grep type
# Should show: type monitor
```

## Service Management

```bash
# Check status
sudo systemctl status picarx-unified.service

# Start/stop/restart
sudo systemctl start picarx-unified.service
sudo systemctl stop picarx-unified.service
sudo systemctl restart picarx-unified.service

# Enable/disable on boot
sudo systemctl enable picarx-unified.service
sudo systemctl disable picarx-unified.service

# View logs
sudo journalctl -u picarx-unified.service -f
```

## Running Without Service

For development or testing, you can run directly:

```bash
source .venv/bin/activate
python -m picarx_unified
```

Or use the run script:
```bash
bash scripts/run_pi.sh
```
