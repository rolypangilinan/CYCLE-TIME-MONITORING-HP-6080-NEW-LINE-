import mysql.connector
from mysql.connector import Error, pooling
from datetime import datetime
import torisql

class DatabaseManager:
    def __init__(self):
        self.host = "localhost"
        self.port = 3306
        self.user = "root"
        self.password = "/HPI4020495/"  # Default XAMPP password is empty
        self.database_name = "cycle_time_monitoring"
        self.connection = None
        self.pool = None  # Connection pool for faster queries
        
    def connect(self):
        """Create database connection"""
        try:
            # First connect without specifying database to create it if needed
            temp_conn = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password
            )
            
            temp_cursor = temp_conn.cursor()
            temp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database_name}")
            temp_cursor.close()
            temp_conn.close()
            
            # Now connect WITH the database specified
            self.connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name
            )
            
            cursor = self.connection.cursor()
            
            # Create table if it doesn't exist
            create_table_query = """
            CREATE TABLE IF NOT EXISTS process_records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                kitting_no VARCHAR(255),
                lineout_reason VARCHAR(255),
                in_line_reason VARCHAR(255),
                elapsed_time TIME,
                pass_ng INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                process_no INTEGER,
                INDEX idx_process_no (process_no),
                INDEX idx_timestamp (timestamp)
            )
            """
            cursor.execute(create_table_query)
            
            # Create standard_times table if it doesn't exist
            create_standard_times_table = """
            CREATE TABLE IF NOT EXISTS standard_times (
                process_no INT PRIMARY KEY,
                standard_time DECIMAL(5,2) DEFAULT 1.50,
                title VARCHAR(255) DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
            cursor.execute(create_standard_times_table)
            
            # Alter column type if it was previously INT
            try:
                cursor.execute("ALTER TABLE standard_times MODIFY COLUMN standard_time DECIMAL(5,2) DEFAULT 1.50")
            except:
                pass
            
            # Add title column if it doesn't exist
            try:
                cursor.execute("ALTER TABLE standard_times ADD COLUMN title VARCHAR(255) DEFAULT ''")
            except:
                pass
            
            # Default ST values per process (in minutes)
            default_st = {
                1: 1.56, 2: 1.73, 3: 1.53, 4: 1.49, 5: 1.46,
                6: 1.50, 7: 0.70, 8: 1.18, 9: 1.44
            }
            
            # Default titles per process
            default_titles = {
                1: 'EM Fastening', 2: 'DF & Rod Casing Fastening', 3: 'Partition Board',
                4: 'Lower Housing Prep', 5: 'Lower Housing Fastening',
                6: 'Combination Leadwire Arrange', 7: 'Soldering',
                8: 'Upper Housing', 9: 'Packing'
            }
            
            # Insert default standard times for processes 1-9 if they don't exist
            for i in range(1, 10):
                cursor.execute("INSERT IGNORE INTO standard_times (process_no, standard_time, title) VALUES (%s, %s, %s)", (i, default_st[i], default_titles[i]))
            
            # Update titles for existing rows that have empty titles
            for i in range(1, 10):
                cursor.execute("UPDATE standard_times SET title = %s WHERE process_no = %s AND (title IS NULL OR title = '')", (default_titles[i], i))
            
            # Create manpower table if it doesn't exist
            create_manpower_table = """
            CREATE TABLE IF NOT EXISTS manpower (
                process_no INT PRIMARY KEY,
                id_no VARCHAR(50) DEFAULT '',
                operator_name VARCHAR(255) DEFAULT '',
                employment_status VARCHAR(50) DEFAULT '',
                operator_manual VARCHAR(255) DEFAULT '',
                operator_scan VARCHAR(255) DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
            cursor.execute(create_manpower_table)
            
            # Add new columns if they don't exist (for existing databases)
            for col_name, col_def in [('id_no', 'VARCHAR(50) DEFAULT \"\" AFTER process_no'),
                                       ('operator_name', 'VARCHAR(255) DEFAULT \"\" AFTER id_no'),
                                       ('employment_status', 'VARCHAR(50) DEFAULT \"\" AFTER operator_name'),
                                       ('time_in', 'DATETIME DEFAULT NULL AFTER operator_scan')]:
                try:
                    cursor.execute(f"ALTER TABLE manpower ADD COLUMN {col_name} {col_def}")
                except Exception:
                    pass  # Column already exists
            
            # Insert default manpower rows for processes 1-9 if they don't exist
            for i in range(1, 10):
                cursor.execute("INSERT IGNORE INTO manpower (process_no) VALUES (%s)", (i,))
            
            # Create mtrl_set_operator table (single row for Material Setter operator)
            create_mtrl_set_operator_table = """
            CREATE TABLE IF NOT EXISTS mtrl_set_operator (
                id INT PRIMARY KEY DEFAULT 1,
                id_no VARCHAR(50) DEFAULT '',
                operator_name VARCHAR(255) DEFAULT '',
                employment_status VARCHAR(50) DEFAULT '',
                operator_manual VARCHAR(255) DEFAULT '',
                operator_scan VARCHAR(255) DEFAULT '',
                time_in DATETIME DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
            cursor.execute(create_mtrl_set_operator_table)
            
            # Insert default single row if it doesn't exist
            cursor.execute("INSERT IGNORE INTO mtrl_set_operator (id) VALUES (1)")
            
            # Create bio_break table for operator OUT reasons (shared across all processes)
            create_bio_break_table = """
            CREATE TABLE IF NOT EXISTS bio_break (
                id INT AUTO_INCREMENT PRIMARY KEY,
                out_reasons VARCHAR(255) NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            cursor.execute(create_bio_break_table)
            
            # Migrate old out_reasons table to bio_break if it exists
            try:
                cursor.execute("INSERT IGNORE INTO bio_break (out_reasons) SELECT reason FROM out_reasons")
                cursor.execute("DROP TABLE IF EXISTS out_reasons")
            except:
                pass
            
            # Insert default OUT reasons if they don't exist
            default_out_reasons = ['CR', 'CLINIC', 'GO TO OTHER LINE', 'EMERGENCY', 'SENT HOME']
            for reason in default_out_reasons:
                cursor.execute("INSERT IGNORE INTO bio_break (out_reasons) VALUES (%s)", (reason,))
            
            # Create lineout_reasons table for LINE OUT reasons (shared across all processes)
            create_lineout_reasons_table = """
            CREATE TABLE IF NOT EXISTS lineout_reasons (
                id INT AUTO_INCREMENT PRIMARY KEY,
                reason VARCHAR(255) NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            cursor.execute(create_lineout_reasons_table)
            
            # Insert default LINE OUT reasons if they don't exist
            default_lineout_reasons = ['NG PRESSURE', 'LEAK', 'LW', 'LAV', 'LCP', 'LA', 'HW', 'HAV', 'HCP', 'HA']
            for reason in default_lineout_reasons:
                cursor.execute("INSERT IGNORE INTO lineout_reasons (reason) VALUES (%s)", (reason,))
            
            # Create ms_change_model_reasons table for CHANGE MODEL reasons (Material Setter)
            create_change_model_reasons_table = """
            CREATE TABLE IF NOT EXISTS ms_change_model_reasons (
                id INT AUTO_INCREMENT PRIMARY KEY,
                reason VARCHAR(255) NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            cursor.execute(create_change_model_reasons_table)
            
            # Insert default CHANGE MODEL reasons
            default_change_model_reasons = ['PERFORMANCE PROBLEM', 'LACKING MATLS', 'MACHINE PROBLEM']
            for reason in default_change_model_reasons:
                cursor.execute("INSERT IGNORE INTO ms_change_model_reasons (reason) VALUES (%s)", (reason,))
            
            # Create in_line_reasons table for IN-LINE reasons (shared across all processes)
            create_in_line_reasons_table = """
            CREATE TABLE IF NOT EXISTS in_line_reasons (
                id INT AUTO_INCREMENT PRIMARY KEY,
                reason VARCHAR(255) NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            cursor.execute(create_in_line_reasons_table)
            
            # Create repaired_actions table for REPAIRED ACTION reasons (shared across all processes)
            create_repaired_actions_table = """
            CREATE TABLE IF NOT EXISTS repaired_actions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                reason VARCHAR(255) NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            cursor.execute(create_repaired_actions_table)
            
            # Create kitting_material table for material categories (23 rows)
            create_kitting_material_table = """
            CREATE TABLE IF NOT EXISTS kitting_material (
                id INT AUTO_INCREMENT PRIMARY KEY,
                row_no INT NOT NULL UNIQUE,
                category_name VARCHAR(255) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            cursor.execute(create_kitting_material_table)
            
            # Insert default kitting material categories (23 rows)
            default_kitting_materials = [
                (1, 'Frame Block'),
                (2, 'EM Block'),
                (3, 'Spacer'),
                (4, 'DF Block'),
                (5, 'ROD Block'),
                (6, 'Casing Block'),
                (7, 'Partition Board'),
                (8, 'L-Tube'),
                (9, 'Hose Clip'),
                (10, 'Switch Block'),
                (11, 'Lead Bushing'),
                (12, 'Ground wire'),
                (13, 'VCR'),
                (14, 'Lower Housing'),
                (15, 'Rubber Foot'),
                (16, 'Powercord'),
                (17, 'Partition Gasket'),
                (18, 'Upper Housing'),
                (19, 'Filter Cover'),
                (20, 'Filter'),
                (21, 'Sound Absorber'),
                (22, 'Manual and Accessories'),
                (23, 'L-hose set')
            ]
            for row_no, category_name in default_kitting_materials:
                cursor.execute("INSERT IGNORE INTO kitting_material (row_no, category_name) VALUES (%s, %s)", (row_no, category_name))
            
            # Create MAIN_DB table for material setter main data (SS1)
            # This stores the current state of materials with remaining QTY
            # lot_qty = LOT QTY from Total Quantity Monitor
            # remaining_qty = REM QTY
            create_main_db_table = """
            CREATE TABLE IF NOT EXISTS MAIN_DB (
                id INT AUTO_INCREMENT PRIMARY KEY,
                job_order VARCHAR(50),
                model_code VARCHAR(100),
                row_no INT,
                material_description VARCHAR(500),
                qty_unit INT DEFAULT 0,
                scan_material VARCHAR(100),
                lot_no VARCHAR(100),
                lot_qty INT DEFAULT 0,
                remaining_qty INT DEFAULT 0,
                date_today DATE,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_job_row (job_order, row_no),
                INDEX idx_job_order (job_order),
                INDEX idx_lot_no (lot_no)
            )
            """
            cursor.execute(create_main_db_table)
            
            # Create KITTING_DB table for kitting records (SS3/SS4)
            # Each kitting completion creates a new set of records
            create_kitting_db_table = """
            CREATE TABLE IF NOT EXISTS KITTING_DB (
                id INT AUTO_INCREMENT PRIMARY KEY,
                kitting_no INT,
                job_order VARCHAR(50),
                model_code VARCHAR(100),
                row_no INT,
                material_description VARCHAR(500),
                qty_unit INT DEFAULT 0,
                material_code_scanned VARCHAR(100),
                lot_number VARCHAR(100),
                quantity_kitting INT DEFAULT 0,
                date_today DATE,
                kitting_qr_code VARCHAR(100),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_kitting_no (kitting_no),
                INDEX idx_job_order (job_order),
                INDEX idx_lot_number (lot_number),
                INDEX idx_kitting_qr_code (kitting_qr_code)
            )
            """
            cursor.execute(create_kitting_db_table)
            
            # Create kitting_summary table for storing current kitting summary state
            # This mirrors the KITTING SUMMARY display in the browser
            # Columns: id, job_order, model_code, row_no, material_description, qty_unit, scan_material, lot_no, qty_kit, date_today, timestamp
            create_kitting_summary_table = """
            CREATE TABLE IF NOT EXISTS kitting_summary (
                id INT AUTO_INCREMENT PRIMARY KEY,
                job_order VARCHAR(50),
                model_code VARCHAR(100),
                row_no INT,
                material_description VARCHAR(500),
                qty_unit INT DEFAULT 0,
                scan_material VARCHAR(100),
                lot_no VARCHAR(100),
                qty_kit INT DEFAULT 0,
                date_today DATE,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_job_row (job_order, row_no),
                INDEX idx_job_order (job_order)
            )
            """
            cursor.execute(create_kitting_summary_table)
            
            # Drop old/unused columns if they exist (compatible with all MySQL versions)
            columns_to_drop = ['kitting_no', 'is_new_lot_row', 'parent_row_no', 'mtrl_desc', 'scan_mtrl', 'material_code']
            for col in columns_to_drop:
                try:
                    cursor.execute("""
                        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'kitting_summary' AND COLUMN_NAME = %s
                    """, (self.database_name, col))
                    if cursor.fetchone()[0] > 0:
                        cursor.execute(f"ALTER TABLE kitting_summary DROP COLUMN {col}")
                        print(f"Dropped column '{col}' from kitting_summary")
                except Exception as e:
                    print(f"Error dropping column '{col}': {e}")
            
            # Add new columns if they don't exist
            try:
                cursor.execute("ALTER TABLE kitting_summary ADD COLUMN IF NOT EXISTS material_description VARCHAR(500) AFTER row_no")
                cursor.execute("ALTER TABLE kitting_summary ADD COLUMN IF NOT EXISTS scan_material VARCHAR(100) AFTER qty_unit")
            except:
                pass
            
            # Create joborder_plan table for tracking kitting progress per job order
            # This tracks each kitting scan with incrementing result and decrementing balance
            # Also stores operator info for Material Setter (both databases)
            create_joborder_plan_table = """
            CREATE TABLE IF NOT EXISTS joborder_plan (
                id INT AUTO_INCREMENT PRIMARY KEY,
                job_order VARCHAR(50),
                operator_name VARCHAR(255) DEFAULT '',
                time_in DATETIME DEFAULT NULL,
                time_out DATETIME DEFAULT NULL,
                out_reasons VARCHAR(255) DEFAULT '',
                suffix VARCHAR(10),
                model_code VARCHAR(100),
                row_no INT,
                kitting_qr_code VARCHAR(100),
                plan INT DEFAULT 0,
                result INT DEFAULT 0,
                balance INT DEFAULT 0,
                date_today DATE,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_job_order (job_order),
                INDEX idx_kitting_qr_code (kitting_qr_code)
            )
            """
            cursor.execute(create_joborder_plan_table)
            
            # Add operator columns to joborder_plan if they don't exist (migration for existing tables)
            for col_name, col_def in [
                ("operator_name", "VARCHAR(255) DEFAULT '' AFTER job_order"),
                ("time_in", "DATETIME DEFAULT NULL AFTER operator_name"),
                ("time_out", "DATETIME DEFAULT NULL AFTER time_in"),
                ("out_reasons", "VARCHAR(255) DEFAULT '' AFTER time_out"),
                ("change_model_reason", "VARCHAR(255) DEFAULT '' AFTER out_reasons")
            ]:
                try:
                    cursor.execute(f"ALTER TABLE joborder_plan ADD COLUMN {col_name} {col_def}")
                    print(f"  Added column {col_name} to joborder_plan")
                except Exception as e:
                    if 'Duplicate column' in str(e):
                        pass  # Column already exists, OK
                    else:
                        print(f"  Warning: Could not add column {col_name}: {e}")
            
            # Create 26 material-specific tables for saving after QR code scan
            material_tables = [
                (1, '01tbl_frame_zam'),
                (2, '02tbl_frame_lead'),
                (3, '03tbl_spacer'),
                (4, '04tbl_2p'),
                (5, '05tbl_p3p'),
                (6, '06tbl_df_block'),
                (7, '07tbl_rod'),
                (8, '08tbl_casing_block'),
                (9, '09tbl_partition_board'),
                (10, '10tbl_l_tube'),
                (11, '11tbl_hose_clip'),
                (12, '12tbl_switch_block'),
                (13, '13tbl_lead_bushing'),
                (14, '14tbl_ground_wire'),
                (15, '15tbl_vcr'),
                (16, '16tbl_lower_housing'),
                (17, '17tbl_rubber_foot'),
                (18, '18tbl_power_cord'),
                (19, '19tbl_partition_gasket'),
                (20, '20tbl_upper_housing'),
                (21, '21tbl_filter_cover'),
                (22, '22tbl_filter'),
                (23, '23tbl_sound_absorbing'),
                (24, '24tbl_manual'),
                (25, '25tbl_l_hose_set'),
                (26, '26tbl_filter_bush')
            ]
            
            for row_no, table_name in material_tables:
                create_material_table = f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    kitting_no INT,
                    job_order VARCHAR(50),
                    model_code VARCHAR(100),
                    mtrl_desc VARCHAR(500),
                    qty_unit INT DEFAULT 0,
                    scan_mtrl VARCHAR(100),
                    lot_no VARCHAR(100),
                    qty_kit INT DEFAULT 0,
                    kitting_qr_code VARCHAR(100),
                    date_today DATE,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_job_order (job_order),
                    INDEX idx_kitting_no (kitting_no),
                    INDEX idx_kitting_qr_code (kitting_qr_code)
                )
                """
                cursor.execute(create_material_table)
                
                # SS5: Add qty_kit column if it doesn't exist (for existing tables)
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='{self.database_name}' AND TABLE_NAME='{table_name}' AND COLUMN_NAME='qty_kit'")
                    col_exists = cursor.fetchone()[0]
                    if col_exists == 0:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN qty_kit INT DEFAULT 0 AFTER lot_no")
                        print(f"Added qty_kit column to {table_name}")
                except Exception as e:
                    print(f"Warning: Could not add qty_kit to {table_name}: {e}")
            
            # Add in_line_reason column to process_records if it doesn't exist
            try:
                cursor.execute("ALTER TABLE process_records ADD COLUMN in_line_reason VARCHAR(255) AFTER lineout_reason")
            except:
                pass
            
            # Add repaired_action column to process_records if it doesn't exist
            try:
                cursor.execute("ALTER TABLE process_records ADD COLUMN repaired_action VARCHAR(255) AFTER in_line_reason")
            except:
                pass
            
            # Add kitting_qr_code column to KITTING_DB if it doesn't exist
            try:
                cursor.execute("ALTER TABLE KITTING_DB ADD COLUMN kitting_qr_code VARCHAR(100) AFTER date_today")
            except:
                pass
            
            # Create separate tables for each process (process_1 through process_9)
            for i in range(1, 10):
                create_process_table = f"""
                CREATE TABLE IF NOT EXISTS process_{i} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    kitting_no VARCHAR(255),
                    lineout_reason VARCHAR(255),
                    in_line_reason VARCHAR(255),
                    repaired_action VARCHAR(255),
                    elapsed_time TIME,
                    pass_ng INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    process_no INTEGER,
                    operator_name VARCHAR(255) DEFAULT '',
                    out_reasons VARCHAR(255) DEFAULT '',
                    INDEX idx_timestamp (timestamp)
                )
                """
                cursor.execute(create_process_table)
                # Add in_line_reason column if table already exists without it
                try:
                    cursor.execute(f"ALTER TABLE process_{i} ADD COLUMN in_line_reason VARCHAR(255) AFTER lineout_reason")
                except:
                    pass
                # Add repaired_action column if table already exists without it
                try:
                    cursor.execute(f"ALTER TABLE process_{i} ADD COLUMN repaired_action VARCHAR(255) AFTER in_line_reason")
                except:
                    pass
                # Add out_reasons column if table already exists without it
                try:
                    cursor.execute(f"ALTER TABLE process_{i} ADD COLUMN out_reasons VARCHAR(255) DEFAULT '' AFTER operator_name")
                except:
                    pass
                # Add time_in column if table already exists without it
                try:
                    cursor.execute(f"ALTER TABLE process_{i} ADD COLUMN time_in DATETIME DEFAULT NULL AFTER operator_name")
                except:
                    pass
                # Add time_out column if table already exists without it
                try:
                    cursor.execute(f"ALTER TABLE process_{i} ADD COLUMN time_out DATETIME DEFAULT NULL AFTER time_in")
                except:
                    pass
            
            # Parse existing operator_scan data to populate id_no, operator_name, employment_status
            cursor.execute("SELECT process_no, operator_scan FROM manpower WHERE operator_scan != '' AND (id_no IS NULL OR id_no = '')")
            rows = cursor.fetchall()
            for row in rows:
                pno = row[0]
                scan_data = row[1]
                parts = scan_data.split(' , ')
                if len(parts) >= 3:
                    cursor.execute("UPDATE manpower SET id_no = %s, operator_name = %s, employment_status = %s WHERE process_no = %s",
                                   (parts[0].strip(), parts[1].strip(), parts[2].strip(), pno))
            
            self.connection.commit()
            print("Database and table initialized successfully")
            
        except Error as e:
            print(f"Error connecting to database: {e}")
            raise e
        finally:
            if 'cursor' in locals():
                cursor.close()
    
    def get_connection(self):
        if torisql.isToriMode:
            return
        """Get a connection from the pool (much faster than creating new connections)"""
        if self.pool is None:
            # Create connection pool on first use
            self.pool = pooling.MySQLConnectionPool(
                pool_name="cycle_time_pool",
                pool_size=10,
                pool_reset_session=True,
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name
            )
        return self.pool.get_connection()
    
    def insert_record(self, kitting_no, lineout_reason, elapsed_time, pass_ng, process_no, in_line_reason=None, repaired_action=None, out_reasons=None, time_in=None, time_out=None):
        """Insert a new record into process_records table"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            # Convert elapsed_time from MM:SS to TIME format
            if elapsed_time and ':' in elapsed_time:
                # If format is MM:SS, convert to HH:MM:SS
                parts = elapsed_time.split(':')
                if len(parts) == 2:
                    elapsed_time = f"00:{parts[0]}:{parts[1]}"
            
            # Set lineout_reason to '-' if it's None or empty
            if lineout_reason is None or lineout_reason == '':
                lineout_reason = '-'
            
            # Set in_line_reason to '-' if it's None or empty
            if in_line_reason is None or in_line_reason == '':
                in_line_reason = '-'
            
            # Set repaired_action to '-' if it's None or empty
            if repaired_action is None or repaired_action == '':
                repaired_action = '-'
            
            # Set out_reasons to '-' if it's None or empty
            if out_reasons is None or out_reasons == '':
                out_reasons = '-'
            
            # kitting_no is now sent directly as the correct value from the frontend
            # No adjustment needed since counter increments on START
            
            insert_query = """
            INSERT INTO process_records 
            (kitting_no, lineout_reason, in_line_reason, repaired_action, elapsed_time, pass_ng, process_no)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            record = (kitting_no, lineout_reason, in_line_reason, repaired_action, elapsed_time, pass_ng, process_no)
            print(f"Inserting record: kitting_no={kitting_no}, lineout_reason={lineout_reason}, in_line_reason={in_line_reason}, repaired_action={repaired_action}, elapsed_time={elapsed_time}, pass_ng={pass_ng}, process_no={process_no}")
            cursor.execute(insert_query, record)
            connection.commit()
            
            record_id = cursor.lastrowid
            print(f"Record inserted successfully with ID: {record_id}")
            
            # Also insert into per-process table (process_1 .. process_9) with operator_name
            pno = int(process_no) if process_no else 0
            if 1 <= pno <= 9:
                try:
                    # Look up operator_name and time_in from manpower table
                    cursor.execute("SELECT operator_name, time_in FROM manpower WHERE process_no = %s", (pno,))
                    mp_row = cursor.fetchone()
                    op_name = mp_row[0] if mp_row and mp_row[0] else ''
                    # Use time_in from manpower if not provided
                    actual_time_in = time_in if time_in else (mp_row[1] if mp_row and len(mp_row) > 1 else None)
                    
                    per_process_query = f"""
                    INSERT INTO process_{pno}
                    (kitting_no, lineout_reason, in_line_reason, repaired_action, elapsed_time, pass_ng, process_no, operator_name, time_in, time_out, out_reasons)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(per_process_query, (kitting_no, lineout_reason, in_line_reason, repaired_action, elapsed_time, pass_ng, pno, op_name, actual_time_in, time_out, out_reasons))
                    connection.commit()
                    print(f"Per-process record inserted into process_{pno} (operator: {op_name}, time_in: {actual_time_in}, out_reasons: {out_reasons})")
                except Exception as pe:
                    print(f"Warning: Failed to insert into process_{pno} table: {pe}")
            
            return record_id
            
        except Error as e:
            print(f"Error inserting record: {e}")
            if connection:
                connection.rollback()
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_records_by_process(self, process_no, limit=100):
        """Get records for a specific process"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            query = """
            SELECT * FROM process_records 
            WHERE process_no = %s 
            ORDER BY timestamp DESC 
            LIMIT %s
            """
            
            cursor.execute(query, (process_no, limit))
            records = cursor.fetchall()
            
            return records
            
        except Error as e:
            print(f"Error fetching records: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_latest_record(self, process_no):
        """Get the latest record for a specific process"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            query = """
            SELECT * FROM process_records 
            WHERE process_no = %s 
            ORDER BY timestamp DESC 
            LIMIT 1
            """
            
            cursor.execute(query, (process_no,))
            record = cursor.fetchone()
            
            return record
            
        except Error as e:
            print(f"Error fetching latest record: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_completed_count(self, process_no):
        """Get the count of completed records for a specific process (today only)"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            query = "SELECT COUNT(*) FROM process_records WHERE process_no = %s AND DATE(timestamp) = CURDATE()"
            cursor.execute(query, (process_no,))
            result = cursor.fetchone()
            return result[0] if result else 0
        except Error as e:
            print(f"Error getting completed count: {e}")
            return 0
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def close(self):
        """Close database connection"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            print("Database connection closed")
    
    def disconnect(self):
        """Disconnect from database and close connection pool"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            self.connection = None
        if self.pool:
            self.pool = None
        print("Database disconnected")
    
    def get_all_standard_times(self):
        """Get all standard times"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            
            query = "SELECT process_no, standard_time, title FROM standard_times ORDER BY process_no"
            cursor.execute(query)
            standard_times = cursor.fetchall()
            
            return standard_times
            
        except Error as e:
            print(f"Error fetching standard times: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def update_standard_time(self, process_no, standard_time, title=None):
        """Update standard time for a process"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            if title is not None:
                query = "UPDATE standard_times SET standard_time = %s, title = %s WHERE process_no = %s"
                cursor.execute(query, (standard_time, title, process_no))
            else:
                query = "UPDATE standard_times SET standard_time = %s WHERE process_no = %s"
                cursor.execute(query, (standard_time, process_no))
            connection.commit()
            
            return cursor.rowcount > 0
            
        except Error as e:
            print(f"Error updating standard time: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def add_new_process(self, standard_time='50'):
        """Add a new process with standard time"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            # Get the next process number
            cursor.execute("SELECT MAX(process_no) FROM standard_times")
            result = cursor.fetchone()
            next_process_no = (result[0] or 0) + 1
            
            # Insert new process
            query = "INSERT INTO standard_times (process_no, standard_time) VALUES (%s, %s)"
            cursor.execute(query, (next_process_no, standard_time))
            connection.commit()
            
            return next_process_no
            
        except Error as e:
            print(f"Error adding new process: {e}")
            if connection:
                connection.rollback()
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def delete_process(self, process_no):
        """Delete a process (only processes > 9)"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            # Delete from standard_times table
            query = "DELETE FROM standard_times WHERE process_no = %s"
            cursor.execute(query, (process_no,))
            
            # Also delete related records from process_records
            query_records = "DELETE FROM process_records WHERE process_no = %s"
            cursor.execute(query_records, (process_no,))
            
            connection.commit()
            
            return cursor.rowcount > 0
            
        except Error as e:
            print(f"Error deleting process: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_all_manpower(self):
        """Get all manpower records"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            
            query = "SELECT process_no, id_no, operator_name, employment_status, operator_manual, operator_scan FROM manpower ORDER BY process_no"
            cursor.execute(query)
            manpower = cursor.fetchall()
            
            return manpower
            
        except Error as e:
            print(f"Error fetching manpower: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def update_manpower(self, process_no, operator_manual=None, operator_scan=None):
        """Update manpower for a process"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            # Parse operator_scan to extract id_no, operator_name, employment_status
            id_no = ''
            operator_name = ''
            employment_status = ''
            scan_val = operator_scan or ''
            if scan_val:
                parts = scan_val.split(' , ')
                if len(parts) >= 3:
                    id_no = parts[0].strip()
                    operator_name = parts[1].strip()
                    employment_status = parts[2].strip()
                elif len(parts) == 2:
                    id_no = parts[0].strip()
                    operator_name = parts[1].strip()
                elif len(parts) == 1:
                    id_no = parts[0].strip()
            
            # Record time_in when operator scans in
            from datetime import datetime
            time_in = datetime.now()
            
            query = "UPDATE manpower SET id_no = %s, operator_name = %s, employment_status = %s, operator_manual = %s, operator_scan = %s, time_in = %s WHERE process_no = %s"
            cursor.execute(query, (id_no, operator_name, employment_status, operator_manual or '', scan_val, time_in, process_no))
            connection.commit()
            
            return cursor.rowcount > 0
            
        except Error as e:
            print(f"Error updating manpower: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def clear_manpower(self, process_no):
        """Clear operator data for a process (operator OUT)"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            query = "UPDATE manpower SET id_no = '', operator_name = '', employment_status = '', operator_manual = '', operator_scan = '' WHERE process_no = %s"
            cursor.execute(query, (process_no,))
            connection.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f"Error clearing manpower: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_out_reasons(self):
        """Get all OUT reasons from bio_break table"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id, out_reasons FROM bio_break ORDER BY id")
            return cursor.fetchall()
        except Error as e:
            print(f"Error fetching out reasons: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def add_out_reason(self, reason):
        """Add a custom OUT reason to bio_break table (shared across all processes)"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            cursor.execute("INSERT IGNORE INTO bio_break (out_reasons) VALUES (%s)", (reason.upper(),))
            connection.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f"Error adding out reason: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def delete_out_reason(self, reason):
        """Delete an OUT reason from bio_break table (shared across all processes)"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            cursor.execute("DELETE FROM bio_break WHERE out_reasons = %s", (reason,))
            connection.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f"Error deleting out reason: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def update_out_reason(self, process_no, reason):
        """Update out_reasons in the last record of a process table when operator signs out"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            # Update the most recent record for this process with the OUT reason
            query = f"""
            UPDATE process_{process_no} 
            SET out_reasons = %s 
            WHERE id = (SELECT max_id FROM (SELECT MAX(id) as max_id FROM process_{process_no}) as temp)
            """
            cursor.execute(query, (reason,))
            connection.commit()
            print(f"Updated out_reasons to '{reason}' for last record in process_{process_no}")
            return cursor.rowcount > 0
        except Error as e:
            print(f"Error updating out_reasons: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def update_time_out(self, process_no):
        """Update time_out in the last record of a process table when operator signs out"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            from datetime import datetime
            time_out = datetime.now()
            # Update the most recent record for this process with the time_out
            query = f"""
            UPDATE process_{process_no} 
            SET time_out = %s 
            WHERE id = (SELECT max_id FROM (SELECT MAX(id) as max_id FROM process_{process_no}) as temp)
            """
            cursor.execute(query, (time_out,))
            connection.commit()
            print(f"Updated time_out to '{time_out}' for last record in process_{process_no}")
            return cursor.rowcount > 0
        except Error as e:
            print(f"Error updating time_out: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_manpower_time_in(self, process_no):
        """Get the time_in for a specific process from manpower table"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            cursor.execute("SELECT time_in FROM manpower WHERE process_no = %s", (process_no,))
            row = cursor.fetchone()
            return row[0] if row and row[0] else None
        except Error as e:
            print(f"Error getting time_in: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_lineout_reasons(self):
        """Get all LINE OUT reasons"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id, reason FROM lineout_reasons ORDER BY id")
            return cursor.fetchall()
        except Error as e:
            print(f"Error fetching lineout reasons: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def add_lineout_reason(self, reason):
        """Add a custom LINE OUT reason (shared across all processes)"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            cursor.execute("INSERT IGNORE INTO lineout_reasons (reason) VALUES (%s)", (reason,))
            connection.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f"Error adding lineout reason: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def delete_lineout_reason(self, reason):
        """Delete a LINE OUT reason (shared across all processes)"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            cursor.execute("DELETE FROM lineout_reasons WHERE reason = %s", (reason,))
            connection.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f"Error deleting lineout reason: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_in_line_reasons(self):
        """Get all IN-LINE reasons"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id, reason FROM in_line_reasons ORDER BY id")
            return cursor.fetchall()
        except Error as e:
            print(f"Error fetching in_line reasons: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def add_in_line_reason(self, reason):
        """Add a custom IN-LINE reason (shared across all processes)"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            cursor.execute("INSERT IGNORE INTO in_line_reasons (reason) VALUES (%s)", (reason,))
            connection.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f"Error adding in_line reason: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def delete_in_line_reason(self, reason):
        """Delete an IN-LINE reason (shared across all processes)"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            cursor.execute("DELETE FROM in_line_reasons WHERE reason = %s", (reason,))
            connection.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f"Error deleting in_line reason: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_repaired_actions(self):
        """Get all REPAIRED ACTION reasons"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id, reason FROM repaired_actions ORDER BY id")
            return cursor.fetchall()
        except Error as e:
            print(f"Error fetching repaired actions: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def add_repaired_action(self, reason):
        """Add a custom REPAIRED ACTION reason (shared across all processes)"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            cursor.execute("INSERT IGNORE INTO repaired_actions (reason) VALUES (%s)", (reason,))
            connection.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f"Error adding repaired action: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def delete_repaired_action(self, reason):
        """Delete a REPAIRED ACTION reason (shared across all processes)"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            cursor.execute("DELETE FROM repaired_actions WHERE reason = %s", (reason,))
            connection.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f"Error deleting repaired action: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_cycle_graph_data(self):
        """Get average elapsed time per process for cycle graph monitoring"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # Get average elapsed_time per process (only records with valid elapsed_time)
            query = """
            SELECT process_no, 
                   AVG(TIME_TO_SEC(elapsed_time)) as avg_seconds,
                   COUNT(*) as record_count
            FROM process_records 
            WHERE elapsed_time IS NOT NULL 
              AND elapsed_time != '00:00:00'
            GROUP BY process_no 
            ORDER BY process_no
            """
            cursor.execute(query)
            records = cursor.fetchall()
            
            # Convert avg_seconds to M.SS format
            result = []
            for row in records:
                avg_sec = float(row['avg_seconds']) if row['avg_seconds'] else 0
                minutes = int(avg_sec // 60)
                secs = int(avg_sec % 60)
                m_ss_value = minutes + (secs / 100.0)  # M.SS format
                result.append({
                    'process_no': row['process_no'],
                    'avg_seconds': avg_sec,
                    'avg_mss': round(m_ss_value, 2),
                    'record_count': row['record_count']
                })
            
            return result
            
        except Error as e:
            print(f"Error fetching cycle graph data: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def get_line_trend_data(self, process_no, limit=10, after_timestamp=None):
        """Get individual elapsed time records for a process (for line trend graph)
        Only returns records from TODAY to ensure graph resets on new day.
        If after_timestamp is provided, only returns records after that time (for job order reset)."""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            if after_timestamp:
                query = """
                SELECT id, kitting_no, elapsed_time, TIME_TO_SEC(elapsed_time) as elapsed_seconds, timestamp
                FROM process_records 
                WHERE process_no = %s 
                  AND elapsed_time IS NOT NULL 
                  AND elapsed_time != '00:00:00'
                  AND DATE(timestamp) = CURDATE()
                  AND timestamp >= %s
                ORDER BY timestamp DESC 
                LIMIT %s
                """
                cursor.execute(query, (process_no, after_timestamp, limit))
            else:
                query = """
                SELECT id, kitting_no, elapsed_time, TIME_TO_SEC(elapsed_time) as elapsed_seconds, timestamp
                FROM process_records 
                WHERE process_no = %s 
                  AND elapsed_time IS NOT NULL 
                  AND elapsed_time != '00:00:00'
                  AND DATE(timestamp) = CURDATE()
                ORDER BY timestamp DESC 
                LIMIT %s
                """
                cursor.execute(query, (process_no, limit))
            records = cursor.fetchall()
            
            # Reverse so oldest is first (left-to-right on chart)
            records.reverse()
            
            # Convert to M.SS format
            result = []
            for row in records:
                elapsed_sec = float(row['elapsed_seconds']) if row['elapsed_seconds'] else 0
                minutes = int(elapsed_sec // 60)
                secs = int(elapsed_sec % 60)
                m_ss_value = minutes + (secs / 100.0)
                result.append({
                    'id': row['id'],
                    'kitting_no': row['kitting_no'] if row['kitting_no'] else '',
                    'elapsed_mss': round(m_ss_value, 2),
                    'elapsed_seconds': elapsed_sec,
                    'timestamp': row['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if row['timestamp'] else '',
                    'date': row['timestamp'].strftime('%Y-%m-%d') if row['timestamp'] else '',
                    'time': row['timestamp'].strftime('%H:%M:%S') if row['timestamp'] else ''
                })
            
            return result
            
        except Error as e:
            print(f"Error fetching line trend data: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def reset_records_only(self):
        """DISABLED - SQL records should NEVER be deleted.
        This function now does nothing to protect permanent data."""
        print("reset_records_only called but DISABLED - SQL records are permanent and will NOT be deleted")
        return True
    
    def reset_all_for_new_day(self):
        """Reset for new day: clear manpower only.
        SQL database records are NOT deleted - they are permanent historical data."""
        connection = None
        cursor = None
        try:
            print("reset_all_for_new_day: Starting manpower reset...")
            connection = self.get_connection()
            cursor = connection.cursor()
            
            # DO NOT delete process_records - this is permanent historical data
            # DO NOT delete process_1 to process_9 tables - this is permanent data
            
            # Only clear manpower data (operators must scan in each day)
            cursor.execute("""
                UPDATE manpower SET 
                    id_no = '', 
                    operator_name = '', 
                    employment_status = '', 
                    operator_manual = '', 
                    operator_scan = '',
                    time_in = NULL
                WHERE process_no BETWEEN 1 AND 9
            """)
            rows_affected = cursor.rowcount
            
            connection.commit()
            print(f"Daily reset: Cleared manpower for {rows_affected} processes (SQL records preserved)")
            return True
        except Error as e:
            print(f"Error in reset_all_for_new_day: {e}")
            import traceback
            traceback.print_exc()
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_manpower_by_process(self, process_no):
        """Get manpower for a specific process"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            query = "SELECT process_no, id_no, operator_name, employment_status, operator_manual, operator_scan FROM manpower WHERE process_no = %s"
            cursor.execute(query, (process_no,))
            result = cursor.fetchone()
            
            return result
            
        except Error as e:
            print(f"Error fetching manpower: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def has_records_today(self):
        """Check if any process records exist for today (any process 1-9)"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            
            query = """
                SELECT COUNT(*) FROM process_records 
                WHERE DATE(timestamp) = CURDATE()
            """
            cursor.execute(query)
            count = cursor.fetchone()[0]
            return count > 0
            
        except Error as e:
            print(f"Error checking today's records: {e}")
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def insert_material_setter(self, job_order, model_code, materials):
        """Insert or update material setter records into MATERIAL_SETTER table
        
        - id is AUTO_INCREMENT PRIMARY KEY (keeps incrementing for new job orders)
        - UNIQUE constraint on (job_order, row_no) ensures no duplicates
        - Same job order: UPDATE existing rows (id stays the same)
        - New job order: INSERT new rows (id increments)
        
        Args:
            job_order: Job order number
            model_code: Model code
            materials: List of dicts with row_no, kitting_mtls, mtrl_desc, material_code, scan_material, lot_no, qty
        """
        connection = None
        cursor = None
        try:
            # Create direct connection (bypass Tori mode check)
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True  # Auto-consume unread results
            )
            cursor = connection.cursor()
            
            # Create table if not exists (with UNIQUE constraint on job_order + row_no)
            # Use IF NOT EXISTS so it won't fail if table already exists
            create_table_query = """
            CREATE TABLE IF NOT EXISTS MATERIAL_SETTER (
                id INT AUTO_INCREMENT PRIMARY KEY,
                job_order VARCHAR(50),
                model_code VARCHAR(100),
                row_no INT,
                kitting_mtls VARCHAR(255),
                mtrl_desc VARCHAR(500),
                material_code VARCHAR(100),
                matl_qty VARCHAR(50),
                scan_material VARCHAR(100),
                lot_no VARCHAR(100),
                qty INT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_job_order (job_order),
                INDEX idx_timestamp (timestamp)
            )
            """
            cursor.execute(create_table_query)
            connection.commit()
            
            # Add matl_qty column if it doesn't exist (for existing tables)
            try:
                cursor.execute("ALTER TABLE MATERIAL_SETTER ADD COLUMN matl_qty VARCHAR(50) AFTER material_code")
                connection.commit()
            except:
                pass  # Column already exists
            
            # Try to add unique constraint if it doesn't exist (ignore error if already exists)
            try:
                cursor.execute("ALTER TABLE MATERIAL_SETTER ADD UNIQUE KEY uq_job_row (job_order, row_no)")
                connection.commit()
            except:
                pass  # Constraint already exists, ignore
            
            # Use INSERT ... ON DUPLICATE KEY UPDATE
            # - If (job_order, row_no) exists: UPDATE the row (id stays same)
            # - If (job_order, row_no) doesn't exist: INSERT new row (id auto-increments)
            upsert_query = """
            INSERT INTO MATERIAL_SETTER 
            (job_order, model_code, row_no, kitting_mtls, mtrl_desc, material_code, matl_qty, scan_material, lot_no, qty, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE
                job_order = VALUES(job_order),
                model_code = VALUES(model_code),
                kitting_mtls = VALUES(kitting_mtls),
                mtrl_desc = VALUES(mtrl_desc),
                material_code = VALUES(material_code),
                matl_qty = VALUES(matl_qty),
                scan_material = VALUES(scan_material),
                lot_no = VALUES(lot_no),
                qty = VALUES(qty),
                timestamp = NOW()
            """
            
            for material in materials:
                row_no = material.get('row_no', 0)
                record = (
                    job_order,
                    model_code,
                    row_no,
                    material.get('kitting_mtls', ''),
                    material.get('mtrl_desc', ''),
                    material.get('material_code', ''),
                    material.get('matl_qty', ''),
                    material.get('scan_material', ''),
                    material.get('lot_no', ''),
                    material.get('qty', 0)
                )
                cursor.execute(upsert_query, record)
            
            connection.commit()
            print(f"Saved {len(materials)} material setter records for job order: {job_order}")
            return True
            
        except Exception as e:
            print(f"Error inserting/updating material setter records: {e}")
            if connection:
                connection.rollback()
            raise e
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def clear_main_db_for_job_order(self, job_order):
        """Clear all MAIN_DB records for a specific job order"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            delete_query = "DELETE FROM MAIN_DB WHERE job_order = %s"
            cursor.execute(delete_query, (job_order,))
            connection.commit()
            deleted_count = cursor.rowcount
            print(f"Cleared {deleted_count} records from MAIN_DB for job order: {job_order}")
            return True
            
        except Exception as e:
            print(f"Error clearing MAIN_DB: {e}")
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def save_to_main_db(self, job_order, model_code, materials):
        """Save or update materials to MAIN_DB table
        
        Args:
            job_order: Job order number
            model_code: Model code
            materials: List of material dictionaries with row_no, material_description, 
                      qty_unit, scan_material, lot_no, lot_qty
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Insert new row or update existing
            # remaining_qty is updated from the UI (already deducted after kitting)
            # Set id = row_no to ensure sequential IDs from 1 to 25
            upsert_query = """
            INSERT INTO MAIN_DB 
            (id, job_order, model_code, row_no, material_description, qty_unit, scan_material, 
             lot_no, lot_qty, remaining_qty, date_today)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                id = VALUES(id),
                job_order = VALUES(job_order),
                model_code = VALUES(model_code),
                material_description = VALUES(material_description),
                qty_unit = VALUES(qty_unit),
                scan_material = VALUES(scan_material),
                lot_no = VALUES(lot_no),
                lot_qty = VALUES(lot_qty),
                remaining_qty = VALUES(remaining_qty),
                date_today = VALUES(date_today)
            """
            
            for material in materials:
                qty_unit = int(material.get('qty_unit', 0) or 0)
                # lot_qty from material data
                lot_qty = int(material.get('lot_qty', 0) or 0)
                # BUG FIX (Bug D): use explicit None check instead of `or qty_unit`
                # because 0 or qty_unit evaluates to qty_unit in Python (falsy-zero bug).
                # When remaining_qty is 0, it means the lot is fully consumed — save 0, not qty_unit.
                raw_rem = material.get('remaining_qty')
                remaining_qty = int(raw_rem) if raw_rem is not None and raw_rem != '' else qty_unit
                row_no = material.get('row_no', 0)
                
                record = (
                    row_no,  # id = row_no for sequential IDs 1-25
                    job_order,
                    model_code,
                    row_no,
                    material.get('material_description', ''),
                    qty_unit,
                    material.get('scan_material', ''),
                    material.get('lot_no', ''),
                    lot_qty,
                    remaining_qty,
                    today
                )
                cursor.execute(upsert_query, record)
            
            connection.commit()
            print(f"Saved {len(materials)} records to MAIN_DB for job order: {job_order}")
            return True
            
        except Exception as e:
            print(f"Error saving to MAIN_DB: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_main_db_data(self, job_order):
        """Get materials from MAIN_DB for a job order"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            
            query = """
            SELECT * FROM MAIN_DB 
            WHERE job_order = %s 
            ORDER BY row_no
            """
            cursor.execute(query, (job_order,))
            results = cursor.fetchall()
            return results
            
        except Exception as e:
            print(f"Error getting MAIN_DB data: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_all_main_db_data(self):
        """Get all materials from MAIN_DB (for Total Quantity Monitor auto-refresh)"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            
            query = """
            SELECT * FROM MAIN_DB 
            ORDER BY job_order, row_no
            """
            cursor.execute(query)
            results = cursor.fetchall()
            return results
            
        except Exception as e:
            print(f"Error getting all MAIN_DB data: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def save_to_kitting_db(self, kitting_no, job_order, model_code, materials, kitting_qr_code=''):
        """Save kitting completion records to KITTING_DB
        
        Args:
            kitting_no: Kitting number (1, 2, 3, etc.)
            job_order: Job order number
            model_code: Model code
            materials: List of material dictionaries
            kitting_qr_code: QR code data (DD/MM/YY-KITTING_NO JOB_ORDER)
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            insert_query = """
            INSERT INTO KITTING_DB 
            (kitting_no, job_order, model_code, row_no, material_description, qty_unit, 
             material_code_scanned, lot_number, quantity_kitting, date_today, kitting_qr_code)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            for material in materials:
                # quantity_kitting should equal qty_unit (per user requirement)
                qty_unit = int(material.get('qty_unit', 0) or 0)
                record = (
                    kitting_no,
                    job_order,
                    model_code,
                    material.get('row_no', 0),
                    material.get('material_description', ''),
                    qty_unit,  # qty_unit
                    material.get('scan_material', ''),
                    material.get('lot_no', ''),
                    qty_unit,  # quantity_kitting = qty_unit
                    today,
                    kitting_qr_code  # New: QR code data
                )
                cursor.execute(insert_query, record)
            
            connection.commit()
            print(f"Saved kitting {kitting_qr_code} with {len(materials)} records to KITTING_DB")
            return True
            
        except Exception as e:
            print(f"Error saving to KITTING_DB: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_kitting_db_data(self, job_order, today_only=True):
        """Get all kitting records from KITTING_DB for a job order
        
        If today_only=True, only returns records from today (for Total count reset on new day).
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            
            if today_only:
                # Get today's date
                today = datetime.now().strftime('%Y-%m-%d')
                query = """
                SELECT * FROM KITTING_DB 
                WHERE job_order = %s AND date_today = %s
                ORDER BY kitting_no, row_no
                """
                cursor.execute(query, (job_order, today))
                print(f"get_kitting_db_data: job_order={job_order}, today={today}")
            else:
                query = """
                SELECT * FROM KITTING_DB 
                WHERE job_order = %s 
                ORDER BY kitting_no, row_no
                """
                cursor.execute(query, (job_order,))
            results = cursor.fetchall()
            return results
            
        except Exception as e:
            print(f"Error getting KITTING_DB data: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_next_kitting_no(self, job_order):
        """Get the next kitting number - DAILY GLOBAL across ALL job orders.
        
        Kitting numbering is sequential for the entire day regardless of job order.
        If JO1 finishes at kitting 10, the next JO starts at kitting 11.
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            # DAILY GLOBAL: Get max kitting_no across ALL job orders for today
            # This ensures kitting continues sequentially regardless of JO changes
            query = """
            SELECT COALESCE(MAX(kitting_no), 0) + 1 as next_kitting_no 
            FROM KITTING_DB 
            WHERE DATE(timestamp) = CURDATE()
            """
            cursor.execute(query)
            print(f"get_next_kitting_no: DAILY GLOBAL (job_order={job_order})")
            result = cursor.fetchone()
            return result[0] if result else 1
            
        except Exception as e:
            print(f"Error getting next kitting number: {e}")
            return 1
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def has_kitting_records(self, job_order):
        """Check if a specific job order has any kitting records (for new JO detection)"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM KITTING_DB WHERE job_order = %s", (job_order,))
            result = cursor.fetchone()
            return result[0] > 0 if result else False
        except Exception as e:
            print(f"Error checking kitting records: {e}")
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def update_main_db_after_kitting(self, job_order, row_no, qty_used):
        """Update MAIN_DB after kitting completion
        
        remaining_qty = remaining_qty - qty_used (deduct from remaining)
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            # Update remaining_qty (subtract) - lot_qty stays unchanged
            update_query = """
            UPDATE MAIN_DB 
            SET remaining_qty = remaining_qty - %s
            WHERE job_order = %s AND row_no = %s
            """
            cursor.execute(update_query, (qty_used, job_order, row_no))
            connection.commit()
            print(f"Updated MAIN_DB row {row_no}: remaining_qty -{qty_used}")
            return True
            
        except Exception as e:
            print(f"Error updating MAIN_DB: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def fix_main_db_lot_qty(self, job_order):
        """Fix existing MAIN_DB data: set lot_qty from material data"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            # This function is kept for compatibility but lot_qty should be set from UI
            update_query = """
            UPDATE MAIN_DB 
            SET lot_qty = lot_qty
            WHERE job_order = %s
            """
            cursor.execute(update_query, (job_order,))
            affected_rows = cursor.rowcount
            connection.commit()
            print(f"Fixed MAIN_DB for job order {job_order}: {affected_rows} rows updated")
            return affected_rows
            
        except Exception as e:
            print(f"Error fixing MAIN_DB: {e}")
            if connection:
                connection.rollback()
            return 0
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def save_kitting_summary(self, job_order, model_code, summary_rows):
        """Save kitting summary data to kitting_summary table (upsert - insert or update)
        This mirrors the KITTING SUMMARY display in the browser
        
        Args:
            job_order: Job order number
            model_code: Model code
            summary_rows: List of dicts with row_no, material_description, qty_unit, scan_material, lot_no, qty_kit
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Upsert query - insert or update existing row
            upsert_query = """
            INSERT INTO kitting_summary 
            (job_order, model_code, row_no, material_description, qty_unit, scan_material, lot_no, qty_kit, date_today)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                job_order = VALUES(job_order),
                model_code = VALUES(model_code),
                material_description = VALUES(material_description),
                qty_unit = VALUES(qty_unit),
                scan_material = VALUES(scan_material),
                lot_no = VALUES(lot_no),
                qty_kit = VALUES(qty_kit),
                date_today = VALUES(date_today)
            """
            
            for row in summary_rows:
                row_no = row.get('row_no', 0)
                if row_no == 0:
                    continue
                values = (
                    job_order,
                    model_code,
                    row_no,
                    row.get('material_description', '') or row.get('mtrl_desc', ''),
                    int(row.get('qty_unit', 0) or 0),
                    row.get('scan_material', '') or row.get('scan_mtrl', ''),
                    row.get('lot_no', ''),
                    int(row.get('qty_kit', 0) or 0),
                    today
                )
                cursor.execute(upsert_query, values)
            
            connection.commit()
            print(f"Saved {len(summary_rows)} rows to kitting_summary for job order {job_order}")
            return True
            
        except Exception as e:
            print(f"Error saving kitting summary: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_all_kitting_summary(self):
        """Get all kitting summary data (no filter) - used to check if table has data
        
        Returns:
            List with count if data exists, empty list otherwise
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            
            query = "SELECT COUNT(*) as count FROM kitting_summary"
            cursor.execute(query)
            result = cursor.fetchone()
            return [result] if result and result['count'] > 0 else []
            
        except Exception as e:
            print(f"Error getting all kitting summary: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_kitting_summary(self, job_order):
        """Get kitting summary data for a job order
        
        Args:
            job_order: Job order number
            
        Returns:
            List of kitting summary records ordered by row_no
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            
            query = """
            SELECT row_no, material_description, qty_unit, scan_material, lot_no, qty_kit 
            FROM kitting_summary 
            WHERE job_order = %s
            ORDER BY row_no ASC
            """
            cursor.execute(query, (job_order,))
            results = cursor.fetchall()
            return results
            
        except Exception as e:
            print(f"Error getting kitting summary: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def clear_kitting_summary(self, job_order):
        """Clear kitting summary data for a job order
        
        Args:
            job_order: Job order number
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            cursor.execute("DELETE FROM kitting_summary WHERE job_order = %s", (job_order,))
            connection.commit()
            print(f"Cleared kitting_summary for job order {job_order}")
            return True
            
        except Exception as e:
            print(f"Error clearing kitting summary: {e}")
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_latest_kitting_summary(self, job_order):
        """Get the latest kitting summary for a job order (most recent kitting_no)
        
        Args:
            job_order: Job order number
            
        Returns:
            List of kitting summary records for the latest kitting
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            
            # First get the latest kitting_no
            query_max = """
            SELECT MAX(kitting_no) as max_kitting FROM kitting_summary 
            WHERE job_order = %s
            """
            cursor.execute(query_max, (job_order,))
            result = cursor.fetchone()
            
            if not result or result['max_kitting'] is None:
                return []
            
            max_kitting = result['max_kitting']
            
            # Get all rows for the latest kitting
            query = """
            SELECT * FROM kitting_summary 
            WHERE job_order = %s AND kitting_no = %s
            ORDER BY row_no ASC
            """
            cursor.execute(query, (job_order, max_kitting))
            results = cursor.fetchall()
            return results
            
        except Exception as e:
            print(f"Error getting latest kitting summary: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    def save_to_material_tables(self, kitting_no, job_order, model_code, materials, kitting_qr_code, material_lots=None):
        """Save each material row to its designated table after QR code scan
        
        Args:
            kitting_no: Kitting number
            job_order: Job order number
            model_code: Model code
            materials: List of dicts with row_no, mtrl_desc, qty_unit, scan_mtrl, lot_no, qty_kit
            kitting_qr_code: QR code data
            material_lots: Optional dict { "<row_no>": [ {scan_material, lot_no, qty_kit}, ... ] }.
                IMAGE 7: when a row was problematic, store ONE table row per scanned lot
                (old lot + every inserted new lot) instead of just the single collapsed row.
                The per-lot qty_kit is written to the qty_unit column to mirror the spec.
        """
        if material_lots is None:
            material_lots = {}
        # Map row_no to table name
        row_to_table = {
            1: '01tbl_frame_zam',
            2: '02tbl_frame_lead',
            3: '03tbl_spacer',
            4: '04tbl_2p',
            5: '05tbl_p3p',
            6: '06tbl_df_block',
            7: '07tbl_rod',
            8: '08tbl_casing_block',
            9: '09tbl_partition_board',
            10: '10tbl_l_tube',
            11: '11tbl_hose_clip',
            12: '12tbl_switch_block',
            13: '13tbl_lead_bushing',
            14: '14tbl_ground_wire',
            15: '15tbl_vcr',
            16: '16tbl_lower_housing',
            17: '17tbl_rubber_foot',
            18: '18tbl_power_cord',
            19: '19tbl_partition_gasket',
            20: '20tbl_upper_housing',
            21: '21tbl_filter_cover',
            22: '22tbl_filter',
            23: '23tbl_sound_absorbing',
            24: '24tbl_manual',
            25: '25tbl_l_hose_set',
            26: '26tbl_filter_bush'
        }
        
        connection = None
        cursor = None
        print(f"[save_to_material_tables] Called with kitting_no={kitting_no}, job_order={job_order}, materials count={len(materials)}, material_lots keys={list(material_lots.keys()) if material_lots else 'None'}")
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            total_inserted = 0
            for material in materials:
                row_no = material.get('row_no', 0)
                table_name = row_to_table.get(row_no)
                
                if not table_name:
                    print(f"[save_to_material_tables] No table mapping for row_no {row_no}")
                    continue
                print(f"[save_to_material_tables] Processing row {row_no} -> {table_name}")
                
                # SS3/SS4/SS5: INSERT with both qty_unit (original 6) and qty_kit (per-lot 2, 4)
                insert_query = f"""
                INSERT INTO {table_name} 
                (kitting_no, job_order, model_code, mtrl_desc, qty_unit, scan_mtrl, lot_no, qty_kit, kitting_qr_code, date_today)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                mtrl_desc = material.get('material_description', '') or material.get('mtrl_desc', '')
                # SS3/SS4: qty_unit is the ORIGINAL QTY/UNIT value (e.g., 6), NOT the per-lot qty_kit
                original_qty_unit = int(material.get('qty_unit', 0) or 0)
                
                # IMAGE 7: if this row was problematic, expand it into one row per scanned lot.
                # material_lots keys may be int or str (JSON object keys are strings).
                lots = material_lots.get(str(row_no)) or material_lots.get(row_no)
                
                if lots:
                    for lot in lots:
                        # SS3/SS4: qty_unit stays as original (6), qty_kit is the per-lot value (2, 4)
                        per_lot_qty_kit = int(lot.get('qty_kit', 0) or 0)
                        values = (
                            kitting_no,
                            job_order,
                            model_code,
                            mtrl_desc,
                            original_qty_unit,  # SS3/SS4: qty_unit = original QTY/UNIT (6)
                            lot.get('scan_material', '') or lot.get('scan_mtrl', ''),
                            lot.get('lot_no', ''),
                            per_lot_qty_kit,    # SS5: qty_kit = per-lot QTY/KIT from Kitting Summary (2, 4)
                            kitting_qr_code,
                            today
                        )
                        cursor.execute(insert_query, values)
                        total_inserted += 1
                else:
                    # Normal row (not problematic): qty_kit equals qty_unit
                    values = (
                        kitting_no,
                        job_order,
                        model_code,
                        mtrl_desc,
                        original_qty_unit,
                        material.get('scan_material', '') or material.get('scan_mtrl', ''),
                        material.get('lot_no', ''),
                        original_qty_unit,  # For normal rows, qty_kit = qty_unit
                        kitting_qr_code,
                        today
                    )
                    cursor.execute(insert_query, values)
                    total_inserted += 1
            
            connection.commit()
            print(f"Saved {total_inserted} material rows to their respective tables for kitting #{kitting_no}")
            return True
            
        except Exception as e:
            print(f"Error saving to material tables: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def save_joborder_plan(self, job_order, suffix, model_code, kitting_qr_code, plan_qty, operator_name='', time_in=None):
        """Save or update joborder_plan record when a kitting QR code is scanned
        
        Logic:
        - If first kitting for this job_order: result=1, balance=plan-1
        - If subsequent kitting: result increments, balance decrements
        - kitting_qr_code format: DDMMYY-XXXX JOB_ORDER (slash removed from date)
        - Automatically fetches operator_name from mtrl_set_operator table
        
        Args:
            job_order: Job order number (e.g., 3J73802302)
            suffix: Suffix in 4 digits (e.g., 0001)
            model_code: Model code (e.g., 80HP20760P)
            kitting_qr_code: QR code with date format DDMMYY-XXXX JOB_ORDER (no slash)
            plan_qty: The plan quantity (total quantity to produce)
            operator_name: (deprecated - auto-fetched from mtrl_set_operator)
            time_in: (deprecated - auto-fetched from mtrl_set_operator)
        """
        # Auto-fetch operator info from mtrl_set_operator table
        ms_operator_name, ms_time_in = self.get_mtrl_set_operator_name()
        if ms_operator_name:
            operator_name = ms_operator_name
            time_in = ms_time_in
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Get current max row_no for this job_order to determine next row
            cursor.execute("""
                SELECT COALESCE(MAX(row_no), 0) as max_row, 
                       COALESCE(MAX(result), 0) as max_result
                FROM joborder_plan 
                WHERE job_order = %s
            """, (job_order,))
            result = cursor.fetchone()
            
            next_row_no = (result['max_row'] or 0) + 1
            next_result = (result['max_result'] or 0) + 1
            balance = int(plan_qty) - next_result
            
            # Insert new record with operator info
            insert_query = """
            INSERT INTO joborder_plan 
            (job_order, operator_name, time_in, suffix, model_code, row_no, kitting_qr_code, plan, result, balance, date_today)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            cursor.execute(insert_query, (
                job_order,
                operator_name or '',
                time_in,
                suffix,
                model_code,
                next_row_no,
                kitting_qr_code,
                int(plan_qty),
                next_result,
                balance,
                today
            ))
            
            connection.commit()
            print(f"Saved joborder_plan: job_order={job_order}, row_no={next_row_no}, result={next_result}, balance={balance}")
            return {
                'success': True,
                'row_no': next_row_no,
                'result': next_result,
                'balance': balance
            }
            
        except Exception as e:
            print(f"Error saving joborder_plan: {e}")
            if connection:
                connection.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_joborder_plan(self, job_order):
        """Get all joborder_plan records for a job order
        
        Args:
            job_order: Job order number
            
        Returns:
            List of joborder_plan records ordered by row_no
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            
            query = """
            SELECT id, job_order, suffix, model_code, row_no, kitting_qr_code, plan, result, balance, date_today, timestamp
            FROM joborder_plan 
            WHERE job_order = %s
            ORDER BY row_no ASC
            """
            cursor.execute(query, (job_order,))
            results = cursor.fetchall()
            return results
            
        except Exception as e:
            print(f"Error getting joborder_plan: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_joborder_plan_latest(self, job_order):
        """Get the latest joborder_plan record for a job order
        
        Args:
            job_order: Job order number
            
        Returns:
            Latest joborder_plan record or None
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            
            query = """
            SELECT id, job_order, suffix, model_code, row_no, kitting_qr_code, plan, result, balance, date_today, timestamp
            FROM joborder_plan 
            WHERE job_order = %s
            ORDER BY row_no DESC
            LIMIT 1
            """
            cursor.execute(query, (job_order,))
            result = cursor.fetchone()
            return result
            
        except Exception as e:
            print(f"Error getting latest joborder_plan: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def clear_joborder_plan(self, job_order):
        """Clear all joborder_plan records for a job order
        
        Args:
            job_order: Job order number
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            cursor.execute("DELETE FROM joborder_plan WHERE job_order = %s", (job_order,))
            connection.commit()
            print(f"Cleared joborder_plan for job order {job_order}")
            return True
            
        except Exception as e:
            print(f"Error clearing joborder_plan: {e}")
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_ms_operator(self):
        """Get current Material Setter operator from mtrl_set_operator table.
        Returns the operator if time_in is today. If time_in is from a previous day,
        returns expired=True for daily auto-logout.
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            cursor.execute("SELECT * FROM mtrl_set_operator WHERE id = 1")
            result = cursor.fetchone()
            
            if not result or not result.get('operator_name'):
                return {'operator': None, 'expired': False}
            
            # Check if time_in is from today (daily auto-logout)
            time_in = result.get('time_in')
            if time_in:
                time_in_date = time_in.strftime('%Y-%m-%d') if hasattr(time_in, 'strftime') else str(time_in)[:10]
                if time_in_date != today:
                    # Auto-clear the operator for new day
                    self.clear_mtrl_set_operator()
                    return {'operator': None, 'expired': True, 'last_operator': result['operator_name']}
            
            return {
                'operator': result['operator_name'],
                'time_in': str(result['time_in']) if result['time_in'] else None,
                'expired': False
            }
            
        except Exception as e:
            print(f"Error getting MS operator: {e}")
            return {'operator': None, 'expired': False, 'error': str(e)}
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def set_ms_operator_in(self, operator_name):
        """Set Material Setter operator IN - updates mtrl_set_operator table.
        Parses scan format: 'ID_NO , NAME , STATUS' and stores in single row.
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            
            now = datetime.now()
            
            # Parse operator_name (scan format: "ID_NO , NAME , STATUS")
            id_no = ''
            name = ''
            employment_status = ''
            scan_val = operator_name or ''
            if scan_val:
                parts = scan_val.split(' , ')
                if len(parts) >= 3:
                    id_no = parts[0].strip()
                    name = parts[1].strip()
                    employment_status = parts[2].strip()
                elif len(parts) == 2:
                    id_no = parts[0].strip()
                    name = parts[1].strip()
                elif len(parts) == 1:
                    name = parts[0].strip()
            
            cursor.execute("""
                UPDATE mtrl_set_operator 
                SET id_no = %s, operator_name = %s, employment_status = %s,
                    operator_scan = %s, time_in = %s
                WHERE id = 1
            """, (id_no, name, employment_status, scan_val, now))
            
            connection.commit()
            print(f"MS Operator IN: {name} (id_no={id_no}) at {now}")
            return {'success': True, 'time_in': str(now)}
            
        except Exception as e:
            print(f"Error setting MS operator IN: {e}")
            if connection:
                connection.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def set_ms_operator_out(self, out_reasons=''):
        """Set Material Setter operator OUT - clears mtrl_set_operator table."""
        self.clear_mtrl_set_operator()
        print(f"MS Operator OUT, reason: {out_reasons}")
        return {'success': True}

    def get_mtrl_set_operator(self):
        """Get the mtrl_set_operator record (single row)."""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM mtrl_set_operator WHERE id = 1")
            result = cursor.fetchone()
            if result:
                # Convert datetime fields to string for JSON
                if result.get('time_in'):
                    result['time_in'] = str(result['time_in'])
                if result.get('created_at'):
                    result['created_at'] = str(result['created_at'])
                if result.get('updated_at'):
                    result['updated_at'] = str(result['updated_at'])
            return result or {}
        except Exception as e:
            print(f"Error getting mtrl_set_operator: {e}")
            return {}
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def update_mtrl_set_operator(self, operator_manual=None, operator_scan=None):
        """Update mtrl_set_operator with manual or scan input."""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            
            # Parse operator_scan to extract id_no, operator_name, employment_status
            id_no = ''
            operator_name = ''
            employment_status = ''
            scan_val = operator_scan or ''
            if scan_val:
                parts = scan_val.split(' , ')
                if len(parts) >= 3:
                    id_no = parts[0].strip()
                    operator_name = parts[1].strip()
                    employment_status = parts[2].strip()
                elif len(parts) == 2:
                    id_no = parts[0].strip()
                    operator_name = parts[1].strip()
                elif len(parts) == 1:
                    id_no = parts[0].strip()
            
            now = datetime.now()
            
            cursor.execute("""
                UPDATE mtrl_set_operator 
                SET id_no = %s, operator_name = %s, employment_status = %s,
                    operator_manual = %s, operator_scan = %s, time_in = %s
                WHERE id = 1
            """, (id_no, operator_name, employment_status, operator_manual or '', scan_val, now))
            connection.commit()
            
            return cursor.rowcount > 0
            
        except Exception as e:
            print(f"Error updating mtrl_set_operator: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def clear_mtrl_set_operator(self):
        """Clear mtrl_set_operator data (Manual Reset)."""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor()
            cursor.execute("""
                UPDATE mtrl_set_operator 
                SET id_no = '', operator_name = '', employment_status = '',
                    operator_manual = '', operator_scan = '', time_in = NULL
                WHERE id = 1
            """)
            connection.commit()
            return True
        except Exception as e:
            print(f"Error clearing mtrl_set_operator: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_mtrl_set_operator_name(self):
        """Get just the operator_name from mtrl_set_operator (for kitting saves)."""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT operator_name, time_in FROM mtrl_set_operator WHERE id = 1")
            result = cursor.fetchone()
            if result:
                return result.get('operator_name', ''), result.get('time_in')
            return '', None
        except Exception as e:
            print(f"Error getting mtrl_set_operator_name: {e}")
            return '', None
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def reset_kitting_summary_ids(self):
        """Reset kitting_summary table with sequential IDs matching row_no order.
        This fixes gaps in the AUTO_INCREMENT id column by:
        1. Backing up all data
        2. Truncating the table (resets AUTO_INCREMENT)
        3. Re-inserting all rows ordered by job_order and row_no
        
        Returns:
            True if successful, False otherwise
        """
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database_name,
                consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            
            # Step 1: Backup all data ordered by job_order and row_no
            cursor.execute("""
                SELECT job_order, model_code, row_no, material_description, 
                       qty_unit, scan_material, lot_no, qty_kit, date_today, timestamp
                FROM kitting_summary 
                ORDER BY job_order, row_no ASC
            """)
            backup_data = cursor.fetchall()
            
            if not backup_data:
                print("No data in kitting_summary to reset")
                return True
            
            print(f"Backed up {len(backup_data)} rows from kitting_summary")
            
            # Step 2: Truncate table (resets AUTO_INCREMENT to 1)
            cursor.execute("TRUNCATE TABLE kitting_summary")
            print("Truncated kitting_summary table")
            
            # Step 3: Re-insert all rows (will get sequential IDs 1, 2, 3, ...)
            insert_query = """
                INSERT INTO kitting_summary 
                (job_order, model_code, row_no, material_description, 
                 qty_unit, scan_material, lot_no, qty_kit, date_today, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            for row in backup_data:
                values = (
                    row['job_order'],
                    row['model_code'],
                    row['row_no'],
                    row['material_description'],
                    row['qty_unit'],
                    row['scan_material'],
                    row['lot_no'],
                    row['qty_kit'],
                    row['date_today'],
                    row['timestamp']
                )
                cursor.execute(insert_query, values)
            
            connection.commit()
            print(f"Re-inserted {len(backup_data)} rows with sequential IDs")
            return True
            
        except Exception as e:
            print(f"Error resetting kitting_summary IDs: {e}")
            if connection:
                connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def run_functional_test(self, test_id, **kwargs):
        """Run a functional self-test and return {passed: bool, detail: str}"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)

            if test_id == 'problematic_row_insert':
                test_jo = '__SELFTEST__'
                cursor.execute("""
                    INSERT INTO kitting_summary (job_order, model_code, row_no, material_description, qty_unit, scan_material, lot_no, qty_kit, date_today)
                    VALUES (%s, 'TEST_MODEL', 99, 'SELF_TEST_ROW', 1, 'TEST_SCAN', 'TEST_LOT', 0, CURDATE())
                """, (test_jo,))
                connection.commit()
                cursor.execute("SELECT COUNT(*) as cnt FROM kitting_summary WHERE job_order = %s AND row_no = 99", (test_jo,))
                row = cursor.fetchone()
                found = row and row['cnt'] > 0
                cursor.execute("DELETE FROM kitting_summary WHERE job_order = %s", (test_jo,))
                connection.commit()
                return {'passed': found, 'detail': 'Insert test row into kitting_summary: ' + ('OK - inserted and cleaned up' if found else 'FAILED')}

            elif test_id == 'track_last_kitting':
                test_jo = '__SELFTEST__'
                cursor.execute("INSERT INTO KITTING_DB (kitting_no, job_order, model_code, row_no, date_today) VALUES (1, %s, 'TEST', 1, CURDATE())", (test_jo,))
                cursor.execute("INSERT INTO KITTING_DB (kitting_no, job_order, model_code, row_no, date_today) VALUES (2, %s, 'TEST', 1, CURDATE())", (test_jo,))
                connection.commit()
                cursor.execute("SELECT COALESCE(MAX(kitting_no), 0) + 1 as next_no FROM KITTING_DB WHERE job_order = %s", (test_jo,))
                row = cursor.fetchone()
                next_no = row['next_no'] if row else 0
                passed = (next_no == 3)
                cursor.execute("DELETE FROM KITTING_DB WHERE job_order = %s", (test_jo,))
                connection.commit()
                return {'passed': passed, 'detail': f'Next kitting no after 2 inserts: {next_no} (expected 3)'}

            elif test_id == 'read_suffix':
                cursor.execute("SHOW COLUMNS FROM joborder_plan LIKE 'suffix'")
                row = cursor.fetchone()
                has_suffix = row is not None
                return {'passed': has_suffix, 'detail': 'joborder_plan table has suffix column: ' + ('YES' if has_suffix else 'NO')}

            elif test_id == 'read_jo_qty':
                cursor.execute("SHOW COLUMNS FROM joborder_plan LIKE 'plan'")
                row = cursor.fetchone()
                has_plan = row is not None
                return {'passed': has_plan, 'detail': 'joborder_plan table has plan (qty) column: ' + ('YES' if has_plan else 'NO')}

            elif test_id == 'one_time_scan':
                test_jo = '__SELFTEST__'
                cursor.execute("INSERT INTO joborder_plan (job_order, suffix, model_code, row_no, plan, result, balance, date_today) VALUES (%s, '0001', 'TEST', 1, 10, 0, 10, CURDATE())", (test_jo,))
                cursor.execute("INSERT INTO joborder_plan (job_order, suffix, model_code, row_no, plan, result, balance, date_today) VALUES (%s, '0001', 'TEST', 1, 10, 0, 10, CURDATE())", (test_jo,))
                connection.commit()
                cursor.execute("SELECT COUNT(*) as cnt FROM joborder_plan WHERE job_order = %s", (test_jo,))
                row = cursor.fetchone()
                count = row['cnt'] if row else 0
                cursor.execute("DELETE FROM joborder_plan WHERE job_order = %s", (test_jo,))
                connection.commit()
                return {'passed': count == 2, 'detail': f'Inserted 2 records, found {count}. DB accepts inserts correctly.'}

            elif test_id == 'suffix_both':
                cursor.execute("SELECT COUNT(*) as cnt FROM kitting_summary")
                ks = cursor.fetchone()
                cursor.execute("SELECT COUNT(*) as cnt FROM KITTING_DB")
                kd = cursor.fetchone()
                ks_cnt = ks['cnt'] if ks else -1
                kd_cnt = kd['cnt'] if kd else -1
                return {'passed': ks_cnt >= 0 and kd_cnt >= 0, 'detail': f'kitting_summary: {ks_cnt} rows, KITTING_DB: {kd_cnt} rows - both accessible'}

            elif test_id == 'operator_persist':
                cursor.execute("SELECT COUNT(*) as cnt FROM manpower WHERE operator_scan != '' OR operator_manual != ''")
                row = cursor.fetchone()
                count = row['cnt'] if row else 0
                return {'passed': True, 'detail': f'Manpower table has {count} operators logged. Data persists until daily reset.'}

            elif test_id == 'custom':
                tables = kwargs.get('tables', '')
                action = kwargs.get('action', 'SELECT')
                test_jo = kwargs.get('test_jo', '')
                table_list = [t.strip() for t in tables.split(',') if t.strip()]
                if not table_list:
                    return {'passed': False, 'detail': 'No target tables specified'}
                results = []
                all_ok = True
                for table in table_list:
                    try:
                        if action == 'SELECT':
                            cursor.execute(f"SELECT COUNT(*) as cnt FROM `{table}`")
                            row = cursor.fetchone()
                            cnt = row['cnt'] if row else 0
                            results.append(f"{table}: {cnt} rows")
                        elif action == 'INSERT':
                            if test_jo:
                                cursor.execute(f"SELECT COUNT(*) as cnt FROM `{table}` WHERE job_order = %s", (test_jo,))
                                row = cursor.fetchone()
                                cnt = row['cnt'] if row else 0
                                results.append(f"{table}: {cnt} rows for JO {test_jo}")
                            else:
                                cursor.execute(f"SELECT COUNT(*) as cnt FROM `{table}`")
                                row = cursor.fetchone()
                                cnt = row['cnt'] if row else 0
                                results.append(f"{table}: {cnt} rows total")
                        elif action == 'VERIFY':
                            cursor.execute(f"SHOW TABLES LIKE '{table}'")
                            exists = cursor.fetchone() is not None
                            results.append(f"{table}: {'EXISTS' if exists else 'NOT FOUND'}")
                            if not exists:
                                all_ok = False
                    except Exception as te:
                        results.append(f"{table}: ERROR - {str(te)}")
                        all_ok = False
                return {'passed': all_ok, 'detail': ' | '.join(results)}

            return {'passed': False, 'detail': f'Unknown test_id: {test_id}'}

        except Exception as e:
            return {'passed': False, 'detail': f'Test error: {str(e)}'}
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    # ==================== CHANGE MODEL (Material Setter) ====================
    
    def get_change_model_reasons(self):
        """Get all CHANGE MODEL reasons from ms_change_model_reasons table"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host, port=self.port,
                user=self.user, password=self.password,
                database=self.database_name, consume_results=True
            )
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id, reason FROM ms_change_model_reasons ORDER BY id")
            return cursor.fetchall()
        except Exception as e:
            print(f"Error fetching change model reasons: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if connection: connection.close()

    def add_change_model_reason(self, reason):
        """Add a custom CHANGE MODEL reason"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host, port=self.port,
                user=self.user, password=self.password,
                database=self.database_name, consume_results=True
            )
            cursor = connection.cursor()
            cursor.execute("INSERT IGNORE INTO ms_change_model_reasons (reason) VALUES (%s)", (reason.upper(),))
            connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error adding change model reason: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if connection: connection.close()

    def delete_change_model_reason(self, reason):
        """Delete a CHANGE MODEL reason"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host, port=self.port,
                user=self.user, password=self.password,
                database=self.database_name, consume_results=True
            )
            cursor = connection.cursor()
            cursor.execute("DELETE FROM ms_change_model_reasons WHERE reason = %s", (reason,))
            connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error deleting change model reason: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if connection: connection.close()

    def save_change_model_event(self, job_order, reason):
        """Save change_model_reason to joborder_plan for the given job order"""
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host=self.host, port=self.port,
                user=self.user, password=self.password,
                database=self.database_name, consume_results=True
            )
            cursor = connection.cursor()
            cursor.execute("""
                UPDATE joborder_plan SET change_model_reason = %s 
                WHERE job_order = %s AND row_no = (SELECT max_row FROM (SELECT MAX(row_no) as max_row FROM joborder_plan WHERE job_order = %s) as temp)
            """, (reason, job_order, job_order))
            connection.commit()
            print(f"Change model reason saved to joborder_plan: JO={job_order}, reason={reason}")
            return True
        except Exception as e:
            print(f"Error saving change model reason: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if connection: connection.close()

