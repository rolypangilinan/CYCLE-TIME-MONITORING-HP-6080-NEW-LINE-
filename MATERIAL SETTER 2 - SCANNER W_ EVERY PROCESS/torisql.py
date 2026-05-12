#%%
import glob
import pyodbc
import pandas as pd
import os
from datetime import datetime
# import pandas as pd



isToriMode = False

conn = None
cursor = None

def setToriMode(mode):
    """Set isToriMode to True (block local DB) or False (unblock local DB)"""
    global isToriMode
    isToriMode = mode
    print(f"isToriMode set to: {mode}")

def connect():
    global conn
    global cursor

    conn = pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=sqldb.hiblow.local;"   # or IP
        "DATABASE=MesDB;"
        "UID=MES_USER;"
        "PWD=hp!M3s#USR;"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )

    cursor = conn.cursor()
    
    print("Connected!")

def getJobOrderMaterials(job_order=None):
    global cursor
    global isToriMode

    if job_order is None:
        job_order = '3J73802302'  # Default for testing
    
    # Ensure job_order is exactly 10 characters (truncate if longer)
    job_order = str(job_order)[:10]

    pd.set_option('display.max_columns', None)


    cursor.execute("""
    select *
    From test.test_v_JobMat_mst BOM
    WHERE 
        BOM.job =?
        and
        BOM.suffix ='1'
    Order BY 
        BOM.oper_num,
        BOM.sequence
    """, (job_order,))

    # for row in connection.cursor.fetchall():
    #     print(row)

    rows = cursor.fetchall()
    columns = [col[0] for col in cursor.description]  # column names
 
    df = pd.DataFrame.from_records(rows, columns=columns)
    print("Dataframe Successful")
    isToriMode = False
    return df
#%%
def preprocess_dataframe(df, options=None):
    """Preprocess DataFrame before CSV export"""
    if df is None or len(df) == 0:
        return df
    
    if options is None:
        options = {}
    
    # Create a copy to avoid modifying original
    df_processed = df.copy()
    
    # Handle null values
    if options.get('replace_nulls', True):
        null_replacement = options.get('null_replacement', '')
        df_processed = df_processed.fillna(null_replacement)
    
    # Trim string columns (only actual string columns, not Decimal or other objects)
    if options.get('trim_strings', True):
        for col in df_processed.columns:
            if df_processed[col].dtype == 'object':
                # Only apply strip to columns where first non-null value is a string
                first_valid = df_processed[col].dropna().head(1)
                if len(first_valid) > 0 and isinstance(first_valid.iloc[0], str):
                    df_processed[col] = df_processed[col].apply(
                        lambda x: x.strip() if isinstance(x, str) else x
                    )
    
    # Format datetime columns
    if options.get('format_dates', True):
        date_format = options.get('date_format', '%Y-%m-%d %H:%M:%S')
        datetime_columns = df_processed.select_dtypes(include=['datetime64']).columns
        for col in datetime_columns:
            df_processed[col] = df_processed[col].dt.strftime(date_format)
    
    return df_processed

def export_to_csv(df, filename=None, options=None):
    """
    Enhanced CSV export function with configurable options
    
    Args:
        df: DataFrame to export
        filename: Custom filename (without extension)
        options: Dictionary of export options
    
    Returns:
        dict: Export result with file path and metadata
    """
    if df is None or len(df) == 0:
        return {"success": False, "error": "No data to export"}
    
    if options is None:
        options = {}
    
    # Get base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Generate filename if not provided
    if filename is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        job_order = options.get('job_order', 'unknown')
        filename = f"torisql_materials_{job_order}_{timestamp}"
    
    # Ensure .csv extension
    if not filename.endswith('.csv'):
        filename += '.csv'
    
    # Full file path
    csv_path = os.path.join(base_dir, filename)
    
    # Preprocess data
    df_processed = preprocess_dataframe(df, options)
    
    # Export options
    export_params = {
        'index': options.get('include_index', False),
        'encoding': options.get('encoding', 'utf-8-sig'),  # utf-8-sig for Excel compatibility
    }
    
    # Add metadata header if requested
    if options.get('include_metadata', True):
        metadata_lines = []
        metadata_lines.append(f"# Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        metadata_lines.append(f"# Job Order: {options.get('job_order', 'N/A')}")
        metadata_lines.append(f"# Record Count: {len(df_processed)}")
        metadata_lines.append(f"# Source: test.test_v_JobMat_mst")
        metadata_lines.append("")
        
        # Write metadata first
        with open(csv_path, 'w', encoding='utf-8-sig') as f:
            f.write('\n'.join(metadata_lines))
        
        # Append data
        df_processed.to_csv(csv_path, mode='a', **export_params)
    else:
        # Direct export
        df_processed.to_csv(csv_path, **export_params)
    
    return {
        "success": True,
        "file_path": csv_path,
        "filename": filename,
        "record_count": len(df_processed),
        "export_time": datetime.now().isoformat()
    }

# connect()                   #THIS SHOULD BE COMMENT WHEN SCANNING JOB ORDER
# getJobOrderMaterials()      #THIS SHOULD BE COMMENT WHEN SCANNING JOB ORDER

if __name__ == "__main__":
    connect()
    scanned_job = input("Scan or enter Job Order: ").strip()
    if scanned_job:
        df = getJobOrderMaterials(scanned_job)
        print(df)
    else:
        print("No job order entered.")