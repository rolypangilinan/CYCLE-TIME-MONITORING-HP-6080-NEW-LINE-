"""
Arduino Serial Bridge for Cycle Time Monitoring
================================================
Reads serial data from Arduino and sends HTTP POST requests
to the Flask web server to trigger START/STOP buttons in the browser.

Usage:
  python arduino_bridge.py
  python arduino_bridge.py --port COM3
  python arduino_bridge.py --port COM3 --baud 9600
"""

import serial
import serial.tools.list_ports
import requests
import time
import sys
import argparse

# Flask server URL (default)
FLASK_URL = "http://127.0.0.1:5000"

def find_arduino_port(no_prompt=False):
    """Auto-detect Arduino COM port"""
    ports = serial.tools.list_ports.comports()
    print("\n=== Available COM Ports ===")
    for port in ports:
        print(f"  {port.device} - {port.description}")
    
    # Try to find Arduino automatically
    for port in ports:
        desc = port.description.lower()
        if 'arduino' in desc or 'ch340' in desc or 'usb serial' in desc or 'usb-serial' in desc:
            print(f"\n>>> Auto-detected Arduino on: {port.device}")
            return port.device
    
    # If no Arduino found, ask user (skip prompt in auto mode)
    if ports:
        print("\n>>> Could not auto-detect Arduino.")
        print(">>> Available ports:", [p.device for p in ports])
        if no_prompt:
            print(">>> Running in auto mode (--no-prompt), skipping interactive prompt.")
            return None
        port_input = input(">>> Enter COM port (e.g. COM3): ").strip()
        return port_input if port_input else None
    
    return None

def send_signal_to_flask(process_no, action):
    """Send Arduino signal to Flask server"""
    try:
        url = f"{FLASK_URL}/api/arduino_signal"
        payload = {
            "process_no": process_no,
            "action": action  # "start" or "stop"
        }
        response = requests.post(url, json=payload, timeout=2)
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                print(f"  -> Signal sent OK: Process {process_no} {action.upper()}")
            else:
                print(f"  -> Server error: {result.get('error', 'Unknown')}")
        else:
            print(f"  -> HTTP Error: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"  -> ERROR: Cannot connect to Flask server at {FLASK_URL}")
        print(f"           Make sure cycleTimeMoni.py is running!")
    except Exception as e:
        print(f"  -> ERROR sending signal: {e}")

def parse_serial_message(message):
    """
    Parse Arduino serial message.
    Expected format: P1START, P1STOP, P2START, ... P9STOP
    Returns (process_no, action) or (None, None) if invalid.
    """
    message = message.strip().upper()
    
    if not message.startswith("P"):
        return None, None
    
    # Try to extract process number and action
    for i in range(1, 10):
        prefix = f"P{i}"
        if message.startswith(prefix):
            remainder = message[len(prefix):]
            if remainder == "START":
                return i, "start"
            elif remainder == "STOP":
                return i, "stop"
    
    return None, None

def main():
    global FLASK_URL
    
    parser = argparse.ArgumentParser(description="Arduino Serial Bridge for Cycle Time Monitoring")
    parser.add_argument("--port", type=str, help="COM port (e.g. COM3)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument("--url", type=str, default=FLASK_URL, help=f"Flask server URL (default: {FLASK_URL})")
    parser.add_argument("--no-prompt", action="store_true", help="Skip interactive COM port prompt (for auto-launch mode)")
    args = parser.parse_args()
    
    FLASK_URL = args.url
    
    print("=" * 50)
    print("  ARDUINO SERIAL BRIDGE")
    print("  Cycle Time Monitoring System")
    print("=" * 50)
    print(f"  Flask Server: {FLASK_URL}")
    
    # Find Arduino port
    com_port = args.port if args.port else find_arduino_port(no_prompt=args.no_prompt)
    
    if not com_port:
        print("\nERROR: No COM port found. Please connect Arduino and try again.")
        print("       Or specify port manually: python arduino_bridge.py --port COM3")
        sys.exit(1)
    
    print(f"\n>>> Connecting to Arduino on {com_port} at {args.baud} baud...")
    
    try:
        ser = serial.Serial(com_port, args.baud, timeout=1)
        time.sleep(2)  # Wait for Arduino to reset after serial connection
        print(f">>> Connected successfully to {com_port}!")
        print(f">>> Listening for button presses...\n")
        print("-" * 50)
        
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
                
                # Skip Arduino ready message
                if line == "ARDUINO_READY":
                    print("  -> Arduino is ready!")
                    continue
                
                # Parse and forward signal
                process_no, action = parse_serial_message(line)
                if process_no and action:
                    send_signal_to_flask(process_no, action)
                else:
                    print(f"  -> Unknown message (ignored)")
            
            time.sleep(0.01)  # Small delay to prevent CPU spinning
            
    except serial.SerialException as e:
        print(f"\nERROR: Could not open {com_port}: {e}")
        print("Make sure:")
        print("  1. Arduino is connected")
        print("  2. The correct COM port is specified")
        print("  3. No other program is using the port (close Arduino IDE Serial Monitor)")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n>>> Bridge stopped by user (Ctrl+C)")
        if 'ser' in locals():
            ser.close()
        sys.exit(0)

if __name__ == "__main__":
    main()
