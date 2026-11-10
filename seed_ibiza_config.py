import os
from dotenv import load_dotenv
from databases.connection import get_connection

load_dotenv()

IBIZA_GUILD_ID = int(os.getenv("GUILD_ID", "1132046806595944488"))

def seed_config():
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()

    # Asegurar tabla
    cur.execute("""
        CREATE TABLE IF NOT EXISTS configuracion_servidor (
            guild_id BIGINT,
            clave TEXT,
            valor TEXT,
            PRIMARY KEY (guild_id, clave)
        )
    """)

    insertados = 0
    with open(".env", "r", encoding="utf-8", errors="ignore") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            clave = clave.strip()
            valor = valor.strip().split("#")[0].strip() # quitar comentarios inline si hay
            
            # No guardar secretos o tokens en la tabla pública de roles/canales
            if clave in ["DISCORD_TOKEN", "DATABASE_URL", "PORT"]:
                continue
            if valor:
                cur.execute("""
                    INSERT INTO configuracion_servidor (guild_id, clave, valor)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (guild_id, clave) DO UPDATE SET valor = EXCLUDED.valor
                """, (IBIZA_GUILD_ID, clave, valor))
                insertados += 1

    conn.close()
    print(f"✅ Se guardaron {insertados} configuraciones para el servidor original ({IBIZA_GUILD_ID}).")

if __name__ == "__main__":
    seed_config()
