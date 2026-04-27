import glob
import pyodbc
import pandas as pd

isToriMode = True

conn = None
cursor = None

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

def getJobOrderMaterials():
    global cursor
    global isToriMode


    cursor.execute("""
    select *
    From test.test_v_JobMat_mst BOM
    WHERE 
        BOM.job ='3J73802302'
        and
        BOM.suffix ='1'
    Order BY 
        BOM.oper_num,
        BOM.sequence
    """)

    # for row in connection.cursor.fetchall():
    #     print(row)

    rows = cursor.fetchall()
    columns = [col[0] for col in cursor.description]  # column names
 
    df = pd.DataFrame.from_records(rows, columns=columns)
    print("Dataframe Successful")
    print(df)

    isToriMode = False
connect()
getJobOrderMaterials()
