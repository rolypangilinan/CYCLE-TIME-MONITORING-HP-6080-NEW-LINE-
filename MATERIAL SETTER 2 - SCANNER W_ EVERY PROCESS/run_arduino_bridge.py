import os
import subprocess
import sys

def run_arduino_bridge():
    """Change directory and run arduino_bridge.py automatically"""
    
    # Target directory
    target_dir = r"c:\Users\Admin\Desktop\NEW HP 60_80 LINE\CYCLE TIME MONITORING\SAVE\WORKING 16B 1D 1A9"
    
    try:
        # Change to the target directory
        print(f"Changing directory to: {target_dir}")
        os.chdir(target_dir)
        print("Directory changed successfully!")
        
        # Run arduino_bridge.py
        print("Starting arduino_bridge.py...")
        print("-" * 50)
        
        # Use subprocess to run the Python script
        subprocess.run([sys.executable, "arduino_bridge.py"], check=True)
        
    except FileNotFoundError:
        print(f"ERROR: Directory not found: {target_dir}")
        print("Please check the path and try again.")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to run arduino_bridge.py: {e}")
    except KeyboardInterrupt:
        print("\nScript stopped by user.")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    run_arduino_bridge()
