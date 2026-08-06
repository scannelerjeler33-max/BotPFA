from databases.connection import get_connection

TABLES = [
    "advertencias",
    "advertencias_historial",
    "historial_nombres",
    "usuarios",
    "misiones_activas",
    "misiones_completadas",
    "misiones_diarias_activas",
    "misiones_diarias_completadas",
    "rachas_diarias",
    "competencia_subdivisiones",
    "robos_acudidos",
    "evidencias_usadas",
    "ausencias_activas",
    "registro_pedidos_ausencia",
    "pfa_blacklist",
    "strikes",
    "strikes_historial",
]

conn = get_connection()

with conn.cursor() as cur:
    for table in TABLES:
        cur.execute(f"SELECT COUNT(*) FROM {table};")
        count = cur.fetchone()[0]
        print(f"{table}: {count}")

conn.close()