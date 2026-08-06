import discord
import os
from decimal import Decimal
from databases.connection import get_connection

# --- BASE DE DATOS GLOBAL ---
conn = get_connection()
conn.autocommit = True
cursor = conn.cursor()

def ejecutar_mantenimiento_db():
    cursor.execute("""CREATE TABLE IF NOT EXISTS competencia_subdivisiones (division TEXT PRIMARY KEY, puntos INTEGER DEFAULT 0)""")
    for div in ["URA", "Halcon", "PDI"]:
        cursor.execute("INSERT INTO competencia_subdivisiones (division, puntos) VALUES (%s, 0) ON CONFLICT (division) DO NOTHING", (div,))

    cursor.execute("ALTER TABLE misiones_activas ADD COLUMN IF NOT EXISTS division TEXT")
    cursor.execute("ALTER TABLE misiones_activas ADD COLUMN IF NOT EXISTS progreso INTEGER DEFAULT 0")
    cursor.execute("ALTER TABLE usuarios ALTER COLUMN coins TYPE NUMERIC(12, 2) USING coins::numeric")
    cursor.execute("ALTER TABLE usuarios ALTER COLUMN coins SET DEFAULT 0")
    cursor.execute("ALTER TABLE evidencias_usadas ADD COLUMN IF NOT EXISTS image_hash TEXT")
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS ausencias_activas (user_id BIGINT PRIMARY KEY, fecha_fin BIGINT NOT NULL)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS registro_pedidos_ausencia (user_id BIGINT PRIMARY KEY, ultima_fecha TEXT, conteo_mes INTEGER DEFAULT 0, dias_usados_mes INTEGER DEFAULT 0)""")
    
    try:
        cursor.execute("ALTER TABLE registro_pedidos_ausencia ADD COLUMN IF NOT EXISTS conteo_mes INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE registro_pedidos_ausencia ADD COLUMN IF NOT EXISTS dias_usados_mes INTEGER DEFAULT 0")
    except: pass
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS nuevos_ingresantes (user_id BIGINT PRIMARY KEY, fecha_expiracion TIMESTAMP WITH TIME ZONE NOT NULL)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS oposiciones_sesiones (id SERIAL PRIMARY KEY, interviewer_id BIGINT NOT NULL, fecha_apertura TIMESTAMPTZ NOT NULL DEFAULT NOW(), fecha_cierre TIMESTAMPTZ, numero_semanal INT NOT NULL, semana_iso INT NOT NULL, anio INT NOT NULL, activa BOOLEAN DEFAULT TRUE)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS oposiciones_resultados (id SERIAL PRIMARY KEY, sesion_id INT REFERENCES oposiciones_sesiones(id), interviewer_id BIGINT NOT NULL, postulante_id BIGINT NOT NULL, nota INT NOT NULL, aprobado BOOLEAN NOT NULL, invitado_por BIGINT, semana_iso INT NOT NULL, anio INT NOT NULL, fecha TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS oposiciones_cooldown (user_id BIGINT PRIMARY KEY, puede_postular_desde TIMESTAMPTZ NOT NULL)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS oposiciones_cierre_semanal (id SERIAL PRIMARY KEY, semana_iso INT NOT NULL, anio INT NOT NULL, cerrado_por BIGINT NOT NULL, fecha_cierre TIMESTAMPTZ DEFAULT NOW(), total_sesiones INT NOT NULL, total_evaluados INT NOT NULL, total_aprobados INT NOT NULL, total_horas_decimal NUMERIC(6,2), resumen_json JSONB)""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS oposiciones_ajustes (
            id SERIAL PRIMARY KEY,
            interviewer_id BIGINT NOT NULL,
            aprobados_ajuste INTEGER DEFAULT 0,
            horas_ajuste NUMERIC(6,2) DEFAULT 0.0,
            semana_iso INTEGER NOT NULL,
            anio INTEGER NOT NULL,
            fecha TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.commit()

ejecutar_mantenimiento_db()

def obtener_coins(user_id):
    cursor.execute("SELECT coins FROM usuarios WHERE user_id = %s", (user_id,))
    resultado = cursor.fetchone()
    return float(resultado[0]) if resultado else 0.0

def actualizar_coins(user_id, cantidad):
    cantidad_decimal = Decimal(str(cantidad))
    cursor.execute("""
        INSERT INTO usuarios (user_id, coins) VALUES (%s, GREATEST(0, %s))
        ON CONFLICT (user_id) DO UPDATE SET coins = GREATEST(0, usuarios.coins + %s) RETURNING coins
    """, (user_id, cantidad_decimal, cantidad_decimal))
    conn.commit()
    return float(cursor.fetchone()[0])

async def enviar_log(bot, staff_o_usuario: discord.Member, target_id: int, cantidad: float, tipo: str, item: str = None):
    from utils.config import obtener_config_int
    guild_id = staff_o_usuario.guild.id
    canal_logs_id = obtener_config_int(guild_id, "CANAL_LOGS_ID", 1474174294803222528)
    canal_general_id = obtener_config_int(guild_id, "CANAL_GENERAL_ID", 1351225457864867963)
    
    canal_logs = bot.get_channel(canal_logs_id)
    if not canal_logs: return

    color, titulo = discord.Color.light_grey(), "Notificación de Sistema"
    if tipo == "dar": color, titulo = discord.Color.green(), "➕ Monedas Entregadas"
    elif tipo == "quitar": color, titulo = discord.Color.red(), "➖ Monedas Retiradas"
    elif tipo == "compra": color, titulo = discord.Color.gold(), "🛒 Compra en Shop"
    elif tipo == "blackjack": color, titulo = discord.Color.purple(), "🃏 Apuesta Blackjack"
    elif tipo == "ruleta": color, titulo = discord.Color.fuchsia(), "🎰 Apuesta Ruleta" 
    elif tipo == "airdrop_lanzado": color, titulo = discord.Color.blue(), "📦 Airdrop Lanzado"
    elif tipo == "airdrop_reclamado": color, titulo = discord.Color.dark_blue(), "🎁 Airdrop Reclamado"
    elif tipo == "mision_completada": color, titulo = discord.Color.brand_green(), "🏆 Misión Semanal Completada"
    elif tipo == "reset_mision": color, titulo = discord.Color.orange(), "♻️ Reinicio de Misiones"
    elif tipo == "misiones_auto": color, titulo = discord.Color.dark_teal(), "📋 Pago de Operativo"

    embed = discord.Embed(title=titulo, color=color, timestamp=discord.utils.utcnow())
    
    if tipo == "airdrop_lanzado":
        embed.add_field(name="🛡️ Staff Responsable", value=f"{staff_o_usuario.mention} (`{staff_o_usuario.id}`)", inline=False)
        embed.add_field(name="📍 Canal", value=f"<#{CANAL_GENERAL_ID}>", inline=False)
    elif tipo == "reset_mision":
        embed.add_field(name="🛡️ Staff Responsable", value=f"{staff_o_usuario.mention} (`{staff_o_usuario.id}`)", inline=False)
        embed.add_field(name="👤 Usuario Afectado", value=f"<@{target_id}> (`{target_id}`)", inline=False)
        if item: embed.add_field(name="📝 Detalle", value=f"**{item}**", inline=False)
    elif tipo in ["compra", "blackjack", "ruleta", "airdrop_reclamado", "mision_completada", "misiones_auto"]: 
        embed.add_field(name="👤 Usuario", value=f"{staff_o_usuario.mention} (`{staff_o_usuario.id}`)", inline=False)
        if item: embed.add_field(name="📝 Detalle de Apuesta" if tipo in ["blackjack", "ruleta"] else "📦 Detalle", value=f"{item}", inline=False)
    else:
        embed.add_field(name="🛡️ Staff Responsable", value=f"{staff_o_usuario.mention} (`{staff_o_usuario.id}`)", inline=False)
        embed.add_field(name="👤 Usuario Afectado", value=f"<@{target_id}> (`{target_id}`)", inline=False)
    
    if tipo not in ["airdrop_lanzado", "reset_mision"]:
        embed.add_field(name="💰 Cambio Neto", value=f"**{abs(cantidad):,.2f} coins**", inline=True)
        embed.add_field(name="🏦 Nuevo Saldo", value=f"**{obtener_coins(target_id):,.2f} coins**", inline=True)
    
    embed.set_footer(text="Registro de Auditoría - Scanneler Economy")
    await canal_logs.send(embed=embed)