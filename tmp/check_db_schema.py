import sqlite3

def check_db(db_path):
    print(f"Checking {db_path}...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cursor.fetchall()]
        print(f"Tables: {tables}")
        print(f"Has 'discipline_lockouts': {'discipline_lockouts' in tables}")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

check_db("trading.db")
