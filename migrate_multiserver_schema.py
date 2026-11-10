import os
from dotenv import load_dotenv
from databases.connection import get_connection

load_dotenv()
IBIZA_GUILD_ID = int(os.getenv("GUILD_ID", "1132046806595944488"))

def migrar_esquema_multiservidor():
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()

    print("🚀 Iniciando migración de esquema multi-servidor...")

    # 1. Agregar columna guild_id a todas las tablas si no existe
    tablas = [
        "usuarios",
        "cupones_usuario",
        "strikes",
        "strikes_historial",
        "advertencias",
        "advertencias_historial",
        "pfa_blacklist",
        "turnos_oficiales",
        "farmeo_horas_semanal",
        "doble_faccion_solicitudes",
        "ausencias_activas",
        "registro_pedidos_ausencia",
        "historial_nombres",
        "ura_top_misiones",
        "competencia_subdivisiones",
        "misiones_activas",
        "misiones_diarias_activas",
        "misiones_completadas",
        "misiones_diarias_completadas",
        "rachas_diarias",
        "robos_acudidos",
        "nuevos_ingresantes",
        "oposiciones_sesiones",
        "oposiciones_resultados",
        "oposiciones_cooldown",
        "oposiciones_cierre_semanal",
        "oposiciones_ajustes"
    ]

    for tabla in tablas:
        try:
            cur.execute(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS guild_id BIGINT DEFAULT %s", (IBIZA_GUILD_ID,))
            cur.execute(f"UPDATE {tabla} SET guild_id = %s WHERE guild_id IS NULL", (IBIZA_GUILD_ID,))
            print(f"  ✓ Columna guild_id verificada en {tabla}")
        except Exception as e:
            print(f"  ⚠️ Error en {tabla}: {e}")

    # 2. Ajustar Primary Keys para que incluyan guild_id
    redefinir_pks = [
        ("usuarios", ["guild_id", "user_id"]),
        ("cupones_usuario", ["guild_id", "user_id", "tipo_cupon"]),
        ("pfa_blacklist", ["guild_id", "user_id"]),
        ("turnos_oficiales", ["guild_id", "user_id"]),
        ("farmeo_horas_semanal", ["guild_id", "user_id", "semana_iso", "anio"]),
        ("doble_faccion_solicitudes", ["guild_id", "user_id"]),
        ("ausencias_activas", ["guild_id", "user_id"]),
        ("registro_pedidos_ausencia", ["guild_id", "user_id"]),
        ("ura_top_misiones", ["guild_id", "user_id"]),
        ("competencia_subdivisiones", ["guild_id", "division"]),
        ("misiones_activas", ["guild_id", "user_id"]),
        ("misiones_diarias_activas", ["guild_id", "user_id"]),
        ("rachas_diarias", ["guild_id", "user_id"]),
        ("robos_acudidos", ["guild_id", "user_id"]),
        ("nuevos_ingresantes", ["guild_id", "user_id"]),
        ("oposiciones_cooldown", ["guild_id", "user_id"])
    ]

    for tabla, cols in redefinir_pks:
        try:
            # Obtener nombre de la restricción PK actual
            cur.execute(f"""
                SELECT conname FROM pg_constraint 
                WHERE conrelid = '{tabla}'::regclass AND contype = 'p'
            """)
            pk_info = cur.fetchone()
            if pk_info:
                pk_name = pk_info[0]
                cur.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT {pk_name}")
            
            cols_str = ", ".join(cols)
            cur.execute(f"ALTER TABLE {tabla} ADD PRIMARY KEY ({cols_str})")
            print(f"  ✓ Primary Key actualizada en {tabla} ({cols_str})")
        except Exception as e:
            print(f"  ⚠️ No se pudo actualizar PK en {tabla}: {e}")

    conn.close()
    print("✅ Migración completada exitosamente.")

if __name__ == "__main__":
    migrar_esquema_multiservidor()
