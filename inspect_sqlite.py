import sqlite3
from pathlib import Path

DB_FOLDER = Path("databases")

for db_path in DB_FOLDER.glob("*.db"):
    print("\n" + "=" * 60)
    print(f"BASE DE DATOS: {db_path}")
    print("=" * 60)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    if not tables:
        print("Sin tablas.")
        conn.close()
        continue

    for (table_name,) in tables:
        print(f"\nTABLA: {table_name}")

        cursor.execute(f"PRAGMA table_info({table_name});")
        print("COLUMNAS:")
        for column in cursor.fetchall():
            print(column)

        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        print("REGISTROS:", cursor.fetchone()[0])

    conn.close()