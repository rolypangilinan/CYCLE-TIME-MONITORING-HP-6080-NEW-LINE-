# Import tools needed to build a website
# Flask: The main tool that creates our website
# request: Helps handle user clicks and form submissions
# render_template: Shows our HTML pages to visitors
# jsonify: For returning JSON responses to AJAX calls
from flask import Flask, request, render_template, jsonify
from database_manager  import DatabaseManager
import threading
import time

import json
import os
import subprocess
import sys

import torisql
import pandas as pd
import qr_printer

# CSV file path for FALSE TEST database
FALSE_TEST_CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'TORITANI DATABASE HIPROC.csv')

# Initialize database manager
db_manager = DatabaseManager()

# Create our website using Flask
# This line starts up our web application
app = Flask(__name__)

@app.after_request
def add_no_cache_headers(response):
    """Prevent browser from caching HTML pages so users always get the latest code"""
    if 'text/html' in response.content_type:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# Arduino signal queue: stores pending signals from the Arduino bridge
# Format: { process_no: {"action": "start"/"stop", "timestamp": time.time()} }
arduino_signals = {}
arduino_signals_lock = threading.Lock()

# ==================== SERVER-SIDE TIMER TRACKING ====================
# Tracks active timers server-side so Arduino START works even when browser page is closed
# Format: { process_no: {"start_time": time.time(), "kitting_no": N} }
server_timers = {}
server_timers_lock = threading.Lock()

# Server-side counter tracking per process
# Format: { process_no: counter_value }
server_counters = {}
server_counters_lock = threading.Lock()

# Server-side blocked counters tracking (replaces localStorage blocked_counters)
# Format: { process_no: [list of blocked kitting numbers] }
server_blocked_counters = {}
server_blocked_counters_lock = threading.Lock()

# Server-side active kitting tracking (which process is working on which kitting)
# Format: { process_no: kitting_no }
server_active_kittings = {}
server_active_kittings_lock = threading.Lock()

# Tracks when data was last updated (for auto-refresh on graph pages)
last_data_update = {"timestamp": time.time()}
last_data_update_lock = threading.Lock()

# Tracks the last date the system was active (for daily auto-reset)
last_active_date = {"date": None}
last_active_date_lock = threading.Lock()

# Tracks when a new job order started (for graph filtering)
job_order_start_time = {"timestamp": None}
job_order_start_time_lock = threading.Lock()

# Tracks if any process has started running today (to disable manpower warning after first start)
# Once any process starts, the warning is disabled until next day reset
processes_started_today = {"started": False}
processes_started_today_lock = threading.Lock()

# Server start timestamp for auto-reload detection
# When browser detects this changed, it will auto-refresh
SERVER_START_TIME = time.time()

# File to persist timer state across Flask restarts
TIMER_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server_timer_state.json')

# File to persist last active date across Flask restarts
LAST_DATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'last_active_date.json')

# File to persist job order start time across Flask restarts
JOB_ORDER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'job_order_start.json')

def save_last_active_date(date_str):
    """Save last active date to file"""
    try:
        with open(LAST_DATE_FILE, 'w') as f:
            json.dump({"date": date_str}, f)
        print(f"Saved last active date to file: {date_str}")
    except Exception as e:
        print(f"Error saving last active date: {e}")

def load_last_active_date():
    """Load last active date from file on startup"""
    try:
        if os.path.exists(LAST_DATE_FILE):
            with open(LAST_DATE_FILE, 'r') as f:
                data = json.load(f)
            date_str = data.get("date")
            if date_str:
                with last_active_date_lock:
                    last_active_date["date"] = date_str
                print(f"Loaded last active date from file: {date_str}")
                return date_str
    except Exception as e:
        print(f"Error loading last active date: {e}")
    return None

def save_job_order_start_time(timestamp_str):
    """Save job order start time to file"""
    try:
        with open(JOB_ORDER_FILE, 'w') as f:
            json.dump({"timestamp": timestamp_str}, f)
        print(f"Saved job order start time to file: {timestamp_str}")
    except Exception as e:
        print(f"Error saving job order start time: {e}")

def load_job_order_start_time():
    """Load job order start time from file on startup"""
    try:
        if os.path.exists(JOB_ORDER_FILE):
            with open(JOB_ORDER_FILE, 'r') as f:
                data = json.load(f)
            timestamp_str = data.get("timestamp")
            if timestamp_str:
                with job_order_start_time_lock:
                    job_order_start_time["timestamp"] = timestamp_str
                print(f"Loaded job order start time from file: {timestamp_str}")
                return timestamp_str
    except Exception as e:
        print(f"Error loading job order start time: {e}")
    return None

def set_new_job_order_start():
    """Set a new job order start time (called when all processes have same kitting)"""
    from datetime import datetime
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with job_order_start_time_lock:
        job_order_start_time["timestamp"] = timestamp_str
    save_job_order_start_time(timestamp_str)
    print(f"New job order started at: {timestamp_str}")
    return timestamp_str

def check_all_processes_same_kitting():
    """Check if all 9 processes have the same completed count (kitting value).
    If they do, it means a job order is complete and we should reset the graph.
    Runs in background thread to avoid blocking the response."""
    def _check():
        try:
            counts = []
            for i in range(1, 10):
                count = db_manager.get_completed_count(i)
                counts.append(count)
            
            # Check if all counts are the same AND greater than 0
            if len(set(counts)) == 1 and counts[0] > 0:
                print(f"ALL PROCESSES REACHED SAME KITTING VALUE: {counts[0]} - Starting new job order for graph")
                set_new_job_order_start()
                return True
            return False
        except Exception as e:
            print(f"Error checking all processes same kitting: {e}")
            return False
    
    # Run in background thread so it doesn't block the API response
    threading.Thread(target=_check, daemon=True).start()

def save_timer_state_to_file():
    """Persist server timer and counter state to file (runs in background thread)"""
    def _save():
        try:
            with server_timers_lock:
                timers_copy = {str(k): v for k, v in server_timers.items()}
            with server_counters_lock:
                counters_copy = {str(k): v for k, v in server_counters.items()}
            state = {'timers': timers_copy, 'counters': counters_copy}
            with open(TIMER_STATE_FILE, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            print(f"Error saving timer state to file: {e}")
    
    # Run in background thread so it doesn't block the API response
    threading.Thread(target=_save, daemon=True).start()

def load_timer_state_from_file():
    """Load server timer and counter state from file on startup"""
    try:
        if os.path.exists(TIMER_STATE_FILE):
            with open(TIMER_STATE_FILE, 'r') as f:
                state = json.load(f)
            now = time.time()
            max_age = 7200  # Discard timers older than 2 hours (stale from previous session)
            loaded_timers = 0
            with server_timers_lock:
                for k, v in state.get('timers', {}).items():
                    age = now - v.get('start_time', 0)
                    if age <= max_age:
                        server_timers[int(k)] = v
                        loaded_timers += 1
                    else:
                        print(f"Discarding stale timer for Process {k} (age: {int(age)}s)")
            with server_counters_lock:
                for k, v in state.get('counters', {}).items():
                    server_counters[int(k)] = int(v)
            print(f"Loaded timer state from file: {loaded_timers} active timers, {len(server_counters)} counters")
    except Exception as e:
        print(f"Error loading timer state from file: {e}")

def update_last_data_timestamp():
    """Update the last data change timestamp"""
    with last_data_update_lock:
        last_data_update["timestamp"] = time.time()

def check_daily_reset():
    """Check if it's a new day and perform daily reset if needed.
    Resets: kitting counters, manpower, and clears graph data."""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    
    with last_active_date_lock:
        if last_active_date["date"] is None:
            # First run, just set the date and save to file
            last_active_date["date"] = today
            save_last_active_date(today)
            print(f"Daily reset check: First run, setting date to {today}")
            return False
        
        if last_active_date["date"] != today:
            # New day detected - perform full reset
            print(f"DAILY RESET TRIGGERED: New day detected ({last_active_date['date']} -> {today})")
            old_date = last_active_date["date"]
            last_active_date["date"] = today
            save_last_active_date(today)
            
            # Reset all server state
            with server_timers_lock:
                server_timers.clear()
            with server_counters_lock:
                server_counters.clear()
            with arduino_signals_lock:
                arduino_signals.clear()
            with server_blocked_counters_lock:
                server_blocked_counters.clear()
            with server_active_kittings_lock:
                server_active_kittings.clear()
            
            # Reset processes started flag for new day
            with processes_started_today_lock:
                processes_started_today["started"] = False
            
            # Delete timer state file
            try:
                if os.path.exists(TIMER_STATE_FILE):
                    os.remove(TIMER_STATE_FILE)
            except:
                pass
            save_timer_state_to_file()
            
            # Reset database: counters, manpower, and records
            db_manager.reset_all_for_new_day()
            
            update_last_data_timestamp()
            
            print(f"Daily reset completed: counters, manpower, and records cleared (was {old_date}, now {today})")
            return True
    return False

def clear_all_server_state():
    """Clear all server-side timers, counters, and the state file"""
    with server_timers_lock:
        server_timers.clear()
    with server_counters_lock:
        server_counters.clear()
    with arduino_signals_lock:
        arduino_signals.clear()
    try:
        if os.path.exists(TIMER_STATE_FILE):
            os.remove(TIMER_STATE_FILE)
            print("Deleted server_timer_state.json")
    except Exception as e:
        print(f"Error deleting timer state file: {e}")
    save_timer_state_to_file()
    print("All server timers, counters, and Arduino signals cleared")

def initialize_processes_started_today():
    """Check database on startup to see if any processes have run today.
    If records exist for today, set processes_started_today to True."""
    try:
        has_records = db_manager.has_records_today()
        with processes_started_today_lock:
            processes_started_today["started"] = has_records
        if has_records:
            print("STARTUP: Found records for today - manpower warning disabled")
        else:
            print("STARTUP: No records for today - manpower warning enabled")
    except Exception as e:
        print(f"Error checking today's records on startup: {e}")

# This is the main menu route
# When someone visits our website's main address, this code runs
@app.route("/")
def main_menu():
    # Show the main menu to the visitor
    # This is like opening the front door of our website
    return render_template('main_menu.html')

# This is the Cycle Time Monitoring homepage route
@app.route("/cycle_time_home")
def cycle_time_home():
    # Show the Cycle Time Monitoring homepage
    return render_template('home.html')

# Page for Process 1
# When someone goes to website.com/process1 or process1.html, they see this page
@app.route("/process1")
@app.route("/process1.html")
@app.route("/process1.HTML")
def process1():
    # Show the Process 1 monitoring page
    return render_template('process1.html')

# Page for Process 2
# When someone goes to website.com/process2 or process2.html, they see this page
@app.route("/process2")
@app.route("/process2.html")
@app.route("/process2.HTML")
def process2():
    # Show the Process 2 monitoring page
    return render_template('process2.html')

# Page for Process 3
# When someone goes to website.com/process3 or process3.html, they see this page
@app.route("/process3")
@app.route("/process3.html")
@app.route("/process3.HTML")
def process3():
    # Show the Process 3 monitoring page
    return render_template('process3.html')

# Page for Process 4
# When someone goes to website.com/process4 or process4.html, they see this page
@app.route("/process4")
@app.route("/process4.html")
@app.route("/process4.HTML")
def process4():
    # Show the Process 4 monitoring page
    return render_template('process4.html')

# Page for Process 5
# When someone goes to website.com/process5 or process5.html, they see this page
@app.route("/process5")
@app.route("/process5.html")
@app.route("/process5.HTML")
def process5():
    # Show the Process 5 monitoring page
    return render_template('process5.html')

# Page for Process 6
# When someone goes to website.com/process6 or process6.html, they see this page
@app.route("/process6")
@app.route("/process6.html")
@app.route("/process6.HTML")
def process6():
    # Show the Process 6 monitoring page
    return render_template('process6.html')

# Page for Process 7
# When someone goes to website.com/process7 or process7.html, they see this page
@app.route("/process7")
@app.route("/process7.html")
@app.route("/process7.HTML")
def process7():
    # Show the Process 7 monitoring page
    return render_template('process7.html')

# Page for Process 8
# When someone goes to website.com/process8 or process8.html, they see this page
@app.route("/process8")
@app.route("/process8.html")
@app.route("/process8.HTML")
def process8():
    # Show the Process 8 monitoring page
    return render_template('process8.html')

# Page for Process 9
# When someone goes to website.com/process9 or process9.html, they see this page
@app.route("/process9")
@app.route("/process9.html")
@app.route("/process9.HTML")
def process9():
    # Show the Process 9 monitoring page
    return render_template('process9.html')

# Settings page
@app.route("/settings")
def settings():
    # Show the settings page
    return render_template('settings.html')

# Standard time configuration page
@app.route("/standard_time")
def standard_time():
    # Show the standard time configuration page
    return render_template('standard_time.html')

# Manpower configuration page
@app.route("/manpower")
def manpower():
    # Show the manpower configuration page
    return render_template('manpower.html')

# Cycle Time Graph Monitoring page
@app.route("/cycle_graph")
def cycle_graph():
    # Show the cycle time graph monitoring page
    return render_template('cycle_graph.html')

# Line Trend Graph Monitoring page
@app.route("/line_trend")
def line_trend():
    # Show the line trend graph monitoring page
    return render_template('line_trend.html')

# Material Setter page
@app.route("/material_setter")
def material_setter():
    # Get database type from query parameter
    db_type = request.args.get('db', 'toritani')
    
    # Set database name for display
    if db_type == 'falsetest':
        db_name = 'FALSE TEST'
    else:
        db_name = 'TORITANI SAN DATABASE'
    
    # Show the material setter page with database info
    return render_template('material_setter.html', db_name=db_name, db_type=db_type)

# Kitting material categories for matching (row_no -> category keyword)
# These keywords are searched in MaterialDescription column of torisql.py
KITTING_MATERIAL_CATEGORIES = {
    1: 'FRAME ZAM',
    2: 'FRAME LEAD',
    3: 'SPACER',
    4: '2P',
    5: 'P3P',
    6: 'DF BLOCK',
    7: 'ROD',
    8: 'CASING',
    9: 'PARTITION BOARD',
    10: 'L-TUBE',
    11: 'HOSE CLIP',
    12: 'SWITCH',
    13: 'LEAD BUSHING',
    14: 'GROUND WIRE',
    15: 'V.C.R',
    16: 'LOWER HOUSING',
    17: 'RUBBER FOOT',
    18: 'POWER CORD',
    19: 'PARTITION GASKET',
    20: 'UPPER HOUSING',
    21: 'FILTER COVER',
    22: 'FILTER',
    23: 'SOUND ABSORB',
    24: 'MANUAL',
    25: 'L-HOSE SET',
    26: 'FILTER BUSHING'
}

@app.route("/getQuantityAndSuffix", methods=["GET", "POST"])
def getQuantityAndSuffix():
    data = request.get_json()
    job_order_raw = data.get("job_order_raw")
    db_type = data.get("db_type", "toritani")
    
    print(f"JOB ORDER RAW '{job_order_raw}' (len={len(str(job_order_raw)) if job_order_raw else 0}), DB TYPE: {db_type}")

    if db_type == 'falsetest':
        # For FALSE TEST database, read suffix from CSV
        try:
            job_order = str(job_order_raw)[:10]
            suffix = job_order_raw[13:] if len(job_order_raw) > 13 else '0'
            suffix = suffix.strip()[:4] if suffix else '0'
            
            # Read CSV and find matching job order
            df = pd.read_csv(FALSE_TEST_CSV_PATH)
            job_data = df[df['job'] == job_order]
            
            if len(job_data) > 0:
                suffix = str(job_data.iloc[0]['suffix'])
            
            print(f"FALSE TEST - Suffix: {suffix}")
            # Quantity is hardcoded as "FT 468" on frontend
            return jsonify({"success": True, "quantity": 468, "suffix": suffix})
        except Exception as e:
            print(f"Error reading FALSE TEST CSV: {e}")
            return jsonify({"success": True, "quantity": 468, "suffix": "0"})
    else:
        # TORITANI SAN DATABASE - use SQL (retry up to 3 times on failure)
        last_error = None
        for attempt in range(3):
            try:
                tori_qty, tori_suffix = torisql.getJobOrderTotalQuantity(job_order_raw)
                print(f"Torio Qty: {tori_qty}, Torio Suffix: {tori_suffix}")
                
                # Ensure suffix is never empty - extract from raw barcode if needed
                if not tori_suffix or tori_suffix.strip() == '':
                    # Try to extract suffix from raw barcode
                    # Format: job_order(10) + padding/data + suffix + trailing(2)
                    raw = str(job_order_raw).strip()
                    if len(raw) > 12:
                        # Remove last 2 chars, then take from position 13
                        extracted = raw[:-2][13:]
                        if extracted.strip():
                            tori_suffix = extracted.strip()
                            print(f"Suffix extracted from barcode: {tori_suffix}")
                    # If still empty, try position 10 to -2 and strip
                    if not tori_suffix or tori_suffix.strip() == '':
                        if len(raw) > 12:
                            middle = raw[10:-2].strip()
                            if middle:
                                tori_suffix = middle.lstrip('0') or '0'
                                print(f"Suffix extracted from middle: {tori_suffix}")
                
                return jsonify({"success": True, "quantity": int(tori_qty), "suffix": tori_suffix})
            except Exception as e:
                last_error = e
                print(f"getQuantityAndSuffix attempt {attempt+1} failed: {e}")
                try:
                    torisql.connect()
                except:
                    pass
        print(f"getQuantityAndSuffix all retries failed: {last_error}")
        return jsonify({"success": False, "error": str(last_error)}), 500

#Get Tori Sql
@app.route("/getToriSql")
def get_tori_sql():
    job_order = request.args.get('job_order', '')
    db_type = request.args.get('db_type', 'toritani')

    # return job_order
    
    print(f"Job Order: {job_order}, DB TYPE: {db_type}")

    

    # Truncate to 10 characters
    job_order = job_order[:10] if job_order else ''
    
    if not job_order:
        return jsonify({"success": False, "error": "No job order provided"})
    
    # Get the REF KITTING MTLS format setting
    settings = load_settings_file()
    ref_kitting_format = settings.get('ref_kitting_format', 'text')  # 'text' or 'text_and_num'
    print(f"REF KITTING MTLS format: {ref_kitting_format}")
    
    try:
        # Get dataframe based on database type
        if db_type == 'falsetest':
            # FALSE TEST database - read from CSV
            print(f"Reading from FALSE TEST CSV for job order: {job_order}")
            df_full = pd.read_csv(FALSE_TEST_CSV_PATH)
            df = df_full[df_full['job'] == job_order]
            print(f"FALSE TEST Dataframe shape: {df.shape if df is not None else 'None'}")
        else:
            # TORITANI SAN DATABASE - use SQL
            # Connect if not already connected or connection is closed
            if torisql.cursor is None or torisql.conn is None:
                print("Connecting to Tori SQL...")
                torisql.connect()
            
            # Get the dataframe with materials
            print(f"Fetching materials for job order: {job_order}")
            df = torisql.getJobOrderMaterials(job_order)
            print(f"Dataframe shape: {df.shape if df is not None else 'None'}")
        
        # Get the item (4th column - index 3) from the first row if available
        item = None
        matched_materials = {}  # {row_no: MaterialDescription}
        
        if df is not None and len(df) > 0:
            columns = df.columns.tolist()
            print(f"Columns: {columns}")
            
            if len(columns) >= 4:
                # Get the 4th column name (item) and its value from first row
                fourth_column_name = columns[3]
                item = str(df.iloc[0][fourth_column_name]) if df.iloc[0][fourth_column_name] is not None else None
                print(f"4th column ({fourth_column_name}): {item}")
            
            # Find MaterialDescription and Material (material code) columns
            material_desc_col = None
            material_code_col = None
            matl_qty_col = None
            
            # Get Material code from 8th column (index 7) - this is the column with codes like FMB3270905
            if len(columns) >= 8:
                material_code_col = columns[7]
                print(f"Material Code column (8th): {material_code_col}")
            
            for col in columns:
                col_lower = col.lower()
                # Find MaterialDescription column
                if 'materialdescription' in col_lower:
                    material_desc_col = col
            
            # Get matl_qty from 10th column (index 9)
            if len(columns) >= 10:
                matl_qty_col = columns[9]
                print(f"matl_qty column (10th): {matl_qty_col}")
            
            print(f"MaterialDescription column: {material_desc_col}, Material Code column: {material_code_col}, matl_qty column: {matl_qty_col}")
            
            if material_desc_col:
                print(f"Found MaterialDescription column: {material_desc_col}")
                
                # First pass: collect all potential matches for each row in dataframe
                # Then assign the best match to each kitting category
                df_matches = []  # List of (mat_desc, mat_code, matched_categories)
                
                for idx, row in df.iterrows():
                    mat_desc = str(row[material_desc_col]) if row[material_desc_col] is not None else ''
                    mat_desc_upper = mat_desc.upper()
                    
                    # Get the material code for this row
                    mat_code = ''
                    if material_code_col:
                        mat_code = str(row[material_code_col]) if row[material_code_col] is not None else ''
                    
                    # Get matl_qty (10th column) for this row - convert to whole number
                    matl_qty = ''
                    if matl_qty_col:
                        qty_val = row[matl_qty_col]
                        if qty_val is not None:
                            try:
                                # Convert to integer (whole number, no decimals)
                                matl_qty = str(int(float(qty_val)))
                            except (ValueError, TypeError):
                                matl_qty = str(qty_val)
                    
                    # Find all matching categories for this description
                    matches = []
                    for row_no, category in KITTING_MATERIAL_CATEGORIES.items():
                        category_upper = category.upper()
                        if category_upper in mat_desc_upper:
                            # Calculate match quality - prioritize position first, then length
                            pos = mat_desc_upper.find(category_upper)
                            # Position is most important (earlier = better), then keyword length
                            # Use negative position * 100 to heavily weight earlier matches
                            score = (100 - pos) * 100 + len(category_upper)
                            matches.append((row_no, category, score))
                    
                    if matches:
                        # Sort by score (higher is better) and take the best match
                        matches.sort(key=lambda x: x[2], reverse=True)
                        best_match = matches[0]
                        row_no = best_match[0]
                        category = best_match[1]
                        
                        # Only assign if not already assigned
                        if row_no not in matched_materials:
                            # Determine kitting_name based on format setting
                            if ref_kitting_format == 'text_and_num':
                                # Use material code (e.g., FMB3270905)
                                kitting_name = category  # Will be overwritten below
                            # Load kitting_name from kitting_materials.json
                            if os.path.exists(KITTING_MATERIALS_FILE):
                                try:
                                    with open(KITTING_MATERIALS_FILE, 'r') as f:
                                        saved_materials = json.load(f)
                                        if str(row_no) in saved_materials:
                                            kitting_name = saved_materials[str(row_no)]
                                except:
                                    pass
                            else:
                                # Use category text (e.g., FRAME ZAM)
                                kitting_name = category
                            
                            matched_materials[row_no] = {
                                'description': mat_desc,
                                'code': mat_code,
                                'qty': matl_qty,
                                'kitting_name': kitting_name
                            }
                            print(f"Row {row_no} ({category}): {mat_desc} | Code: {mat_code} | Qty: {matl_qty} | Kitting: {kitting_name}")
            else:
                print("MaterialDescription column not found in dataframe")
        
        return jsonify({
            "success": True, 
            "job_order": job_order,
            "item": item,
            "materials": matched_materials,
            "message": "Data fetched successfully"
        })
    except Exception as e:
        print(f"Error in getToriSql: {e}")
        return jsonify({"success": False, "error": str(e)})

# Block local database when cursor enters Job Order field
@app.route("/blockLocalDb")
def block_local_db():
    torisql.setToriMode(True)
    return "Local DB blocked"

# Unblock local database (called after JO scan completes)
@app.route("/unblockLocalDb")
def unblock_local_db():
    torisql.setToriMode(False)
    return "Local DB unblocked"

# Save material setter data to MySQL
@app.route("/api/submit_material_data", methods=["POST"])
def submit_material_data():
    """Save material setter data to MATERIAL_SETTER table in MySQL"""
    try:
        data = request.json
        job_order = data.get('job_order', '')
        model_code = data.get('model_code', '')
        materials = data.get('materials', [])
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        if not materials:
            return jsonify({"success": False, "error": "No materials to save"}), 400
        
        # Save to MySQL
        result = db_manager.insert_material_setter(job_order, model_code, materials)
        
        if result:
            return jsonify({"success": True, "message": f"Saved {len(materials)} materials for job order {job_order}"})
        else:
            return jsonify({"success": False, "error": "Failed to save to database"}), 500
            
    except Exception as e:
        print(f"Error saving material setter: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ==================== MAIN_DB AND KITTING_DB API ====================
@app.route("/api/clear_main_db", methods=["POST"])
def clear_main_db():
    """Clear all MAIN_DB records for a job order"""
    try:
        data = request.json
        job_order = data.get('job_order', '')
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        result = db_manager.clear_main_db_for_job_order(job_order)
        
        if result:
            return jsonify({"success": True, "message": f"Cleared MAIN_DB for job order {job_order}"})
        else:
            return jsonify({"success": False, "error": "Failed to clear MAIN_DB"}), 500
            
    except Exception as e:
        print(f"Error clearing MAIN_DB: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_main_db", methods=["POST"])
def save_main_db():
    """Save materials to MAIN_DB table"""
    try:
        data = request.json
        job_order = data.get('job_order', '')
        model_code = data.get('model_code', '')
        materials = data.get('materials', [])
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        result = db_manager.save_to_main_db(job_order, model_code, materials)
        
        if result:
            return jsonify({"success": True, "message": f"Saved to MAIN_DB for job order {job_order}"})
        else:
            return jsonify({"success": False, "error": "Failed to save to MAIN_DB"}), 500
            
    except Exception as e:
        print(f"Error saving to MAIN_DB: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_main_db", methods=["GET"])
def get_main_db():
    """Get materials from MAIN_DB for a job order"""
    try:
        job_order = request.args.get('job_order', '')
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        data = db_manager.get_main_db_data(job_order)
        return jsonify({"success": True, "data": data})
            
    except Exception as e:
        print(f"Error getting MAIN_DB data: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_all_main_db", methods=["GET"])
def get_all_main_db():
    """Get all materials from MAIN_DB (for Total Quantity Monitor auto-refresh)"""
    try:
        data = db_manager.get_all_main_db_data()
        return jsonify({"success": True, "data": data})
            
    except Exception as e:
        print(f"Error getting all MAIN_DB data: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/complete_kitting", methods=["POST"])
def complete_kitting():
    """Complete a kitting - save to KITTING_DB, material-specific tables, and update MAIN_DB remaining qty"""
    try:
        data = request.json
        job_order = data.get('job_order', '')
        model_code = data.get('model_code', '')
        materials = data.get('materials', [])
        # IMAGE 7: per-lot breakdown for problematic rows -> { "<row_no>": [ {scan_material, lot_no, qty_kit}, ... ] }
        material_lots = data.get('material_lots', {})
        kitting_qr_code = data.get('kitting_qr_code', '')  # QR code data (DD/MM/YY-KITTING_NO JOB_ORDER)
        suffix = data.get('suffix', '0001')  # Suffix in 4 digits
        plan_qty = data.get('plan_qty', 0)  # Plan quantity for joborder_plan
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        if not materials:
            return jsonify({"success": False, "error": "No materials to save"}), 400
        
        # Get next kitting number
        kitting_no = db_manager.get_next_kitting_no(job_order)
        
        # Save to KITTING_DB with QR code data
        result = db_manager.save_to_kitting_db(kitting_no, job_order, model_code, materials, kitting_qr_code)
        
        if result:
            # Save each row to its designated material-specific table (1tbl_frame_zam, 2tbl_frame_lead, etc.)
            # IMAGE 7: pass material_lots so problematic rows store one table row PER scanned lot.
            db_manager.save_to_material_tables(kitting_no, job_order, model_code, materials, kitting_qr_code, material_lots)
            
            # Save to joborder_plan table - track kitting progress with incrementing result and decrementing balance
            # Format kitting_qr_code: remove slash from date (DD/MM/YY -> DDMMYY)
            formatted_qr_code = kitting_qr_code.replace('/', '') if kitting_qr_code else ''
            if plan_qty and int(plan_qty) > 0:
                db_manager.save_joborder_plan(job_order, suffix, model_code, formatted_qr_code, plan_qty)
            
            return jsonify({
                "success": True, 
                "kitting_no": kitting_no,
                "kitting_qr_code": kitting_qr_code,
                "message": f"Kitting {kitting_qr_code} completed successfully"
            })
        else:
            return jsonify({"success": False, "error": "Failed to save kitting"}), 500
            
    except Exception as e:
        print(f"Error completing kitting: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_kitting_db", methods=["GET"])
def get_kitting_db():
    """Get all kitting records from KITTING_DB for a job order"""
    try:
        job_order = request.args.get('job_order', '')
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        data = db_manager.get_kitting_db_data(job_order, today_only=True)
        return jsonify({"success": True, "data": data})
            
    except Exception as e:
        print(f"Error getting KITTING_DB data: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_kitting_summary", methods=["POST"])
def save_kitting_summary():
    """Save kitting summary data to kitting_summary table (mirrors browser display)"""
    try:
        data = request.json
        job_order = data.get('job_order', '')
        model_code = data.get('model_code', '')
        rows = data.get('rows', [])
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        if not rows:
            return jsonify({"success": False, "error": "No rows to save"}), 400
        
        result = db_manager.save_kitting_summary(job_order, model_code, rows)
        
        if result:
            return jsonify({"success": True, "message": f"Saved kitting summary for job order {job_order}"})
        else:
            return jsonify({"success": False, "error": "Failed to save kitting summary"}), 500
            
    except Exception as e:
        print(f"Error saving kitting summary: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/clear_kitting_summary", methods=["POST"])
def clear_kitting_summary():
    """Clear kitting summary data for a job order"""
    try:
        data = request.json
        job_order = data.get('job_order', '')
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        result = db_manager.clear_kitting_summary(job_order)
        
        if result:
            return jsonify({"success": True, "message": f"Cleared kitting summary for job order {job_order}"})
        else:
            return jsonify({"success": False, "error": "Failed to clear kitting summary"}), 500
            
    except Exception as e:
        print(f"Error clearing kitting summary: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_all_kitting_summary", methods=["GET"])
def get_all_kitting_summary():
    """Get all kitting summary data (no filter)"""
    try:
        data = db_manager.get_all_kitting_summary()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        print(f"Error getting all kitting summary: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/reset_kitting_summary_ids", methods=["POST"])
def reset_kitting_summary_ids():
    """Reset kitting_summary table IDs to be sequential (fixes gaps in AUTO_INCREMENT)"""
    try:
        result = db_manager.reset_kitting_summary_ids()
        
        if result:
            return jsonify({"success": True, "message": "Kitting summary IDs have been reset to sequential order"})
        else:
            return jsonify({"success": False, "error": "Failed to reset kitting summary IDs"}), 500
            
    except Exception as e:
        print(f"Error resetting kitting summary IDs: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
@app.route("/api/get_kitting_summary", methods=["GET"])
def get_kitting_summary():
    """Get kitting summary data from kitting_summary table"""
    try:
        job_order = request.args.get('job_order', '')
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        data = db_manager.get_kitting_summary(job_order)
        return jsonify({"success": True, "data": data})
            
    except Exception as e:
        print(f"Error getting kitting summary: {e}")
        return jsonify({"success": False, "error": str(e)}), 500




@app.route("/api/get_next_kitting_no", methods=["GET"])
def get_next_kitting_no():
    """Get the next kitting number for a job order"""
    try:
        job_order = request.args.get('job_order', '')
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        kitting_no = db_manager.get_next_kitting_no(job_order)
        return jsonify({"success": True, "kitting_no": kitting_no})
            
    except Exception as e:
        print(f"Error getting next kitting number: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/fix_main_db", methods=["POST"])
def fix_main_db():
    """Fix existing MAIN_DB data: set lot_qty from material data"""
    try:
        job_order = request.args.get('job_order', '')
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        affected_rows = db_manager.fix_main_db_lot_qty(job_order)
        return jsonify({"success": True, "message": f"Fixed {affected_rows} rows in MAIN_DB"})
            
    except Exception as e:
        print(f"Error fixing MAIN_DB: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ==================== JOBORDER_PLAN API ====================
@app.route("/api/save_joborder_plan", methods=["POST"])
def save_joborder_plan():
    """Save a new joborder_plan record when kitting QR code is scanned"""
    try:
        data = request.json
        job_order = data.get('job_order', '')
        suffix = data.get('suffix', '0001')
        model_code = data.get('model_code', '')
        kitting_qr_code = data.get('kitting_qr_code', '')
        plan_qty = data.get('plan_qty', 0)
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        if not kitting_qr_code:
            return jsonify({"success": False, "error": "Kitting QR code is required"}), 400
        
        result = db_manager.save_joborder_plan(job_order, suffix, model_code, kitting_qr_code, plan_qty)
        
        if result.get('success'):
            return jsonify({
                "success": True, 
                "row_no": result['row_no'],
                "result": result['result'],
                "balance": result['balance'],
                "message": f"Saved joborder_plan for job order {job_order}"
            })
        else:
            return jsonify({"success": False, "error": result.get('error', 'Unknown error')}), 500
            
    except Exception as e:
        print(f"Error saving joborder_plan: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_joborder_plan", methods=["GET"])
def get_joborder_plan():
    """Get all joborder_plan records for a job order"""
    try:
        job_order = request.args.get('job_order', '')
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        data = db_manager.get_joborder_plan(job_order)
        return jsonify({"success": True, "data": data})
            
    except Exception as e:
        print(f"Error getting joborder_plan: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_joborder_plan_latest", methods=["GET"])
def get_joborder_plan_latest():
    """Get the latest joborder_plan record for a job order"""
    try:
        job_order = request.args.get('job_order', '')
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        data = db_manager.get_joborder_plan_latest(job_order)
        return jsonify({"success": True, "data": data})
            
    except Exception as e:
        print(f"Error getting latest joborder_plan: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/clear_joborder_plan", methods=["POST"])
def clear_joborder_plan():
    """Clear all joborder_plan records for a job order"""
    try:
        data = request.json
        job_order = data.get('job_order', '')
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        result = db_manager.clear_joborder_plan(job_order)
        
        if result:
            return jsonify({"success": True, "message": f"Cleared joborder_plan for job order {job_order}"})
        else:
            return jsonify({"success": False, "error": "Failed to clear joborder_plan"}), 500
            
    except Exception as e:
        print(f"Error clearing joborder_plan: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ==================== MATERIAL SETTER SETTINGS API ====================
# File to persist material setter settings
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'material_setter_settings.json')
MODEL_CODES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model_codes_no_bushing.json')
KITTING_MATERIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kitting_materials.json')

def load_settings_file():
    """Load settings from file"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading settings: {e}")
    return {}

def save_settings_file(settings):
    """Save settings to file"""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

def load_model_codes_file():
    """Load model codes without bushing from file"""
    try:
        if os.path.exists(MODEL_CODES_FILE):
            with open(MODEL_CODES_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading model codes: {e}")
    return ['80HP40073P', '80HP40701P', '80HP40750P', '60HP40004P', '60HP40701P']  # Default models WITH Filter Bushing (26 rows)

def save_model_codes_file(codes):
    """Save model codes without bushing to file"""
    try:
        with open(MODEL_CODES_FILE, 'w') as f:
            json.dump(codes, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving model codes: {e}")
        return False

@app.route("/api/get_settings", methods=["GET"])
def get_settings():
    """Get all material setter settings"""
    try:
        settings = load_settings_file()
        return jsonify({"success": True, "settings": settings})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_jo_database", methods=["POST"])
def save_jo_database():
    """Save JO Database location settings"""
    try:
        data = request.json
        db_type = data.get('type')
        path = data.get('path')
        
        settings = load_settings_file()
        settings['jo_database'] = {'type': db_type, 'path': path}
        
        if save_settings_file(settings):
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to save settings"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_materials_path", methods=["POST"])
def save_materials_path():
    """Save Materials file location"""
    try:
        data = request.json
        path = data.get('path')
        
        settings = load_settings_file()
        settings['materials_path'] = path
        
        if save_settings_file(settings):
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to save settings"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_latency", methods=["POST"])
def save_latency():
    """Save Arduino polling latency setting"""
    try:
        data = request.json
        latency = data.get('latency', 100)
        
        settings = load_settings_file()
        settings['latency'] = latency
        
        if save_settings_file(settings):
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to save settings"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_elapsed_time_settings", methods=["POST"])
def save_elapsed_time_settings():
    """Save elapsed time display settings (millisecond, blinking)"""
    try:
        data = request.json
        millisecond = data.get('millisecond', False)
        blinking = data.get('blinking', False)
        
        settings = load_settings_file()
        settings['elapsed_time'] = {
            'millisecond': millisecond,
            'blinking': blinking
        }
        
        if save_settings_file(settings):
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to save settings"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_qr_hide_setting", methods=["POST"])
def save_qr_hide_setting():
    """Save QR code hide/unhide setting (persists forever until changed)"""
    try:
        data = request.json
        qr_code_hidden = data.get('qr_code_hidden', False)
        
        settings = load_settings_file()
        settings['qr_code_hidden'] = qr_code_hidden
        
        if save_settings_file(settings):
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to save settings"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_elapsed_time_settings", methods=["GET"])
def get_elapsed_time_settings():
    """Get elapsed time display settings"""
    try:
        settings = load_settings_file()
        elapsed_time = settings.get('elapsed_time', {'millisecond': False, 'blinking': False})
        return jsonify({"success": True, "elapsed_time": elapsed_time})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_page_title", methods=["POST"])
def save_page_title():
    """Save page title"""
    try:
        data = request.json
        title = data.get('title', '')
        settings = load_settings_file()
        settings['page_title'] = title
        if save_settings_file(settings):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Failed to save"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_page_title", methods=["GET"])
def get_page_title():
    """Get page title"""
    try:
        settings = load_settings_file()
        title = settings.get('page_title', 'Job Order and Material Data')
        return jsonify({"success": True, "title": title})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_sub_columns", methods=["POST"])
def save_sub_columns():
    """Save sub column labels"""
    try:
        data = request.json
        sub_columns = data.get('sub_columns', [])
        settings = load_settings_file()
        settings['sub_columns'] = sub_columns
        if save_settings_file(settings):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Failed to save"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_sub_columns", methods=["GET"])
def get_sub_columns():
    """Get sub column labels"""
    try:
        settings = load_settings_file()
        sub_columns = settings.get('sub_columns', ['Job Order #:', 'Model Code:', 'Quantity:'])
        return jsonify({"success": True, "sub_columns": sub_columns})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_column_headers", methods=["POST"])
def save_column_headers():
    """Save column header labels and lengths"""
    try:
        data = request.json
        column_headers = data.get('column_headers', [])
        column_lengths = data.get('column_lengths', [])
        settings = load_settings_file()
        settings['column_headers'] = column_headers
        settings['column_lengths'] = column_lengths
        if save_settings_file(settings):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Failed to save"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_column_headers", methods=["GET"])
def get_column_headers():
    """Get column header labels and lengths"""
    try:
        settings = load_settings_file()
        column_headers = settings.get('column_headers', ['KITTING MTLS', 'MTRL DESC', 'MATERIAL CODE', 'QTY', 'SCAN MATERIAL', 'LOT NO', 'QTY', 'GOOD'])
        column_lengths = settings.get('column_lengths', [])
        return jsonify({"success": True, "column_headers": column_headers, "column_lengths": column_lengths})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_action_buttons", methods=["POST"])
def save_action_buttons():
    """Save action button labels"""
    try:
        data = request.json
        action_buttons = data.get('action_buttons', [])
        settings = load_settings_file()
        settings['action_buttons'] = action_buttons
        if save_settings_file(settings):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Failed to save"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_action_buttons", methods=["GET"])
def get_action_buttons():
    """Get action button labels"""
    try:
        settings = load_settings_file()
        action_buttons = settings.get('action_buttons', ['Delete', 'Main Menu', 'Submit'])
        return jsonify({"success": True, "action_buttons": action_buttons})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_ref_kitting_format", methods=["POST"])
def save_ref_kitting_format():
    """Save REF KITTING MTLS format setting (text or text_and_num)"""
    try:
        data = request.json
        format_type = data.get('format', 'text')
        settings = load_settings_file()
        settings['ref_kitting_format'] = format_type
        if save_settings_file(settings):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Failed to save"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_ref_kitting_format", methods=["GET"])
def get_ref_kitting_format():
    """Get REF KITTING MTLS format setting"""
    try:
        settings = load_settings_file()
        format_type = settings.get('ref_kitting_format', 'text')
        return jsonify({"success": True, "format": format_type})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_row_count", methods=["POST"])
def save_row_count():
    """Save row count setting"""
    try:
        data = request.json
        row_count = data.get('row_count', 25)
        settings = load_settings_file()
        settings['row_count'] = row_count
        if save_settings_file(settings):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Failed to save"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_row_count", methods=["GET"])
def get_row_count():
    """Get row count setting"""
    try:
        settings = load_settings_file()
        row_count = settings.get('row_count', 25)
        return jsonify({"success": True, "row_count": row_count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_model_codes", methods=["GET"])
def get_model_codes():
    """Get model codes without bushing (23 rows)"""
    try:
        codes = load_model_codes_file()
        return jsonify({"success": True, "model_codes": codes})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/add_model_code", methods=["POST"])
def add_model_code():
    """Add a model code without bushing"""
    try:
        data = request.json
        code = data.get('model_code', '').strip().upper()
        
        if not code:
            return jsonify({"success": False, "error": "Model code is required"}), 400
        
        codes = load_model_codes_file()
        if code not in codes:
            codes.append(code)
            save_model_codes_file(codes)
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/delete_model_code", methods=["POST"])
def delete_model_code():
    """Delete a model code without bushing"""
    try:
        data = request.json
        code = data.get('model_code', '').strip().upper()
        
        codes = load_model_codes_file()
        if code in codes:
            codes.remove(code)
            save_model_codes_file(codes)
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_all_model_codes", methods=["GET"])
def get_all_model_codes():
    """Get all available model codes (from materials file or sample data)"""
    try:
        # Sample model codes - in production, load from materials file
        model_codes = [
            '60CAT0211P', '60CAT0212P', '60CAT0213P', '60CAT0214P', '60CAT0215P',
            '60CAT0216P', '60CAT0217P', '60CAT0218P', '60CAT0219P', '60CAT0220P',
            '80CAT0301P', '80CAT0302P', '80CAT0303P', '80CAT0304P', '80CAT0305P',
            '80CAT0306P', '80CAT0307P', '80CAT0308P', '80CAT0309P', '80CAT0310P'
        ]
        return jsonify({"success": True, "model_codes": model_codes})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_kitting_materials", methods=["GET"])
def get_kitting_materials():
    """Get kitting material names"""
    try:
        if os.path.exists(KITTING_MATERIALS_FILE):
            with open(KITTING_MATERIALS_FILE, 'r') as f:
                kitting_materials = json.load(f)
            return jsonify({"success": True, "kitting_materials": kitting_materials})
        else:
            return jsonify({"success": False, "message": "Using defaults"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_kitting_materials", methods=["POST"])
def save_kitting_materials():
    """Save kitting material names"""
    try:
        data = request.json
        kitting_materials = data.get('kitting_materials', {})
        
        with open(KITTING_MATERIALS_FILE, 'w') as f:
            json.dump(kitting_materials, f, indent=2)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_generate_csv", methods=["POST"])
def save_generate_csv():
    """Save CSV generation setting and generate CSV if enabled"""
    try:
        data = request.json
        generate_csv = data.get('generate_csv', False)
        
        settings = load_settings_file()
        settings['generate_csv'] = generate_csv
        
        if save_settings_file(settings):
            # If enabled, generate CSV from torisql dataframe
            if generate_csv:
                try:
                    # Get CSV export options from settings
                    csv_options = settings.get('csv_export_options', {})
                    
                    if torisql.cursor is None or torisql.conn is None:
                        torisql.connect()
                    
                    # Get default job order or use the one from settings
                    job_order = csv_options.get('default_job_order', '3J73802302')
                    
                    # Get DataFrame using existing function
                    df = torisql.getJobOrderMaterials(job_order)
                    
                    if df is not None and len(df) > 0:
                        # Use enhanced export function
                        export_options = {
                            'job_order': job_order,
                            'include_metadata': csv_options.get('include_metadata', True),
                            'replace_nulls': csv_options.get('replace_nulls', True),
                            'trim_strings': csv_options.get('trim_strings', True),
                            'format_dates': csv_options.get('format_dates', True),
                            'encoding': csv_options.get('encoding', 'utf-8-sig')
                        }
                        
                        result = torisql.export_to_csv(df, options=export_options)
                        
                        if result['success']:
                            print(f"CSV generated: {result['file_path']} with {result['record_count']} rows")
                            # Save last export info
                            settings['last_csv_export'] = {
                                'filename': result['filename'],
                                'timestamp': result['export_time'],
                                'record_count': result['record_count']
                            }
                            save_settings_file(settings)
                        else:
                            print(f"CSV export failed: {result.get('error', 'Unknown error')}")
                    else:
                        print("No data returned from query")
                except Exception as csv_error:
                    print(f"Error generating CSV: {csv_error}")
                    import traceback
                    traceback.print_exc()
            
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to save settings"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/save_csv_export_options", methods=["POST"])
def save_csv_export_options():
    """Save CSV export options"""
    try:
        data = request.json
        
        settings = load_settings_file()
        settings['csv_export_options'] = {
            'default_job_order': data.get('default_job_order', '3J73802302'),
            'include_metadata': data.get('include_metadata', True),
            'replace_nulls': data.get('replace_nulls', True),
            'trim_strings': data.get('trim_strings', True),
            'format_dates': data.get('format_dates', True),
            'encoding': data.get('encoding', 'utf-8-sig')
        }
        
        if save_settings_file(settings):
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to save settings"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/export_csv_now", methods=["POST"])
def export_csv_now():
    """Export CSV immediately with current settings"""
    try:
        data = request.json
        job_order = data.get('job_order')
        
        if not job_order:
            return jsonify({"success": False, "error": "Job order is required"}), 400
        
        if torisql.cursor is None or torisql.conn is None:
            torisql.connect()
        
        df = torisql.getJobOrderMaterials(job_order)
        
        if df is None or len(df) == 0:
            return jsonify({"success": False, "error": "No data found for job order"}), 404
        
        settings = load_settings_file()
        csv_options = settings.get('csv_export_options', {})
        
        export_options = {
            'job_order': job_order,
            'include_metadata': csv_options.get('include_metadata', True),
            'replace_nulls': csv_options.get('replace_nulls', True),
            'trim_strings': csv_options.get('trim_strings', True),
            'format_dates': csv_options.get('format_dates', True),
            'encoding': csv_options.get('encoding', 'utf-8-sig')
        }
        
        result = torisql.export_to_csv(df, options=export_options)
        
        if result['success']:
            settings['last_csv_export'] = {
                'filename': result['filename'],
                'timestamp': result['export_time'],
                'record_count': result['record_count'],
                'job_order': job_order
            }
            save_settings_file(settings)
            
            return jsonify({
                "success": True,
                "filename": result['filename'],
                "record_count": result['record_count'],
                "message": "CSV exported successfully"
            })
        else:
            return jsonify({"success": False, "error": result.get('error', 'Export failed')}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/force_daily_reset", methods=["POST"])
def force_daily_reset():
    """Force a full daily reset - clears kitting, manpower, and graph data"""
    try:
        print("FORCE DAILY RESET: Manually triggered")
        
        # Reset all server state
        with server_timers_lock:
            server_timers.clear()
        with server_counters_lock:
            server_counters.clear()
        with arduino_signals_lock:
            arduino_signals.clear()
        with server_blocked_counters_lock:
            server_blocked_counters.clear()
        with server_active_kittings_lock:
            server_active_kittings.clear()
        
        # Delete timer state file
        try:
            if os.path.exists(TIMER_STATE_FILE):
                os.remove(TIMER_STATE_FILE)
        except:
            pass
        save_timer_state_to_file()
        
        # Reset database: counters, manpower, and records
        result = db_manager.reset_all_for_new_day()
        
        # Update last active date
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        with last_active_date_lock:
            last_active_date["date"] = today
        save_last_active_date(today)
        
        update_last_data_timestamp()
        
        print(f"FORCE DAILY RESET: Completed, database result: {result}")
        return jsonify({"success": True, "message": "Full daily reset completed", "db_result": result})
    except Exception as e:
        print(f"Error in force_daily_reset: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# API Routes for data insertion
@app.route("/api/start_process", methods=["POST"])
def start_process():
    """Handle START button click - no database insertion, just acknowledge"""
    try:
        data = request.json
        kitting_no = data.get('kitting_no', '')
        process_no = data.get('process_no', 1)
        
        print(f"START: kitting_no={kitting_no}, process_no={process_no}")
        
        # Don't insert record here - only insert on STOP/NG/LINEOUT
        # This prevents duplicate records for the same process
        
        return jsonify({"success": True, "message": "Process started successfully"})
    except Exception as e:
        print(f"Error in start_process: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/stop_process", methods=["POST"])
def stop_process():
    """Handle STOP button click - update elapsed time"""
    try:
        # Check if request has JSON data
        if not request.is_json:
            print("ERROR: Request is not JSON")
            return jsonify({"success": False, "error": "Request must be JSON"}), 400
            
        data = request.get_json()
        if not data:
            print("ERROR: No JSON data received")
            return jsonify({"success": False, "error": "No data received"}), 400
            
        print(f"Received data: {data}")
        
        kitting_no = data.get('kitting_no', '')
        elapsed_time = data.get('elapsed_time', '00:00')
        process_no = data.get('process_no', 1)
        
        print(f"STOP: kitting_no={kitting_no}, elapsed_time={elapsed_time}, process_no={process_no}, pass_ng=1")
        
        # SERVER-SIDE VALIDATION: Block if upstream process hasn't completed this kitting
        process_no_int = int(process_no) if process_no else 1
        if process_no_int > 1 and kitting_no:
            prev_completed = db_manager.get_completed_count(process_no_int - 1)
            kitting_no_int = int(kitting_no) if str(kitting_no).isdigit() else 0
            if kitting_no_int > prev_completed:
                print(f"STOP BLOCKED: Process {process_no_int} Kitting {kitting_no_int} - Process {process_no_int-1} only completed {prev_completed}")
                return jsonify({"success": False, "error": f"Process {process_no_int-1} has only completed {prev_completed} kittings"})
        
        # Validate elapsed_time format
        if elapsed_time and ':' not in str(elapsed_time):
            print(f"WARNING: Invalid elapsed_time format: {elapsed_time}")
            elapsed_time = '00:00'
        
        # Insert record with elapsed time and pass_ng=1 (PASS)
        record_id = db_manager.insert_record(
            kitting_no=str(kitting_no) if kitting_no else '',
            lineout_reason=None,
            elapsed_time=str(elapsed_time),
            pass_ng=1,
            process_no=int(process_no) if process_no else 1
        )
        
        # Clear server-side timer for this process
        with server_timers_lock:
            server_timers.pop(int(process_no) if process_no else 1, None)
        
        # Update last data timestamp for auto-refresh
        update_last_data_timestamp()
        save_timer_state_to_file()
        
        # Check if all processes have same kitting (new job order complete - reset graph)
        check_all_processes_same_kitting()
        
        if record_id:
            return jsonify({"success": True, "record_id": record_id})
        else:
            return jsonify({"success": False, "error": "Failed to insert record"}), 500
    except Exception as e:
        print(f"Error in stop_process: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/ng_process", methods=["POST"])
def ng_process():
    """Handle NG button click"""
    try:
        # Check if request has JSON data
        if not request.is_json:
            print("ERROR: Request is not JSON")
            return jsonify({"success": False, "error": "Request must be JSON"}), 400
            
        data = request.get_json()
        if not data:
            print("ERROR: No JSON data received")
            return jsonify({"success": False, "error": "No data received"}), 400
            
        print(f"Received data: {data}")
        
        kitting_no = data.get('kitting_no', '')
        elapsed_time = data.get('elapsed_time', '00:00')
        process_no = data.get('process_no', 1)
        
        print(f"NG: kitting_no={kitting_no}, elapsed_time={elapsed_time}, process_no={process_no}, pass_ng=0")
        
        # SERVER-SIDE VALIDATION: Block if upstream process hasn't completed this kitting
        process_no_int = int(process_no) if process_no else 1
        if process_no_int > 1 and kitting_no:
            prev_completed = db_manager.get_completed_count(process_no_int - 1)
            kitting_no_int = int(kitting_no) if str(kitting_no).isdigit() else 0
            if kitting_no_int > prev_completed:
                print(f"NG BLOCKED: Process {process_no_int} Kitting {kitting_no_int} - Process {process_no_int-1} only completed {prev_completed}")
                return jsonify({"success": False, "error": f"Process {process_no_int-1} has only completed {prev_completed} kittings"})
        
        # Validate elapsed_time format
        if elapsed_time and ':' not in str(elapsed_time):
            print(f"WARNING: Invalid elapsed_time format: {elapsed_time}")
            elapsed_time = '00:00'
        
        # Insert record with pass_ng=0 (NG)
        record_id = db_manager.insert_record(
            kitting_no=str(kitting_no) if kitting_no else '',
            lineout_reason=None,
            elapsed_time=str(elapsed_time),
            pass_ng=0,
            process_no=int(process_no) if process_no else 1
        )
        
        # Clear server-side timer for this process
        with server_timers_lock:
            server_timers.pop(int(process_no) if process_no else 1, None)
        
        # Update last data timestamp for auto-refresh
        update_last_data_timestamp()
        save_timer_state_to_file()
        
        # Check if all processes have same kitting (new job order complete - reset graph)
        check_all_processes_same_kitting()
        
        if record_id:
            return jsonify({"success": True, "record_id": record_id})
        else:
            return jsonify({"success": False, "error": "Failed to insert record"}), 500
    except Exception as e:
        print(f"Error in ng_process: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/ng_lineout_process", methods=["POST"])
def ng_lineout_process():
    """Handle NG LINEOUT button click with reason"""
    try:
        data = request.json
        kitting_no = data.get('kitting_no', '')
        lineout_reason = data.get('lineout_reason', '')
        elapsed_time = data.get('elapsed_time', '00:00')
        process_no = data.get('process_no', 1)
        
        print(f"NG LINEOUT: kitting_no={kitting_no}, lineout_reason={lineout_reason}, elapsed_time={elapsed_time}, process_no={process_no}, pass_ng=0")
        
        # SERVER-SIDE VALIDATION: Block if upstream process hasn't completed this kitting
        process_no_int = int(process_no) if process_no else 1
        if process_no_int > 1 and kitting_no:
            prev_completed = db_manager.get_completed_count(process_no_int - 1)
            kitting_no_int = int(kitting_no) if str(kitting_no).isdigit() else 0
            if kitting_no_int > prev_completed:
                print(f"NG LINEOUT BLOCKED: Process {process_no_int} Kitting {kitting_no_int} - Process {process_no_int-1} only completed {prev_completed}")
                return jsonify({"success": False, "error": f"Process {process_no_int-1} has only completed {prev_completed} kittings"})
        
        # Insert record with lineout reason and pass_ng=0 (NG)
        record_id = db_manager.insert_record(
            kitting_no=kitting_no,
            lineout_reason=lineout_reason,
            elapsed_time=elapsed_time,
            pass_ng=0,
            process_no=process_no
        )
        
        # Clear server-side timer for this process
        with server_timers_lock:
            server_timers.pop(int(process_no) if process_no else 1, None)
        
        # Update last data timestamp for auto-refresh
        update_last_data_timestamp()
        save_timer_state_to_file()
        
        # Check if all processes have same kitting (new job order complete - reset graph)
        check_all_processes_same_kitting()
        
        if record_id:
            return jsonify({"success": True, "record_id": record_id})
        else:
            return jsonify({"success": False, "error": "Failed to insert record"}), 500
    except Exception as e:
        print(f"Error in ng_lineout_process: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/lineout_process", methods=["POST"])
def lineout_process():
    """Handle LINEOUT button click with reason"""
    try:
        data = request.json
        kitting_no = data.get('kitting_no', '')
        lineout_reason = data.get('lineout_reason', '')
        elapsed_time = data.get('elapsed_time', '00:00')
        process_no = data.get('process_no', 1)
        
        print(f"LINEOUT: kitting_no={kitting_no}, lineout_reason={lineout_reason}, elapsed_time={elapsed_time}, process_no={process_no}, pass_ng=0")
        
        # SERVER-SIDE VALIDATION: Block if upstream process hasn't completed this kitting
        process_no_int = int(process_no) if process_no else 1
        if process_no_int > 1 and kitting_no:
            prev_completed = db_manager.get_completed_count(process_no_int - 1)
            kitting_no_int = int(kitting_no) if str(kitting_no).isdigit() else 0
            if kitting_no_int > prev_completed:
                print(f"LINEOUT BLOCKED: Process {process_no_int} Kitting {kitting_no_int} - Process {process_no_int-1} only completed {prev_completed}")
                return jsonify({"success": False, "error": f"Process {process_no_int-1} has only completed {prev_completed} kittings"})
        
        # Insert record with lineout reason and pass_ng=0 (NG)
        record_id = db_manager.insert_record(
            kitting_no=kitting_no,
            lineout_reason=lineout_reason,
            elapsed_time=elapsed_time,
            pass_ng=0,
            process_no=process_no
        )
        
        # Clear server-side timer for this process
        with server_timers_lock:
            server_timers.pop(int(process_no) if process_no else 1, None)
        
        # Update last data timestamp for auto-refresh
        update_last_data_timestamp()
        save_timer_state_to_file()
        
        # Check if all processes have same kitting (new job order complete - reset graph)
        check_all_processes_same_kitting()
        
        if record_id:
            return jsonify({"success": True, "record_id": record_id})
        else:
            return jsonify({"success": False, "error": "Failed to insert record"}), 500
    except Exception as e:
        print(f"Error in lineout_process: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_process_records/<int:process_no>", methods=["GET"])
def get_process_records(process_no):
    """Get records for a specific process"""
    try:
        records = db_manager.get_records_by_process(process_no)
        return jsonify({"success": True, "records": records})
    except Exception as e:
        print(f"Error in get_process_records: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_standard_times", methods=["GET"])
def get_standard_times():
    """Get all standard times"""
    try:
        standard_times = db_manager.get_all_standard_times()
        # Convert Decimal to float for JSON serialization
        for st in standard_times:
            st['standard_time'] = float(st['standard_time'])
            st['title'] = st.get('title', '')
        return jsonify({"success": True, "standard_times": standard_times})
    except Exception as e:
        print(f"Error in get_standard_times: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_standard_time/<int:process_no>", methods=["GET"])
def get_standard_time(process_no):
    """Get standard time for a specific process"""
    try:
        standard_times = db_manager.get_all_standard_times()
        for st in standard_times:
            if st['process_no'] == process_no:
                return jsonify({"success": True, "standard_time": float(st['standard_time']), "title": st.get('title', '')})
        return jsonify({"success": False, "error": "Process not found"}), 404
    except Exception as e:
        print(f"Error in get_standard_time: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/update_standard_time", methods=["POST"])
def update_standard_time():
    """Update standard time for a process"""
    try:
        data = request.json
        process_no = data.get('process_no')
        standard_time = data.get('standard_time')
        title = data.get('title', None)
        
        if not process_no or not standard_time:
            return jsonify({"success": False, "error": "Missing process_no or standard_time"}), 400
        
        success = db_manager.update_standard_time(process_no, standard_time, title)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to update standard time"}), 500
    except Exception as e:
        print(f"Error in update_standard_time: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/add_process", methods=["POST"])
def add_process():
    """Add a new process"""
    try:
        data = request.json
        standard_time = data.get('standard_time', '50')
        
        new_process_no = db_manager.add_new_process(standard_time)
        if new_process_no:
            return jsonify({"success": True, "process_no": new_process_no})
        else:
            return jsonify({"success": False, "error": "Failed to add process"}), 500
    except Exception as e:
        print(f"Error in add_process: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/delete_process", methods=["POST"])
def delete_process():
    """Delete a process"""
    try:
        data = request.json
        process_no = data.get('process_no')
        
        if not process_no:
            return jsonify({"success": False, "error": "Missing process_no"}), 400
        
        # Don't allow deletion of processes 1-9 (default processes)
        if process_no <= 9:
            return jsonify({"success": False, "error": "Cannot delete default processes 1-9"}), 400
        
        success = db_manager.delete_process(process_no)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to delete process"}), 500
    except Exception as e:
        print(f"Error in delete_process: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/check_manpower_complete", methods=["GET"])
def check_manpower_complete():
    """Check which processes 1-9 have manpower assigned.
    Returns list of missing processes - frontend shows warning only on the specific process that's missing."""
    try:
        manpower = db_manager.get_all_manpower()
        missing = []
        for i in range(1, 10):
            found = False
            for mp in manpower:
                if mp['process_no'] == i:
                    # Check if operator_scan OR operator_manual is filled
                    has_scan = mp.get('operator_scan', '').strip() != ''
                    has_manual = mp.get('operator_manual', '').strip() != ''
                    if has_scan or has_manual:
                        found = True
                    break
            if not found:
                missing.append(i)
        
        is_complete = len(missing) == 0
        return jsonify({"success": True, "is_complete": is_complete, "missing_processes": missing})
    except Exception as e:
        print(f"Error in check_manpower_complete: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_manpower", methods=["GET"])
def get_manpower():
    """Get all manpower records"""
    try:
        manpower = db_manager.get_all_manpower()
        return jsonify({"success": True, "manpower": manpower})
    except Exception as e:
        print(f"Error in get_manpower: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_manpower/<int:process_no>", methods=["GET"])
def get_manpower_by_process(process_no):
    """Get manpower for a specific process"""
    try:
        manpower = db_manager.get_manpower_by_process(process_no)
        if manpower:
            return jsonify({"success": True, "manpower": manpower})
        return jsonify({"success": False, "error": "Process not found"}), 404
    except Exception as e:
        print(f"Error in get_manpower_by_process: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_cycle_graph_data", methods=["GET"])
def get_cycle_graph_data():
    """Get all data needed for cycle time graph monitoring"""
    try:
        # Get average elapsed times per process
        cycle_data = db_manager.get_cycle_graph_data()
        
        # Get all standard times
        standard_times = db_manager.get_all_standard_times()
        st_map = {}
        for st in standard_times:
            st_map[st['process_no']] = float(st['standard_time'])
        
        # Get all manpower (operator names)
        manpower = db_manager.get_all_manpower()
        operator_map = {}
        for mp in manpower:
            # Use operator_manual or operator_scan, whichever is set
            name = mp.get('operator_manual', '') or mp.get('operator_scan', '') or ''
            operator_map[mp['process_no']] = name
        
        # Build combined data for all 9 processes
        graph_data = []
        for i in range(1, 10):
            avg_mss = 0
            avg_seconds = 0
            record_count = 0
            for cd in cycle_data:
                if cd['process_no'] == i:
                    avg_mss = cd['avg_mss']
                    avg_seconds = cd['avg_seconds']
                    record_count = cd['record_count']
                    break
            
            graph_data.append({
                'process_no': i,
                'avg_mss': avg_mss,
                'avg_seconds': avg_seconds,
                'record_count': record_count,
                'standard_time': st_map.get(i, 1.50),
                'operator': operator_map.get(i, '')
            })
        
        return jsonify({"success": True, "graph_data": graph_data})
    except Exception as e:
        print(f"Error in get_cycle_graph_data: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_line_trend_data", methods=["GET"])
def get_line_trend_data():
    """Get all data needed for line trend graph monitoring"""
    try:
        # Get all standard times
        standard_times = db_manager.get_all_standard_times()
        st_map = {}
        for st in standard_times:
            st_map[st['process_no']] = float(st['standard_time'])
        
        # Get all manpower (operator names)
        manpower = db_manager.get_all_manpower()
        operator_map = {}
        for mp in manpower:
            name = mp.get('operator_manual', '') or mp.get('operator_scan', '') or ''
            operator_map[mp['process_no']] = name
        
        # Get job order start time for filtering (graph resets when all processes have same kitting)
        # Only use if it's a valid timestamp from today
        start_time = None
        with job_order_start_time_lock:
            saved_time = job_order_start_time.get("timestamp")
            if saved_time:
                from datetime import datetime
                try:
                    saved_dt = datetime.strptime(saved_time, "%Y-%m-%d %H:%M:%S")
                    today = datetime.now().date()
                    # Only use timestamp if it's from today (not stale/future)
                    if saved_dt.date() == today:
                        start_time = saved_time
                except:
                    pass
        
        # Build data for all 9 processes
        # Fixed values for all processes: TACT TIME = 1.50, (+) TOL = 1.65, (-) TOL = 1.35
        trend_data = []
        for i in range(1, 10):
            records = db_manager.get_line_trend_data(i, limit=10, after_timestamp=start_time)
            completed_count = db_manager.get_completed_count(i)
            trend_data.append({
                'process_no': i,
                'tol_plus': 1.65,
                'tol_minus': 1.35,
                'tact_time': 1.50,
                'operator': operator_map.get(i, ''),
                'records': records,
                'completed_count': completed_count
            })
        
        return jsonify({"success": True, "trend_data": trend_data})
    except Exception as e:
        print(f"Error in get_line_trend_data: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/update_manpower", methods=["POST"])
def update_manpower():
    """Update manpower for a process"""
    try:
        data = request.json
        process_no = data.get('process_no')
        operator_manual = data.get('operator_manual', '')
        operator_scan = data.get('operator_scan', '')
        
        if not process_no:
            return jsonify({"success": False, "error": "Missing process_no"}), 400
        
        success = db_manager.update_manpower(process_no, operator_manual, operator_scan)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to update manpower"}), 500
    except Exception as e:
        print(f"Error in update_manpower: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/operator_out", methods=["POST"])
def operator_out():
    """Clear operator for a process (operator OUT)"""
    try:
        data = request.json
        process_no = data.get('process_no')
        reason = data.get('reason', '')
        
        if not process_no:
            return jsonify({"success": False, "error": "Missing process_no"}), 400
        
        # Update the out_reasons column in the last record of the process table
        if reason:
            db_manager.update_out_reason(process_no, reason)
        
        # Update the time_out column in the last record of the process table
        db_manager.update_time_out(process_no)
        
        success = db_manager.clear_manpower(process_no)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to clear operator"}), 500
    except Exception as e:
        print(f"Error in operator_out: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_out_reasons", methods=["GET"])
def get_out_reasons():
    """Get all OUT reasons for dropdown"""
    try:
        reasons = db_manager.get_out_reasons()
        return jsonify({"success": True, "reasons": reasons})
    except Exception as e:
        print(f"Error in get_out_reasons: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/add_out_reason", methods=["POST"])
def add_out_reason():
    """Add a custom OUT reason (shared across all processes)"""
    try:
        data = request.json
        reason = data.get('reason', '').strip().upper()
        
        if not reason:
            return jsonify({"success": False, "error": "Missing reason"}), 400
        
        success = db_manager.add_out_reason(reason)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Reason already exists or failed to add"}), 500
    except Exception as e:
        print(f"Error in add_out_reason: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/delete_out_reason", methods=["POST"])
def delete_out_reason():
    """Delete an OUT reason (shared across all processes)"""
    try:
        data = request.json
        reason = data.get('reason', '').strip().upper()
        
        if not reason:
            return jsonify({"success": False, "error": "Missing reason"}), 400
        
        success = db_manager.delete_out_reason(reason)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Reason not found or failed to delete"}), 500
    except Exception as e:
        print(f"Error in delete_out_reason: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_lineout_reasons", methods=["GET"])
def get_lineout_reasons():
    """Get all LINE OUT reasons for dropdown"""
    try:
        reasons = db_manager.get_lineout_reasons()
        return jsonify({"success": True, "reasons": reasons})
    except Exception as e:
        print(f"Error in get_lineout_reasons: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/add_lineout_reason", methods=["POST"])
def add_lineout_reason():
    """Add a custom LINE OUT reason (shared across all processes)"""
    try:
        data = request.json
        reason = data.get('reason', '').strip().upper()
        
        if not reason:
            return jsonify({"success": False, "error": "Missing reason"}), 400
        
        success = db_manager.add_lineout_reason(reason)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Reason already exists or failed to add"}), 500
    except Exception as e:
        print(f"Error in add_lineout_reason: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/delete_lineout_reason", methods=["POST"])
def delete_lineout_reason():
    """Delete a LINE OUT reason (shared across all processes)"""
    try:
        data = request.json
        reason = data.get('reason', '').strip().upper()
        
        if not reason:
            return jsonify({"success": False, "error": "Missing reason"}), 400
        
        success = db_manager.delete_lineout_reason(reason)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Reason not found or failed to delete"}), 500
    except Exception as e:
        print(f"Error in delete_lineout_reason: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/in_line_process", methods=["POST"])
def in_line_process():
    """Handle IN-LINE button click with reason"""
    try:
        data = request.json
        kitting_no = data.get('kitting_no', '')
        in_line_reason = data.get('in_line_reason', '')
        elapsed_time = data.get('elapsed_time', '00:00')
        process_no = data.get('process_no', 1)
        
        print(f"IN-LINE: kitting_no={kitting_no}, in_line_reason={in_line_reason}, elapsed_time={elapsed_time}, process_no={process_no}, pass_ng=0")
        
        # SERVER-SIDE VALIDATION: Block if upstream process hasn't completed this kitting
        process_no_int = int(process_no) if process_no else 1
        if process_no_int > 1 and kitting_no:
            prev_completed = db_manager.get_completed_count(process_no_int - 1)
            kitting_no_int = int(kitting_no) if str(kitting_no).isdigit() else 0
            if kitting_no_int > prev_completed:
                print(f"IN-LINE BLOCKED: Process {process_no_int} Kitting {kitting_no_int} - Process {process_no_int-1} only completed {prev_completed}")
                return jsonify({"success": False, "error": f"Process {process_no_int-1} has only completed {prev_completed} kittings"})
        
        # Insert record with in_line_reason and pass_ng=0
        record_id = db_manager.insert_record(
            kitting_no=kitting_no,
            lineout_reason='',
            elapsed_time=elapsed_time,
            pass_ng=0,
            process_no=process_no,
            in_line_reason=in_line_reason
        )
        
        # Clear server-side timer for this process
        with server_timers_lock:
            server_timers.pop(int(process_no) if process_no else 1, None)
        
        # Update last data timestamp for auto-refresh
        update_last_data_timestamp()
        save_timer_state_to_file()
        
        if record_id:
            return jsonify({"success": True, "record_id": record_id})
        else:
            return jsonify({"success": False, "error": "Failed to insert record"}), 500
    except Exception as e:
        print(f"Error in in_line_process: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_in_line_reasons", methods=["GET"])
def get_in_line_reasons():
    """Get all IN-LINE reasons for dropdown"""
    try:
        reasons = db_manager.get_in_line_reasons()
        return jsonify({"success": True, "reasons": reasons})
    except Exception as e:
        print(f"Error in get_in_line_reasons: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/add_in_line_reason", methods=["POST"])
def add_in_line_reason():
    """Add a custom IN-LINE reason (shared across all processes)"""
    try:
        data = request.json
        reason = data.get('reason', '').strip().upper()
        
        if not reason:
            return jsonify({"success": False, "error": "Missing reason"}), 400
        
        success = db_manager.add_in_line_reason(reason)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Reason already exists or failed to add"}), 500
    except Exception as e:
        print(f"Error in add_in_line_reason: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/delete_in_line_reason", methods=["POST"])
def delete_in_line_reason():
    """Delete an IN-LINE reason (shared across all processes)"""
    try:
        data = request.json
        reason = data.get('reason', '').strip().upper()
        
        if not reason:
            return jsonify({"success": False, "error": "Missing reason"}), 400
        
        success = db_manager.delete_in_line_reason(reason)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Reason not found or failed to delete"}), 500
    except Exception as e:
        print(f"Error in delete_in_line_reason: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# ==================== REPAIRED ACTION API ====================

@app.route("/api/get_repaired_actions", methods=["GET"])
def get_repaired_actions():
    """Get all REPAIRED ACTION reasons for dropdown"""
    try:
        reasons = db_manager.get_repaired_actions()
        return jsonify({"success": True, "reasons": reasons})
    except Exception as e:
        print(f"Error in get_repaired_actions: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/add_repaired_action", methods=["POST"])
def add_repaired_action():
    """Add a custom REPAIRED ACTION reason (shared across all processes)"""
    try:
        data = request.json
        reason = data.get('reason', '').strip().upper()
        
        if not reason:
            return jsonify({"success": False, "error": "Missing reason"}), 400
        
        success = db_manager.add_repaired_action(reason)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Reason already exists or failed to add"}), 500
    except Exception as e:
        print(f"Error in add_repaired_action: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/delete_repaired_action", methods=["POST"])
def delete_repaired_action():
    """Delete a REPAIRED ACTION reason (shared across all processes)"""
    try:
        data = request.json
        reason = data.get('reason', '').strip().upper()
        
        if not reason:
            return jsonify({"success": False, "error": "Missing reason"}), 400
        
        success = db_manager.delete_repaired_action(reason)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Reason not found or failed to delete"}), 500
    except Exception as e:
        print(f"Error in delete_repaired_action: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/stop_repaired_process", methods=["POST"])
def stop_repaired_process():
    """Handle STOP after IN-LINE REPAIR with repaired action reason"""
    try:
        data = request.json
        kitting_no = data.get('kitting_no', '')
        elapsed_time = data.get('elapsed_time', '00:00')
        process_no = data.get('process_no', 1)
        repaired_action = data.get('repaired_action', '')
        in_line_reason = data.get('in_line_reason', '')
        
        print(f"STOP REPAIRED: kitting_no={kitting_no}, elapsed_time={elapsed_time}, process_no={process_no}, repaired_action={repaired_action}, in_line_reason={in_line_reason}, pass_ng=1")
        
        process_no_int = int(process_no) if process_no else 1
        if process_no_int > 1 and kitting_no:
            prev_completed = db_manager.get_completed_count(process_no_int - 1)
            kitting_no_int = int(kitting_no) if str(kitting_no).isdigit() else 0
            if kitting_no_int > prev_completed:
                return jsonify({"success": False, "error": f"Process {process_no_int-1} has only completed {prev_completed} kittings"})
        
        if elapsed_time and ':' not in elapsed_time:
            elapsed_time = '00:00'
        
        record_id = db_manager.insert_record(
            kitting_no=str(kitting_no) if kitting_no else '',
            lineout_reason=None,
            elapsed_time=str(elapsed_time),
            pass_ng=1,
            process_no=int(process_no) if process_no else 1,
            repaired_action=repaired_action,
            in_line_reason=in_line_reason
        )
        
        with server_timers_lock:
            server_timers.pop(int(process_no) if process_no else 1, None)
        
        update_last_data_timestamp()
        save_timer_state_to_file()
        
        if record_id:
            return jsonify({"success": True, "record_id": record_id})
        else:
            return jsonify({"success": False, "error": "Failed to insert record"}), 500
    except Exception as e:
        print(f"Error in stop_repaired_process: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# ==================== ARDUINO SIGNAL API ====================

@app.route("/api/arduino_signal", methods=["POST"])
def receive_arduino_signal():
    """Receive signal from Arduino bridge (arduino_bridge.py)
    Also handles server-side timer start/stop so timers work even when browser page is closed."""
    try:
        data = request.json
        process_no = int(data.get('process_no', 0))
        action = data.get('action', '').lower()  # "start" or "stop"
        
        if process_no < 1 or process_no > 9:
            return jsonify({"success": False, "error": "Invalid process_no"}), 400
        if action not in ('start', 'stop'):
            return jsonify({"success": False, "error": "Invalid action"}), 400
        
        # SERVER-SIDE TIMER HANDLING (works even when browser page is closed)
        if action == 'start':
            # Check if THIS process has manpower assigned before allowing start
            manpower = db_manager.get_all_manpower()
            this_process_has_manpower = False
            for mp in manpower:
                if mp['process_no'] == process_no:
                    has_scan = mp.get('operator_scan', '').strip() != ''
                    has_manual = mp.get('operator_manual', '').strip() != ''
                    if has_scan or has_manual:
                        this_process_has_manpower = True
                    break
            if not this_process_has_manpower:
                print(f"ARDUINO: BLOCKED Process {process_no} - No operator assigned for this process")
                return jsonify({"success": False, "error": f"Process {process_no} does not have an operator assigned"})
            
            # Check if timer is already running for this process
            with server_timers_lock:
                if process_no in server_timers:
                    print(f"ARDUINO: Process {process_no} timer already running, ignoring START")
                    return jsonify({"success": True, "info": "Timer already running"})
            
            # Get current counter and compute next kitting number
            with server_counters_lock:
                current_counter = server_counters.get(process_no, 0)
                new_counter = current_counter + 1
            
            # VALIDATE: Check if previous process has completed enough kittings
            if process_no > 1:
                prev_completed = db_manager.get_completed_count(process_no - 1)
                if new_counter > prev_completed:
                    print(f"ARDUINO: BLOCKED Process {process_no} Kitting {new_counter} - Process {process_no-1} only completed {prev_completed}")
                    return jsonify({"success": False, "error": f"Process {process_no-1} has only completed {prev_completed} kittings"})
            
            # Validation passed - start the timer
            with server_counters_lock:
                server_counters[process_no] = new_counter
            with server_timers_lock:
                server_timers[process_no] = {
                    "start_time": time.time(),
                    "kitting_no": new_counter
                }
            save_timer_state_to_file()
            print(f"ARDUINO: Server-side timer STARTED for Process {process_no}, Kitting {new_counter}")
        
        elif action == 'stop':
            with server_timers_lock:
                timer_data = server_timers.pop(process_no, None)
            
            if timer_data:
                elapsed_seconds = int(time.time() - timer_data["start_time"])
                mins = elapsed_seconds // 60
                secs = elapsed_seconds % 60
                elapsed_time_str = f"{mins:02d}:{secs:02d}"
                kitting_no = timer_data["kitting_no"]
                
                record_id = db_manager.insert_record(
                    kitting_no=str(kitting_no),
                    lineout_reason=None,
                    elapsed_time=elapsed_time_str,
                    pass_ng=1,
                    process_no=process_no
                )
                
                update_last_data_timestamp()
                save_timer_state_to_file()
                
                print(f"ARDUINO: Server-side timer STOPPED for Process {process_no}, Kitting {kitting_no}, Elapsed {elapsed_time_str}, Record ID: {record_id}")
            else:
                print(f"ARDUINO: No active timer for Process {process_no} to stop")
        
        # Store the signal for browser polling (only reached if validation passed)
        with arduino_signals_lock:
            arduino_signals[process_no] = {
                "action": action,
                "timestamp": time.time()
            }
        
        print(f"ARDUINO SIGNAL: Process {process_no} -> {action.upper()}")
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error in receive_arduino_signal: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/arduino_signal/<int:process_no>", methods=["GET"])
def get_arduino_signal(process_no):
    """Browser polls this endpoint to check for pending Arduino signals"""
    try:
        with arduino_signals_lock:
            signal = arduino_signals.pop(process_no, None)
        
        if signal:
            # Only return signals that are less than 10 seconds old
            if time.time() - signal["timestamp"] < 10:
                return jsonify({"success": True, "action": signal["action"]})
        
        return jsonify({"success": True, "action": None})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_server_timer/<int:process_no>", methods=["GET"])
def get_server_timer(process_no):
    """Get server-side timer state for a process.
    Used by browser pages to pick up timers started by Arduino when page was closed."""
    try:
        with server_timers_lock:
            timer_data = server_timers.get(process_no, None)
        
        if timer_data:
            elapsed_seconds = int(time.time() - timer_data["start_time"])
            return jsonify({
                "success": True,
                "active": True,
                "start_time": timer_data["start_time"],
                "kitting_no": timer_data["kitting_no"],
                "elapsed_seconds": elapsed_seconds
            })
        else:
            return jsonify({"success": True, "active": False})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/sync_counter/<int:process_no>", methods=["POST"])
def sync_counter(process_no):
    """Sync browser counter with server-side counter.
    Browser sends its counter value, server updates if browser value is higher."""
    try:
        data = request.json
        browser_counter = int(data.get('counter', 0))
        
        with server_counters_lock:
            server_val = server_counters.get(process_no, 0)
            # Use the higher value (browser or server)
            final_val = max(browser_counter, server_val)
            server_counters[process_no] = final_val
        
        return jsonify({"success": True, "counter": final_val})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/clear_server_timer/<int:process_no>", methods=["POST"])
def clear_server_timer(process_no):
    """Clear server-side timer (called when browser takes over the timer)."""
    try:
        with server_timers_lock:
            server_timers.pop(process_no, None)
        save_timer_state_to_file()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/start_server_timer/<int:process_no>", methods=["POST"])
def start_server_timer(process_no):
    """Start server-side timer tracking (called when browser START button is clicked)."""
    try:
        data = request.json
        kitting_no = int(data.get('kitting_no', 0))
        
        # VALIDATE: Check if previous process has completed enough kittings
        if process_no > 1:
            prev_completed = db_manager.get_completed_count(process_no - 1)
            if kitting_no > prev_completed:
                print(f"START_SERVER_TIMER: BLOCKED Process {process_no} Kitting {kitting_no} - Process {process_no-1} only completed {prev_completed}")
                return jsonify({"success": False, "error": f"Process {process_no-1} has only completed {prev_completed} kittings"})
        
        with server_timers_lock:
            server_timers[process_no] = {
                "start_time": time.time(),
                "kitting_no": kitting_no
            }
        
        # Also update server counter
        with server_counters_lock:
            server_counters[process_no] = max(server_counters.get(process_no, 0), kitting_no)
        
        # Mark that processes have started today (disables manpower warning)
        with processes_started_today_lock:
            if not processes_started_today["started"]:
                processes_started_today["started"] = True
                print("PROCESSES STARTED TODAY: Manpower warning disabled until next day reset")
        
        save_timer_state_to_file()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/stop_server_timer/<int:process_no>", methods=["POST"])
def stop_server_timer(process_no):
    """Stop server-side timer tracking (called when browser STOP button is clicked)."""
    try:
        with server_timers_lock:
            if process_no in server_timers:
                del server_timers[process_no]
        
        # Also clear active kitting
        with server_active_kittings_lock:
            if process_no in server_active_kittings:
                del server_active_kittings[process_no]
        
        save_timer_state_to_file()
        print(f"STOP_SERVER_TIMER: Process {process_no} timer stopped")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_completed_count/<int:process_no>", methods=["GET"])
def get_completed_count(process_no):
    """Get the number of completed records for a process from the database.
    Used by downstream processes to verify upstream completion."""
    try:
        count = db_manager.get_completed_count(process_no)
        # Also check if there's an active server timer (started but not yet stopped)
        with server_timers_lock:
            has_active = process_no in server_timers
        return jsonify({"success": True, "count": count, "has_active_timer": has_active})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/can_start_kitting/<int:process_no>/<int:kitting_no>", methods=["GET"])
def can_start_kitting(process_no, kitting_no):
    """Check if a process can start a specific kitting number.
    Verifies that the previous process (process_no - 1) has completed at least kitting_no records."""
    try:
        if process_no <= 1:
            return jsonify({"success": True, "allowed": True})
        
        prev_process = process_no - 1
        prev_completed = db_manager.get_completed_count(prev_process)
        
        allowed = kitting_no <= prev_completed
        print(f"CAN_START_KITTING: Process {process_no} wants Kitting {kitting_no}, Process {prev_process} completed {prev_completed}, Allowed: {allowed}")
        return jsonify({
            "success": True,
            "allowed": allowed,
            "prev_process": prev_process,
            "prev_completed": prev_completed,
            "requested_kitting": kitting_no
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_all_active_timers", methods=["GET"])
def get_all_active_timers():
    """Get active timer status for all processes (used by graph pages for blinking indicators)"""
    try:
        import time as _time
        with server_timers_lock:
            active = {}
            for k, v in server_timers.items():
                elapsed_sec = int(_time.time() - v.get("start_time", _time.time()))
                active[str(k)] = {"active": True, "elapsed_seconds": elapsed_sec}
        return jsonify({"success": True, "active_timers": active})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_last_update", methods=["GET"])
def get_last_update():
    """Get timestamp of last data update. Used by graph pages for auto-refresh."""
    try:
        with last_data_update_lock:
            ts = last_data_update["timestamp"]
        return jsonify({"success": True, "timestamp": ts})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/server_start_time", methods=["GET"])
def get_server_start_time():
    """Get server start timestamp. Used by browsers to detect server restart and auto-reload."""
    return jsonify({"success": True, "start_time": SERVER_START_TIME})

# ==================== SERVER-SIDE BLOCKED COUNTERS API ====================
# These APIs replace localStorage blocked_counters for multi-device sync

@app.route("/api/block_counter", methods=["POST"])
def block_counter():
    """Block a kitting number for all subsequent processes (called on NG/LINEOUT)"""
    try:
        data = request.json
        from_process = int(data.get('from_process', 0))
        kitting_no = int(data.get('kitting_no', 0))
        
        if from_process < 1 or from_process > 9 or kitting_no < 1:
            return jsonify({"success": False, "error": "Invalid parameters"}), 400
        
        # Block this kitting for all processes after from_process
        with server_blocked_counters_lock:
            for i in range(from_process + 1, 10):
                if i not in server_blocked_counters:
                    server_blocked_counters[i] = []
                if kitting_no not in server_blocked_counters[i]:
                    server_blocked_counters[i].append(kitting_no)
                    print(f"BLOCKED: Kitting {kitting_no} blocked for Process {i} (NG at Process {from_process})")
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error in block_counter: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/is_counter_blocked/<int:process_no>/<int:kitting_no>", methods=["GET"])
def is_counter_blocked(process_no, kitting_no):
    """Check if a kitting number is blocked for a specific process"""
    try:
        with server_blocked_counters_lock:
            blocked_list = server_blocked_counters.get(process_no, [])
            is_blocked = kitting_no in blocked_list
        return jsonify({"success": True, "blocked": is_blocked})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_blocked_counters/<int:process_no>", methods=["GET"])
def get_blocked_counters(process_no):
    """Get all blocked kitting numbers for a specific process"""
    try:
        with server_blocked_counters_lock:
            blocked_list = server_blocked_counters.get(process_no, [])
        return jsonify({"success": True, "blocked_counters": blocked_list})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/clear_blocked_counters", methods=["POST"])
def clear_blocked_counters():
    """Clear all blocked counters (called on reset)"""
    try:
        with server_blocked_counters_lock:
            server_blocked_counters.clear()
        print("All blocked counters cleared")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ==================== SERVER-SIDE ACTIVE KITTING API ====================
# These APIs replace localStorage active_kitting for multi-device sync

@app.route("/api/set_active_kitting", methods=["POST"])
def set_active_kitting():
    """Set which kitting number a process is currently working on"""
    try:
        data = request.json
        process_no = int(data.get('process_no', 0))
        kitting_no = int(data.get('kitting_no', 0))
        
        if process_no < 1 or process_no > 9:
            return jsonify({"success": False, "error": "Invalid process_no"}), 400
        
        with server_active_kittings_lock:
            if kitting_no > 0:
                server_active_kittings[process_no] = kitting_no
            else:
                server_active_kittings.pop(process_no, None)
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/clear_active_kitting/<int:process_no>", methods=["POST"])
def clear_active_kitting(process_no):
    """Clear active kitting for a process (called on STOP)"""
    try:
        with server_active_kittings_lock:
            server_active_kittings.pop(process_no, None)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/is_kitting_active/<int:kitting_no>", methods=["GET"])
def is_kitting_active(kitting_no):
    """Check if a kitting number is being processed by any process"""
    try:
        with server_active_kittings_lock:
            for proc, kit in server_active_kittings.items():
                if kit == kitting_no:
                    return jsonify({"success": True, "active": True, "process_no": proc})
        return jsonify({"success": True, "active": False, "process_no": None})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/get_all_active_kittings", methods=["GET"])
def get_all_active_kittings():
    """Get all active kittings across all processes"""
    try:
        with server_active_kittings_lock:
            active_copy = dict(server_active_kittings)
        return jsonify({"success": True, "active_kittings": active_copy})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ==================== FULL STATE SYNC API ====================
# Single API to get all state needed for a process page

@app.route("/api/get_process_state/<int:process_no>", methods=["GET"])
def get_process_state(process_no):
    """Get complete state for a process (counter, timer, blocked, active kittings)
    This is the main API for multi-device synchronization."""
    try:
        # Check for daily reset (new day detection)
        check_daily_reset()
        
        # Get server counter
        with server_counters_lock:
            counter = server_counters.get(process_no, 0)
        
        # Get server timer
        with server_timers_lock:
            timer_data = server_timers.get(process_no, None)
        
        timer_info = None
        if timer_data:
            elapsed_seconds = int(time.time() - timer_data["start_time"])
            timer_info = {
                "active": True,
                "kitting_no": timer_data["kitting_no"],
                "elapsed_seconds": elapsed_seconds
            }
        
        # Get blocked counters for this process
        with server_blocked_counters_lock:
            blocked = server_blocked_counters.get(process_no, [])
        
        # Get all active kittings (to check if next kitting is being processed elsewhere)
        with server_active_kittings_lock:
            active_kittings = dict(server_active_kittings)
        
        # Get completed count from database
        completed_count = db_manager.get_completed_count(process_no)
        
        # Get previous process completed count (for validation)
        prev_completed = 0
        if process_no > 1:
            prev_completed = db_manager.get_completed_count(process_no - 1)
        
        return jsonify({
            "success": True,
            "process_no": process_no,
            "counter": counter,
            "timer": timer_info,
            "blocked_counters": blocked,
            "active_kittings": active_kittings,
            "completed_count": completed_count,
            "prev_completed": prev_completed
        })
    except Exception as e:
        print(f"Error in get_process_state: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# ==================== QR CODE PRINTER API ====================
@app.route("/api/print_kitting_qr", methods=["POST"])
def print_kitting_qr():
    """Print a kitting QR code label to the SATO PW208NX printer"""
    try:
        data = request.json
        qr_data = data.get('qr_data', '')
        printer_name = data.get('printer_name', None)
        
        if not qr_data:
            return jsonify({"success": False, "error": "QR data is required"}), 400
        
        print(f"PRINTING QR CODE: {qr_data}")
        
        # Try SBPL first, then fall back to CPCL if needed
        result = qr_printer.print_kitting_qr_code(qr_data, printer_name)
        
        if result['success']:
            print(f"QR PRINT SUCCESS: {result['message']}")
            return jsonify({"success": True, "message": result['message']})
        else:
            # Try CPCL format as fallback
            print(f"SBPL failed, trying CPCL: {result['message']}")
            result_cpcl = qr_printer.print_kitting_qr_code_cpcl(qr_data, printer_name)
            if result_cpcl['success']:
                print(f"QR PRINT SUCCESS (CPCL): {result_cpcl['message']}")
                return jsonify({"success": True, "message": result_cpcl['message']})
            else:
                print(f"QR PRINT FAILED: {result_cpcl['message']}")
                return jsonify({"success": False, "error": result_cpcl['message']}), 500
            
    except Exception as e:
        print(f"Error printing QR code: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/list_printers", methods=["GET"])
def api_list_printers():
    """List all available printers on the system"""
    try:
        printers = qr_printer.list_printers()
        sato_printer = qr_printer.get_sato_printer_name()
        return jsonify({
            "success": True, 
            "printers": printers,
            "sato_printer": sato_printer
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def start_arduino_bridge():
    """Launch arduino_bridge.py as a background subprocess (auto-start with Flask)"""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        bridge_script = os.path.join(script_dir, "arduino_bridge.py")
        print("\n>>> Auto-starting Arduino bridge in background...")
        subprocess.Popen(
            [sys.executable, bridge_script, "--no-prompt"],
            cwd=script_dir
        )
        print(">>> Arduino bridge subprocess launched.")
    except Exception as e:
        print(f">>> WARNING: Could not start Arduino bridge: {e}")
        print(">>> The web application will continue running without Arduino input.")

# Start the website when this file is run
# This code only runs when you click "Run" on this file
if __name__ == "__main__":
    # Initialize database connection and create tables
    # try:
    #     db_manager.connect()
    #     print("Database initialized successfully")
    # except Exception as e:
    #     print(f"Failed to initialize database: {e}")
    #     print("Please ensure XAMPP MySQL/MariaDB is running")

    # Load persisted timer state from file (survives Flask restarts)
    load_timer_state_from_file()
    
    # Load last active date from file and check for daily reset
    load_last_active_date()
    check_daily_reset()
    
    # Load job order start time from file (for graph filtering)
    load_job_order_start_time()
    
    # Check if processes have already started today (to disable manpower warning)
    initialize_processes_started_today()
    
    # Auto-start Arduino bridge only in the reloader child process
    # (Flask debug=True runs __main__ twice; this prevents double-launch)
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        start_arduino_bridge()
    
    # host="0.0.0.0": Anyone on the network can visit (not just you)
    # port=5000: The website "door number" - like apartment 5000
    # debug=True: Shows helpful error messages if something breaks
    # app.run(host="192.168.3.220", port=5000, debug=True)  #host="0.0.0.0", port=5000 for porthost
    app.run(host="0.0.0.0", port=5000, debug=True)  #host="0.0.0.0", port=5000 for porthost-
