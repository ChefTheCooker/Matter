# ============================================================
#  MATTER — core/smart_home.py
#  Matter's smart home controller.
#  Scans for Bluetooth & WiFi smart devices on startup,
#  connects automatically, and controls them by voice.
# ============================================================

import asyncio
import threading
import time
from core.config import ENABLE_LOGS


# ── Dependencies ──────────────────────────────────────────
#  pip install bleak              (Bluetooth)
#  pip install python-kasa        (TP-Link smart plugs/switches)
#  pip install homeassistant-api  (Home Assistant bridge - optional)

try:
    from bleak import BleakScanner, BleakClient
    BLUETOOTH_AVAILABLE = True
except ImportError:
    BLUETOOTH_AVAILABLE = False
    if ENABLE_LOGS:
        print("[SmartHome] bleak not installed. Bluetooth disabled.")

try:
    from kasa import Discover, SmartPlug, SmartBulb, SmartStrip
    KASA_AVAILABLE = True
except ImportError:
    KASA_AVAILABLE = False
    if ENABLE_LOGS:
        print("[SmartHome] python-kasa not installed. WiFi devices disabled.")


# ── Device Registry ───────────────────────────────────────
#  Stores all discovered devices in memory.
#  Format: { "device_name": { "type": "bluetooth/wifi", "object": <device> } }

_devices = {}
_scan_complete = False


# ── Friendly name map ─────────────────────────────────────
#  Maps common spoken names to device keywords to match against.

DEVICE_ALIASES = {
    "fan":          ["fan", "air"],
    "light":        ["light", "bulb", "lamp"],
    "dishwasher":   ["dishwasher", "dish"],
    "tv":           ["tv", "television", "screen"],
    "ac":           ["ac", "air conditioner", "aircon", "conditioner"],
    "heater":       ["heater", "heat"],
    "plug":         ["plug", "socket", "outlet"],
    "speaker":      ["speaker", "soundbar", "audio"],
    "kettle":       ["kettle", "water"],
    "washing":      ["washing", "washer", "laundry"],
}


# ── Bluetooth Scanner ─────────────────────────────────────

async def _scan_bluetooth():
    """
    Scans for nearby Bluetooth devices and registers them.
    """
    if not BLUETOOTH_AVAILABLE:
        return

    if ENABLE_LOGS:
        print("[SmartHome] Scanning for Bluetooth devices...")

    try:
        devices = await BleakScanner.discover(timeout=8.0)
        for device in devices:
            name = device.name or f"BT-{device.address}"
            _devices[name.lower()] = {
                "type":    "bluetooth",
                "address": device.address,
                "name":    name,
                "object":  device,
            }
            if ENABLE_LOGS:
                print(f"[SmartHome] Found Bluetooth device: {name}")

    except Exception as e:
        if ENABLE_LOGS:
            print(f"[SmartHome] Bluetooth scan error: {e}")


# ── WiFi / Kasa Scanner ───────────────────────────────────

async def _scan_wifi():
    """
    Scans for TP-Link Kasa smart devices on the local WiFi network.
    """
    if not KASA_AVAILABLE:
        return

    if ENABLE_LOGS:
        print("[SmartHome] Scanning for WiFi smart devices...")

    try:
        found = await Discover.discover(timeout=5)
        for ip, device in found.items():
            await device.update()
            name = device.alias.lower() if device.alias else f"wifi-{ip}"
            _devices[name] = {
                "type":   "wifi",
                "ip":     ip,
                "name":   device.alias or ip,
                "object": device,
            }
            if ENABLE_LOGS:
                print(f"[SmartHome] Found WiFi device: {device.alias} at {ip}")

    except Exception as e:
        if ENABLE_LOGS:
            print(f"[SmartHome] WiFi scan error: {e}")


# ── Startup Scan ──────────────────────────────────────────

def scan_all():
    """
    Runs Bluetooth + WiFi scans concurrently on startup.
    Non-blocking — runs in a background thread.
    """
    global _scan_complete

    def _run():
        global _scan_complete
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(asyncio.gather(
            _scan_bluetooth(),
            _scan_wifi(),
        ))
        loop.close()
        _scan_complete = True
        if ENABLE_LOGS:
            print(f"[SmartHome] Scan complete. {len(_devices)} device(s) found.")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def get_all_devices() -> dict:
    """
    Returns all discovered devices.
    """
    return _devices


def device_count() -> int:
    return len(_devices)


# ── Device Resolver ───────────────────────────────────────

def _resolve_device(spoken_name: str):
    """
    Matches a spoken device name to a registered device.
    Returns the device dict or None if not found.
    """
    spoken = spoken_name.lower().strip()

    # Direct match first
    if spoken in _devices:
        return _devices[spoken]

    # Alias match
    for alias, keywords in DEVICE_ALIASES.items():
        if any(kw in spoken for kw in keywords):
            for dev_name, dev in _devices.items():
                if any(kw in dev_name for kw in keywords):
                    return dev

    return None


# ── Device Control ────────────────────────────────────────

async def _control_wifi_device(device, action: str):
    """
    Controls a WiFi smart device.
    """
    await device["object"].update()
    obj = device["object"]

    if action == "on":
        await obj.turn_on()
    elif action == "off":
        await obj.turn_off()
    elif action == "toggle":
        if obj.is_on:
            await obj.turn_off()
        else:
            await obj.turn_on()


def control(device_name: str, action: str) -> str:
    """
    Main control function. Called by engine.py.
    Controls a device by spoken name and action.

    Parameters:
      device_name — e.g. "fan", "living room light"
      action      — "on", "off", "toggle"

    Returns a spoken response string.
    """
    if not _scan_complete:
        return "Sir, I am still scanning for devices. Please give me a moment."

    device = _resolve_device(device_name)

    if not device:
        return f"Sir, I could not find a device called {device_name}. Make sure it is on the same network or in Bluetooth range."

    name = device["name"]

    try:
        if device["type"] == "wifi":
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_control_wifi_device(device, action))
            loop.close()
            return f"Sir, {name} is now {action}."

        elif device["type"] == "bluetooth":
            # Generic Bluetooth toggle — device-specific logic can be added
            return f"Sir, Bluetooth control for {name} is connected but requires device-specific setup."

    except Exception as e:
        if ENABLE_LOGS:
            print(f"[SmartHome] Control error: {e}")
        return f"Sir, I had trouble controlling {name}. Please check the device."

    return f"Sir, I could not control {name}."


def list_devices() -> str:
    """
    Returns a spoken summary of all connected devices.
    """
    if not _devices:
        return "Sir, no smart devices were found on the network or in Bluetooth range."

    names = [d["name"] for d in _devices.values()]
    return f"Sir, I found {len(names)} device(s): {', '.join(names)}."