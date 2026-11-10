import discord
from discord.ext import commands, tasks
import os
import datetime
from dotenv import load_dotenv
from databases.connection import get_connection
from utils.config import obtener_config_int, safe_env_int

load_dotenv()

# --- CONFIGURACIÓN VIA .ENV (usada como fallback si el servidor no configuró nada) ---
CANAL_GENERAL_ID  = 1351225457864867963  # mismo canal general usado en panel_economia.py / panel_operativo.py / panel_casino.py
ROL_FARMERO_1_ID  = safe_env_int("ROL_FARMERO_1_ID", 0)
ROL_FARMERO_2_ID  = safe_env_int("ROL_FARMERO_2_ID", 0)
ROL_FARMERO_3_ID  = safe_env_int("ROL_FARMERO_3_ID", 0)

NIVEL_MAXIMO = 3


def _obtener_roles_farmero(guild_id: int) -> list[int]:
    return [
        obtener_config_int(guild_id, "ROL_FARMERO_1_ID", ROL_FARMERO_1_ID),
        obtener_config_int(guild_id, "ROL_FARMERO_2_ID", ROL_FARMERO_2_ID),
        obtener_config_int(guild_id, "ROL_FARMERO_3_ID", ROL_FARMERO_3_ID),
    ]

# Offset horario local respecto a UTC (mismo criterio que el resto del bot)
_TZ_OFFSET = safe_env_int("BOT_TIMEZONE_OFFSET", 0)
_TZ_LOCAL = datetime.timezone(datetime.timedelta(hours=_TZ_OFFSET))


def _ahora_local() -> datetime.datetime:
    return datetime.datetime.now(_TZ_LOCAL)


# --- CONEXIÓN A BASE DE DATOS ---
conn = get_connection()
conn.autocommit = True
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS farmeo_horas_semanal (
        user_id BIGINT NOT NULL,
        semana_iso INT NOT NULL,
        anio INT NOT NULL,
        conteo INT NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, semana_iso, anio)
    )
""")


# ---------------------------------------------------------------------------
# Detección del motivo
# ---------------------------------------------------------------------------

def es_motivo_farmeo(razon: str) -> bool:
    """Detecta si una sanción corresponde a farmeo de horas, sin importar
    si vino de una advertencia o de un strike (el texto es el mismo en ambos
    paneles: 'Farmeo de horas (bitácora abierta estando AFK)')."""
    return razon.strip().lower().startswith("farmeo de horas")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

ORIGINAL_GUILD_ID = int(os.getenv("GUILD_ID", "1132046806595944488") or 1132046806595944488)

def registrar_farmeo_horas(user_id: int, guild_id: int = None) -> int:
    if guild_id is None: guild_id = ORIGINAL_GUILD_ID
    ahora = _ahora_local()
    semana_iso = ahora.isocalendar()[1]
    anio = ahora.year

    cursor.execute(
        """
        INSERT INTO farmeo_horas_semanal (guild_id, user_id, semana_iso, anio, conteo)
        VALUES (%s, %s, %s, %s, 1)
        ON CONFLICT (guild_id, user_id, semana_iso, anio)
        DO UPDATE SET conteo = farmeo_horas_semanal.conteo + 1
        RETURNING conteo
        """,
        (guild_id, user_id, semana_iso, anio),
    )
    return cursor.fetchone()[0]


# ---------------------------------------------------------------------------
# Aplicación de roles
# ---------------------------------------------------------------------------

async def _aplicar_rol_farmero(guild: discord.Guild, miembro: discord.Member, conteo: int) -> discord.Role | None:
    """
    Asigna el rol de Farmero correspondiente al nivel actual (tope en Farmero 3)
    y retira cualquier otro rol de Farmero que el miembro tuviera de un nivel
    distinto, para que nunca queden dos roles de farmeo activos a la vez.
    """
    roles_farmero = _obtener_roles_farmero(guild.id)
    nivel = min(conteo, NIVEL_MAXIMO)
    rol_objetivo_id = roles_farmero[nivel - 1]
    rol_objetivo = guild.get_role(rol_objetivo_id) if rol_objetivo_id else None

    roles_a_quitar = []
    for rol_id in roles_farmero:
        if not rol_id or rol_id == rol_objetivo_id:
            continue
        rol = guild.get_role(rol_id)
        if rol and rol in miembro.roles:
            roles_a_quitar.append(rol)

    if roles_a_quitar:
        try:
            await miembro.remove_roles(*roles_a_quitar, reason="Actualización de nivel de farmeo de horas")
        except discord.HTTPException:
            pass

    if rol_objetivo and rol_objetivo not in miembro.roles:
        try:
            await miembro.add_roles(rol_objetivo, reason=f"Farmeo de horas — sanción #{conteo} de la semana")
        except discord.HTTPException:
            pass

    return rol_objetivo


async def procesar_sancion_farmeo(guild: discord.Guild, miembro: discord.Member) -> int:
    """
    Punto de entrada único llamado desde panel_strikes.py y panel_advertencias.py
    cuando el motivo elegido es "Farmeo de horas". Registra la sanción semanal
    y actualiza el rol de Farmero correspondiente. Retorna el conteo actual.
    """
    conteo = registrar_farmeo_horas(miembro.id, guild.id)
    await _aplicar_rol_farmero(guild, miembro, conteo)
    return conteo


# ---------------------------------------------------------------------------
# Cog: reinicio semanal
# ---------------------------------------------------------------------------

class PanelFarmeo(commands.Cog):
    """
    Gestiona el sistema de roles de Farmero (Farmero / Farmero 2 / Farmero 3)
    derivados de sanciones repetidas por farmeo de horas en la misma semana,
    y el reinicio automático de esos roles cada lunes a las 00:00.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_load(self) -> None:
        self.reinicio_semanal_farmeo.start()

    def cog_unload(self) -> None:
        self.reinicio_semanal_farmeo.cancel()

    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=_TZ_LOCAL))
    async def reinicio_semanal_farmeo(self) -> None:
        # El loop corre todos los días a las 00:00 local; solo actuamos los lunes.
        if _ahora_local().weekday() != 0:
            return

        for guild in self.bot.guilds:
            roles_farmero_ids = _obtener_roles_farmero(guild.id)
            roles_farmero = [guild.get_role(rid) for rid in roles_farmero_ids if rid]
            roles_farmero = [r for r in roles_farmero if r]

            afectados = set()
            for rol in roles_farmero:
                for miembro in list(rol.members):
                    afectados.add(miembro.id)
                    try:
                        await miembro.remove_roles(rol, reason="Reinicio semanal del sistema de farmeo de horas")
                    except discord.HTTPException:
                        pass

            if not afectados:
                continue

            canal_general_id = obtener_config_int(guild.id, "CANAL_GENERAL_ID", CANAL_GENERAL_ID)
            canal_general = guild.get_channel(canal_general_id)
            if canal_general:
                await canal_general.send(
                    f"🧹 **Reinicio semanal del sistema de Farmeo de Horas.**\n"
                    f"Se retiraron los roles de Farmero a **{len(afectados)}** integrante/s. "
                    f"¡Gracias por mantener el servicio activo esta semana!"
                )

    @reinicio_semanal_farmeo.before_loop
    async def before_reinicio_semanal_farmeo(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PanelFarmeo(bot))
