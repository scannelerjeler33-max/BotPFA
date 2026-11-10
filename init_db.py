import sys
import os
from dotenv import load_dotenv
from databases.connection import get_connection

load_dotenv()
ORIGINAL_GUILD_ID = int(os.getenv("GUILD_ID", "1132046806595944488") or 1132046806595944488)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def inicializar_base_de_datos():
    print("🔄 Conectando a PostgreSQL...")
    try:
        conn = get_connection()
        conn.autocommit = True
        cur = conn.cursor()
    except Exception as e:
        print(f"❌ Error al conectar a la base de datos: {e}")
        return

    print("📦 Creando tablas necesarias con soporte Multi-Servidor (guild_id)...")

    tablas_sql = f"""
    -- Configuración por servidor
    CREATE TABLE IF NOT EXISTS configuracion_servidor (
        guild_id BIGINT,
        clave TEXT,
        valor TEXT,
        PRIMARY KEY (guild_id, clave)
    );

    -- Tablas de Usuarios y Economía
    CREATE TABLE IF NOT EXISTS usuarios (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        coins NUMERIC(12, 2) DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS cupones_usuario (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        tipo_cupon TEXT,
        cantidad INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, tipo_cupon)
    );

    -- Tablas de Misiones y Actividades
    CREATE TABLE IF NOT EXISTS misiones_activas (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        mision_nombre TEXT,
        division TEXT,
        progreso INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS misiones_completadas (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        mision_nombre TEXT,
        fecha TEXT
    );

    CREATE TABLE IF NOT EXISTS misiones_diarias_activas (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        mision_nombre TEXT,
        division TEXT,
        progreso INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS misiones_diarias_completadas (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        fecha TEXT
    );

    CREATE TABLE IF NOT EXISTS rachas_diarias (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        contador INTEGER DEFAULT 0,
        ultima_fecha TEXT,
        PRIMARY KEY (guild_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS robos_acudidos (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        total_robos INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS evidencias_usadas (
        msg_id TEXT PRIMARY KEY,
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        tipo TEXT,
        image_hash TEXT
    );

    CREATE TABLE IF NOT EXISTS competencia_subdivisiones (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        division TEXT,
        puntos INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, division)
    );

    CREATE TABLE IF NOT EXISTS ura_top_misiones (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        misiones INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    );

    -- Tablas de Sanciones y Blacklist
    CREATE TABLE IF NOT EXISTS advertencias (
        warn_id TEXT PRIMARY KEY,
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT NOT NULL,
        razon TEXT NOT NULL,
        admin_id BIGINT NOT NULL,
        fecha TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS advertencias_historial (
        id SERIAL PRIMARY KEY,
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        warn_id TEXT NOT NULL,
        user_id BIGINT NOT NULL,
        razon TEXT NOT NULL,
        admin_id BIGINT NOT NULL,
        fecha TEXT NOT NULL,
        accion TEXT NOT NULL,
        motivo_eliminacion TEXT
    );

    CREATE TABLE IF NOT EXISTS strikes (
        strike_id TEXT PRIMARY KEY,
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT NOT NULL,
        razon TEXT NOT NULL,
        admin_id BIGINT NOT NULL,
        fecha TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS strikes_historial (
        id SERIAL PRIMARY KEY,
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        strike_id TEXT NOT NULL,
        user_id BIGINT NOT NULL,
        razon TEXT NOT NULL,
        admin_id BIGINT NOT NULL,
        fecha TEXT NOT NULL,
        accion TEXT NOT NULL,
        motivo_eliminacion TEXT
    );

    CREATE TABLE IF NOT EXISTS pfa_blacklist (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        motivo TEXT NOT NULL,
        admin_id BIGINT NOT NULL,
        fecha TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (guild_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS farmeo_horas_semanal (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT NOT NULL,
        semana_iso INT NOT NULL,
        anio INT NOT NULL,
        conteo INT NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, semana_iso, anio)
    );

    -- Tablas de Gestión, Turnos y Ausencias
    CREATE TABLE IF NOT EXISTS historial_nombres (
        id SERIAL PRIMARY KEY,
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        nombre_anterior TEXT,
        nombre_nuevo TEXT,
        placa TEXT,
        estado TEXT,
        procesado_por BIGINT,
        motivo TEXT,
        fecha TEXT
    );

    CREATE TABLE IF NOT EXISTS ausencias_activas (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        fecha_fin BIGINT NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS registro_pedidos_ausencia (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        ultima_fecha TEXT,
        conteo_mes INTEGER DEFAULT 0,
        dias_usados_mes INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS turnos_oficiales (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        turno_activo BOOLEAN DEFAULT FALSE,
        inicio_turno TIMESTAMPTZ,
        turnos_semana INTEGER DEFAULT 0,
        horas_semana NUMERIC(6,2) DEFAULT 0.0,
        PRIMARY KEY (guild_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS doble_faccion_solicitudes (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        estado TEXT DEFAULT 'pendiente',
        PRIMARY KEY (guild_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS nuevos_ingresantes (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        fecha_expiracion TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    );

    -- Tablas de Oposiciones / Interviewer
    CREATE TABLE IF NOT EXISTS oposiciones_sesiones (
        id SERIAL PRIMARY KEY,
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        interviewer_id BIGINT NOT NULL,
        fecha_apertura TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        fecha_cierre TIMESTAMPTZ,
        numero_semanal INT NOT NULL,
        semana_iso INT NOT NULL,
        anio INT NOT NULL,
        activa BOOLEAN DEFAULT TRUE
    );

    CREATE TABLE IF NOT EXISTS oposiciones_resultados (
        id SERIAL PRIMARY KEY,
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        sesion_id INT REFERENCES oposiciones_sesiones(id),
        interviewer_id BIGINT NOT NULL,
        postulante_id BIGINT NOT NULL,
        nota INT NOT NULL,
        aprobado BOOLEAN NOT NULL,
        invitado_por BIGINT,
        semana_iso INT NOT NULL,
        anio INT NOT NULL,
        fecha TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS oposiciones_cooldown (
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        user_id BIGINT,
        puede_postular_desde TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS oposiciones_cierre_semanal (
        id SERIAL PRIMARY KEY,
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        semana_iso INT NOT NULL,
        anio INT NOT NULL,
        cerrado_por BIGINT NOT NULL,
        fecha_cierre TIMESTAMPTZ DEFAULT NOW(),
        total_sesiones INT NOT NULL,
        total_evaluados INT NOT NULL,
        total_aprobados INT NOT NULL,
        total_horas_decimal NUMERIC(6,2),
        resumen_json JSONB
    );

    CREATE TABLE IF NOT EXISTS oposiciones_ajustes (
        id SERIAL PRIMARY KEY,
        guild_id BIGINT DEFAULT {ORIGINAL_GUILD_ID},
        interviewer_id BIGINT NOT NULL,
        aprobados_ajuste INTEGER DEFAULT 0,
        horas_ajuste NUMERIC(6,2) DEFAULT 0.0,
        semana_iso INTEGER NOT NULL,
        anio INTEGER NOT NULL,
        fecha TIMESTAMPTZ DEFAULT NOW()
    );
    """

    try:
        cur.execute(tablas_sql)
        conn.close()
        print("✅ Todas las tablas multi-servidor han sido verificadas y creadas exitosamente.")
    except Exception as e:
        print(f"❌ Error al crear tablas: {e}")

if __name__ == "__main__":
    inicializar_base_de_datos()
