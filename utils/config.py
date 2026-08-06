from utils.core import cursor, conn
import os

# Caché en memoria para evitar consultas repetidas a la base de datos
_cache_config = {}

# Asegurar que la tabla existe
cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracion_servidor (
        guild_id BIGINT,
        clave TEXT,
        valor TEXT,
        PRIMARY KEY (guild_id, clave)
    )
""")
conn.commit()

def obtener_config(guild_id: int, clave: str, default=None) -> str:
    cache_key = (guild_id, clave)
    if cache_key in _cache_config:
        return _cache_config[cache_key]
        
    cursor.execute("SELECT valor FROM configuracion_servidor WHERE guild_id = %s AND clave = %s", (guild_id, clave))
    res = cursor.fetchone()
    if res:
        val = res[0]
        _cache_config[cache_key] = val
        return val
        
    # Si no está configurado en BD, intentar obtener del .env para compatibilidad con el servidor actual
    val_env = os.getenv(clave)
    if val_env is not None:
        _cache_config[cache_key] = val_env
        return val_env
        
    return default

def establecer_config(guild_id: int, clave: str, valor: str):
    cursor.execute("""
        INSERT INTO configuracion_servidor (guild_id, clave, valor)
        VALUES (%s, %s, %s)
        ON CONFLICT (guild_id, clave) DO UPDATE SET valor = EXCLUDED.valor
    """, (guild_id, clave, str(valor)))
    conn.commit()
    _cache_config[(guild_id, clave)] = str(valor)

def obtener_config_int(guild_id: int, clave: str, default=0) -> int:
    val = obtener_config(guild_id, clave)
    try:
        return int(val) if val else default
    except ValueError:
        return default

def obtener_config_list(guild_id: int, clave: str, default=None) -> list[int]:
    val = obtener_config(guild_id, clave)
    if val:
        try:
            return [int(r) for r in val.split(",") if r.strip().isdigit()]
        except ValueError:
            pass
    return default if default is not None else []

def safe_env_int(clave: str, default: int = 0) -> int:
    val = os.getenv(clave)
    if val and val.strip():
        try:
            return int(val.strip())
        except ValueError:
            pass
    return default
