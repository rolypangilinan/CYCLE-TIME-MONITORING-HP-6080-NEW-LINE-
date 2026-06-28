"""
Arduino Serial Bridge for Material Setter (ESP-12E)
====================================================
Reads serial data from ESP-12E (NodeMCU) and sends HTTP POST requests
to the Flask web server to handle Material Setter button signals.

Usage:
  python arduino_bridge_ms.py
  python arduino_bridge_ms.py --port COM5
  python arduino_bridge_ms.py --port COM5 --baud 9600
"""

import serial
import serial.tools.list_ports
import requests
import time
import sys
import argparse

# Flask server URL (default)
FLASK_URL = "http://127.0.0.1:5001"

def find_esp_port(no_prompt=False):
    """Auto-detect ESP-12E COM port"""
    ports = serial.tools.list_ports.comports()
    print("\n=== Available COM Ports ===")
    for port in ports:
        print(f"  {port.device} - {port.description}")
    
    # Try to find ESP automatically (CP2102/CH340 are common ESP USB chips)
    for port in ports:
        desc = port.description.lower()
        if 'cp210' in desc or 'ch340' in desc or 'usb serial' in desc or 'usb-serial' in desc:
            print(f"\n>>> Auto-detected ESP on: {port.device}")
            return port.device
    
    # If not found, ask user
    if ports:
        print("\n>>> Could not auto-detect ESP-12E.")
        print(">>> Available ports:", [p.device for p in ports])
        if no_prompt:
            print(">>> Running in auto mode (--no-prompt), skipping interactive prompt.")
            return None
        port_input = input(">>> Enter COM port for ESP-12E (e.g. COM5): ").strip()
        return port_input if port_input else None
    
    return None

def send_ms_signal_to_flask(signal_type):
    """Send Material Setter button signal to Flask server"""
    try:
        url = f"{FLASK_URL}/api/ms_arduino_signal"
        payload = {"signal": signal_type}
        response = requests.post(url, json=payload, timeout=2)
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                print(f"  -> MS Signal sent OK: {signal_type} (state: {result.get('state')})")
            else:
                print(f"  -> Server error: {result.get('error', 'Unknown')}")
        else:
            print(f"  -> HTTP Error: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"  -> ERROR: Cannot connect to Flask server at {FLASK_URL}")
        print(f"           Make sure cycleTimeMoni.py is running!")
    except Exception as e:
        print(f"  -> ERROR sending MS signal: {e}")

def parse_ms_message(message):
    """
    Parse ESP-12E serial message for Material Setter.
    Expected: MS1LOAD, MS1UNLOAD, MS2OPEN, P1START_MS
    Returns signal string or None if invalid.
    """
    message = message.strip().upper()
    if message in ("MS1LOAD", "MS1UNLOAD", "MS2OPEN", "P1START_MS"):
        return message
    return None

def main():
    global FLASK_URL
    
    parser = argparse.ArgumentParser(description="ESP-12E Serial Bridge for Material Setter")
    parser.add_argument("--port", type=str, help="COM port (e.g. COM5)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument("--url", type=str, default=FLASK_URL, help=f"Flask server URL (default: {FLASK_URL})")
    parser.add_argument("--no-prompt", action="store_true", help="Skip interactive COM port prompt")
    args = parser.parse_args()
    
    FLASK_URL = args.url
    
    print("=" * 50)
    print("  ESP-12E SERIAL BRIDGE")
    print("  Material Setter Button Controller")
    print("=" * 50)
    print(f"  Flask Server: {FLASK_URL}")
    
    # Find ESP port
    com_port = args.port if args.port else find_esp_port(no_prompt=args.no_prompt)
    
    if not com_port:
        print("\nERROR: No COM port found. Please connect ESP-12E and try again.")
        print("       Or specify port manually: python arduino_bridge_ms.py --port COM5")
        sys.exit(1)
    
    print(f"\n>>> Connecting to ESP-12E on {com_port} at {args.baud} baud...")
    
    # Retry connection up to 5 times
    MAX_RETRIES = 5
    RETRY_DELAY = 3
    ser = None
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            ser = serial.Serial(com_port, args.baud, timeout=1)
            time.sleep(2)  # Wait for ESP to reset after serial connection
            print(f">>> Connected successfully to {com_port}!")
            break
        except serial.SerialException as e:
            if attempt < MAX_RETRIES:
                print(f"    [Retry {attempt}/{MAX_RETRIES}] {com_port} busy ({e}) - retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"\nERROR: Could not open {com_port} after {MAX_RETRIES} attempts: {e}")
                print("Make sure:")
                print("  1. ESP-12E is connected via USB")
                print("  2. The correct COM port is specified")
                print("  3. No other program is using the port")
                sys.exit(1)

    print(f">>> Listening for Material Setter button presses...\n")
    print("-" * 50)
    
    try:
        while True:
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8').strip()
                except UnicodeDecodeError:
                    continue
                
                if not line:
                    continue
                
                # Print raw serial data
                timestamp = time.strftime("%H:%M:%S")
                print(f"[{timestamp}] Received: {line}")
                
                # Skip ESP ready message
                if line == "ESP_READY":
                    print("  -> ESP-12E is ready!")
                    continue
                
                # Parse and forward signal
                signal = parse_ms_message(line)
                if signal:
                    send_ms_signal_to_flask(signal)
                else:
                    print(f"  -> Unknown message (ignored)")
            
            time.sleep(0.01)
    except serial.SerialException as e:
        print(f"\nERROR: Serial connection lost: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n>>> MS Bridge stopped by user (Ctrl+C)")
        if ser:
            ser.close()
        sys.exit(0)

if __name__ == "__main__":
    main()
