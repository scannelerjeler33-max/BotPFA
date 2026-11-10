import sys
from databases.connection import get_connection

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    conn = get_connection()
    print("✅ Conexión exitosa a PostgreSQL")
    conn.close()
except Exception as e:
    print("❌ Error conectando a PostgreSQL:")
    print(e)
