import threading

from picarx_unified.attacks.wifi_jammer import (
    JammerMode,
    JammerState,
    JammerStatus,
    WifiJammer,
)


def make_jammer():
    jammer = WifiJammer.__new__(WifiJammer)
    jammer._robot_network_bssid = None
    jammer._robot_network_essid = None
    return jammer


def test_parse_iw_scan_with_decimal_signal_and_interface_suffix():
    output = """
BSS 74:da:88:bf:10:a2(on wlan1)
        freq: 2417
        signal: -85.00 dBm
        SSID: TP-Link_10A2
        RSN:     * Version: 1
BSS 04:95:e6:19:de:b1(on wlan1)
        freq: 2412
        signal: -30.00 dBm
        SSID: SS
        WPA:     * Version: 1
"""

    networks = make_jammer()._parse_scan_results(output)

    assert len(networks) == 2
    assert networks[0].bssid == "74:DA:88:BF:10:A2"
    assert networks[0].essid == "TP-Link_10A2"
    assert networks[0].channel == 2
    assert networks[0].signal_strength == -85
    assert networks[0].encryption == "WPA/WPA2"
    assert networks[1].bssid == "04:95:E6:19:DE:B1"
    assert networks[1].channel == 1
    assert networks[1].signal_strength == -30


def test_jamming_loop_clears_running_state_when_duration_expires(monkeypatch):
    jammer = make_jammer()
    jammer.monitor_interface = "wlan1"
    jammer._stop_event = threading.Event()
    jammer._status_lock = threading.Lock()
    jammer._status = JammerStatus(
        state=JammerState.RUNNING,
        mode=JammerMode.MASS,
        target_bssid="AA:BB:CC:DD:EE:FF",
        channel=1,
        start_time=0.0,
    )
    jammer._protected_networks = {"AA:BB:CC:DD:EE:FF"}
    jammer._set_managed_mode = lambda: True
    times = iter([0.0, 1.0])
    monkeypatch.setattr("picarx_unified.attacks.wifi_jammer.time.time", lambda: next(times))
    monkeypatch.setattr("picarx_unified.attacks.wifi_jammer.time.sleep", lambda _: None)

    jammer._jamming_loop(
        mode=JammerMode.MASS,
        target_bssids=["AA:BB:CC:DD:EE:FF"],
        channel=None,
        packet_rate=100,
        duration=0.1,
    )

    assert jammer._status.state == JammerState.IDLE
    assert jammer._status.mode is None
    assert jammer._status.target_bssid is None
