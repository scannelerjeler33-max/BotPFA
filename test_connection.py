from databases.connection import get_connection

try:
    conn = get_connection()
    print("✅ Conexión exitosa a PostgreSQL")
    conn.close()
except Exception as e:
    print("❌ Error conectando a PostgreSQL:")
    print(e)