import sqlite3
from pathlib import Path
from databases.connection import get_connection

DATABASES = [
    Path("databases/advertencias.db"),
    Path("databases/cambios_nombre.db"),
    Path("databases/economia.db"),
    Path("databases/strikes.db"),
]

SKIP_TABLES = {"sqlite_sequence"}


def create_tables(pg):
    with pg.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS advertencias (
            warn_id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            razon TEXT NOT NULL,
            admin_id BIGINT NOT NULL,
            fecha TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS advertencias_historial (
            id SERIAL PRIMARY KEY,
            warn_id TEXT NOT NULL,
            user_id BIGINT NOT NULL,
            razon TEXT NOT NULL,
            admin_id BIGINT NOT NULL,
            fecha TEXT NOT NULL,
            accion TEXT NOT NULL,
            motivo_eliminacion TEXT
        );

        CREATE TABLE IF NOT EXISTS historial_nombres (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            nombre_anterior TEXT,
            nombre_nuevo TEXT,
            placa TEXT,
            estado TEXT,
            procesado_por BIGINT,
            motivo TEXT,
            fecha TEXT
        );

        CREATE TABLE IF NOT EXISTS usuarios (
            user_id BIGINT PRIMARY KEY,
            coins NUMERIC(12, 2) DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS misiones_activas (
            user_id BIGINT PRIMARY KEY,
            mision_nombre TEXT,
            division TEXT,
            progreso INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS misiones_completadas (
            user_id BIGINT,
            mision_nombre TEXT,
            fecha TEXT
        );

        CREATE TABLE IF NOT EXISTS misiones_diarias_activas (
            user_id BIGINT PRIMARY KEY,
            mision_nombre TEXT,
            division TEXT,
            progreso INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS misiones_diarias_completadas (
            user_id BIGINT,
            fecha TEXT
        );

        CREATE TABLE IF NOT EXISTS rachas_diarias (
            user_id BIGINT PRIMARY KEY,
            contador INTEGER DEFAULT 0,
            ultima_fecha TEXT
        );

        CREATE TABLE IF NOT EXISTS competencia_subdivisiones (
            division TEXT PRIMARY KEY,
            puntos INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS robos_acudidos (
            user_id BIGINT PRIMARY KEY,
            total_robos INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS evidencias_usadas (
            msg_id TEXT PRIMARY KEY,
            user_id BIGINT,
            tipo TEXT,
            image_hash TEXT
        );

        CREATE TABLE IF NOT EXISTS ausencias_activas (
            user_id BIGINT PRIMARY KEY,
            fecha_fin BIGINT
        );

        CREATE TABLE IF NOT EXISTS registro_pedidos_ausencia (
            user_id BIGINT PRIMARY KEY,
            ultima_fecha TEXT,
            conteo_mes INTEGER DEFAULT 0,
            dias_usados_mes INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS pfa_blacklist (
            user_id BIGINT PRIMARY KEY,
            motivo TEXT NOT NULL,
            admin_id BIGINT NOT NULL,
            fecha TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS strikes (
            strike_id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            razon TEXT NOT NULL,
            admin_id BIGINT NOT NULL,
            fecha TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS strikes_historial (
            id SERIAL PRIMARY KEY,
            strike_id TEXT NOT NULL,
            user_id BIGINT NOT NULL,
            razon TEXT NOT NULL,
            admin_id BIGINT NOT NULL,
            fecha TEXT NOT NULL,
            accion TEXT NOT NULL,
            motivo_eliminacion TEXT
        );
        """)
    pg.commit()


def get_sqlite_tables(sqlite_conn):
    cur = sqlite_conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    return [row[0] for row in cur.fetchall() if row[0] not in SKIP_TABLES]


def migrate_table(sqlite_conn, pg, table_name):
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cur.fetchall()

    if not rows:
        print(f"⚪ {table_name}: sin registros")
        return

    columns = [desc[0] for desc in sqlite_cur.description]
    placeholders = ", ".join(["%s"] * len(columns))
    column_names = ", ".join(columns)

    sql = f"""
        INSERT INTO {table_name} ({column_names})
        VALUES ({placeholders})
        ON CONFLICT DO NOTHING
    """

    with pg.cursor() as pg_cur:
        pg_cur.executemany(sql, rows)

    pg.commit()
    print(f"✅ {table_name}: {len(rows)} registros migrados")


def main():
    pg = get_connection()
    create_tables(pg)

    for db_path in DATABASES:
        print(f"\n📦 Migrando {db_path}")

        sqlite_conn = sqlite3.connect(db_path)
        tables = get_sqlite_tables(sqlite_conn)

        for table_name in tables:
            migrate_table(sqlite_conn, pg, table_name)

        sqlite_conn.close()

    pg.close()
    print("\n🎉 Migración terminada")


if __name__ == "__main__":
    main()
