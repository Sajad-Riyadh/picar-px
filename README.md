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

### WiFi Capabilities

The PiCar-X Unified project includes WiFi functionality enabling:
- Secure authorized network control.
- Enhanced connectivity via pre-configured WiFi modules.
- Educational module for demonstrating WiFi operations responsibly (includes network scanning options).

Refer to additional WiFi setup instructions in the `docs/wifi_features.md` file if available.

---

For full details about the architecture, features, and command details like systemd integrations, continue exploring the respective sections from the expanded README or inline code documentation when available.