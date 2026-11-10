from utils.core import cursor, conn
import os

# Caché en memoria para evitar consultas repetidas a la base de datos
_cache_config = {}

ORIGINAL_GUILD_ID = int(os.getenv("GUILD_ID", "1132046806595944488") or 1132046806595944488)

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
        
    # Solo caer al .env SI es el servidor original (compatibilidad histórica)
    if guild_id and guild_id == ORIGINAL_GUILD_ID:
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
    val = obtener_config(guild_id, clave, None)
    if val is not None and str(val).strip():
        try:
            return int(str(val).strip())
        except ValueError:
            pass
            
    # Si no está configurado:
    # Si es el servidor original, permitimos el fallback histórico
    if guild_id and guild_id == ORIGINAL_GUILD_ID:
        return default
        
    # Si es un servidor nuevo, NO heredamos IDs de Discord de Ibiza (números gigantes tipo Snowflake > 10^14)
    if isinstance(default, int) and default > 100_000_000_000_000:
        return 0
        
    return default

def obtener_config_list(guild_id: int, clave: str, default=None) -> list[int]:
    val = obtener_config(guild_id, clave, None)
    if val:
        try:
            return [int(r) for r in str(val).split(",") if r.strip().isdigit()]
        except ValueError:
            pass
            
    # Solo devolver la lista de roles por defecto si es el servidor original
    if guild_id and guild_id == ORIGINAL_GUILD_ID and default is not None:
        return default
        
    return []

def safe_env_int(clave: str, default: int = 0) -> int:
    val = os.getenv(clave)
    if val and val.strip():
        try:
            return int(val.strip())
        except ValueError:
            pass
    return default
