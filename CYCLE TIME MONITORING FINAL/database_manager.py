import mysql.connector
from mysql.connector import Error
from datetime import datetime

class DatabaseManager:
    def __init__(self):
        self.host = "localhost"
        self.port = 3306
        self.user = "root"
        self.password = ""  # Default XAMPP password is empty
        self.database_name = "cycle_time_monitoring"
        self.connection = None
        
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
        """Create a fresh database connection for each operation"""
        return mysql.connector.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database_name
        )
    
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
    
    def get_all_standard_times(self):
        """Get all standard times"""
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
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
            connection = self.get_connection()
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
            connection = self.get_connection()
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
            connection = self.get_connection()
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
            connection = self.get_connection()
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
            connection = self.get_connection()
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
            connection = self.get_connection()
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
            connection = self.get_connection()
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
            connection = self.get_connection()
            cursor = connection.cursor()
            cursor.execute("INSERT IGNORE INTO bio_break (out_reasons) VALUES (%s)", (reason,))
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
            connection = self.get_connection()
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
