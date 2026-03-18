import sqlite3

def check_db(db_path):
    print(f"Checking {db_path}...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"Tables in {db_path}: {[t[0] for t in tables]}")
        conn.close()
    except Exception as e:
        print(f"Error checking {db_path}: {e}")

check_db("trading.db")
check_db("trading_db.sqlite")
