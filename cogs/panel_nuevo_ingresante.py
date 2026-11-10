import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import datetime
from dotenv import load_dotenv
from databases.connection import get_connection
from utils.config import obtener_config_int, safe_env_int

load_dotenv()

# --- CONEXIÓN A BASE DE DATOS ---
conn_nuevo = get_connection()
conn_nuevo.autocommit = True
cursor_nuevo = conn_nuevo.cursor()

# --- CONFIGURACIÓN VIA .ENV ---
ROL_PFA_ID              = safe_env_int("ROL_PFA_ID", 0)
ROL_NUEVO_INGRESANTE_ID = safe_env_int("ROL_NUEVO_INGRESANTE_ID", 0)
ROL_PANEL_ADMIN_ID      = safe_env_int("ROL_PANEL_ADMIN_ID", 0)
ROL_PERMS               = safe_env_int("ROL_PERMS", 0)

DIAS_GRACIA = 7  # Días que dura el rol antes de expirar automáticamente


# ---------------------------------------------------------------------------
# DB — nuevos_ingresantes
# ---------------------------------------------------------------------------

ORIGINAL_GUILD_ID = int(os.getenv("GUILD_ID", "1132046806595944488") or 1132046806595944488)

def registrar_nuevo_ingresante(user_id: int, guild_id: int = None) -> None:
    if guild_id is None: guild_id = ORIGINAL_GUILD_ID
    cursor_nuevo.execute(
        """
        INSERT INTO nuevos_ingresantes (guild_id, user_id, fecha_expiracion)
        VALUES (%s, %s, NOW() + INTERVAL '7 days')
        ON CONFLICT (guild_id, user_id) DO UPDATE SET fecha_expiracion = NOW() + INTERVAL '7 days'
        """,
        (guild_id, user_id),
    )


def obtener_ingresantes_expirados() -> list[tuple[int, int]]:
    """Retorna pares (guild_id, user_id) cuya fecha_expiracion ya pasó."""
    cursor_nuevo.execute(
        "SELECT guild_id, user_id FROM nuevos_ingresantes WHERE fecha_expiracion < NOW()"
    )
    return cursor_nuevo.fetchall()


def eliminar_ingresante(user_id: int, guild_id: int = None) -> None:
    if guild_id is None: guild_id = ORIGINAL_GUILD_ID
    cursor_nuevo.execute(
        "DELETE FROM nuevos_ingresantes WHERE user_id = %s AND guild_id = %s",
        (user_id, guild_id),
    )


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class PanelNuevoIngresante(commands.Cog):
    """
    Gestiona el rol @Nuevo Ingresante de la PFA.

    - Asigna el rol automáticamente cuando se da @PFA (on_member_update).
    - Expira el rol a los 7 días via tarea periódica (DB persiste la fecha).
    - Comando /nuevo para registrar manualmente cuando el bot estaba offline.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_load(self) -> None:
        self.limpiar_expirados.start()

    def cog_unload(self) -> None:
        self.limpiar_expirados.cancel()

    # --- TAREA PERIÓDICA ---

    @tasks.loop(hours=1)
    async def limpiar_expirados(self) -> None:
        """
        Cada hora revisa nuevos_ingresantes y quita el rol a quienes superaron los
        7 días. Si el bot estuvo offline, la limpieza ocurre al volver a estar online.
        """
        ids_expirados = obtener_ingresantes_expirados()
        if not ids_expirados:
            return

        for guild_id, user_id in ids_expirados:
            guild = self.bot.get_guild(guild_id)
            if guild:
                rol_nuevo_id = obtener_config_int(guild.id, "ROL_NUEVO_INGRESANTE_ID", ROL_NUEVO_INGRESANTE_ID)
                rol_nuevo = guild.get_role(rol_nuevo_id) if rol_nuevo_id else None
                if rol_nuevo:
                    miembro = guild.get_member(user_id)
                    if miembro and rol_nuevo in miembro.roles:
                        try:
                            await miembro.remove_roles(
                                rol_nuevo,
                                reason="Período de nuevo ingresante expirado (7 días)"
                            )
                        except discord.HTTPException:
                            pass
            eliminar_ingresante(user_id, guild_id)

    @limpiar_expirados.before_loop
    async def before_limpiar(self) -> None:
        await self.bot.wait_until_ready()

    # --- LISTENER ---

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """
        Cuando se asigna @PFA, da el rol @Nuevo Ingresante automáticamente
        y registra la expiración de 7 días en la DB.
        """
        roles_agregados = set(after.roles) - set(before.roles)
        rol_pfa_id = obtener_config_int(after.guild.id, "ROL_PFA_ID", ROL_PFA_ID)
        rol_pfa = after.guild.get_role(rol_pfa_id)
        if rol_pfa is None or rol_pfa not in roles_agregados:
            return

        rol_nuevo_id = obtener_config_int(after.guild.id, "ROL_NUEVO_INGRESANTE_ID", ROL_NUEVO_INGRESANTE_ID)
        rol_nuevo = after.guild.get_role(rol_nuevo_id)
        if rol_nuevo:
            try:
                await after.add_roles(
                    rol_nuevo,
                    reason="Nuevo ingresante en PFA — período de gracia de 7 días"
                )
            except discord.HTTPException:
                pass

        registrar_nuevo_ingresante(after.id, after.guild.id)

    # --- COMANDOS ---

    @app_commands.command(
        name="nuevo",
        description="Registra manualmente a un oficial como nuevo ingresante (excluido de limpieza 7 días)."
    )
    async def nuevo(self, interaction: discord.Interaction, miembro: discord.Member) -> None:
        es_staff = (
            interaction.user.id == interaction.guild.owner_id or
            interaction.user.guild_permissions.administrator
        )
        rol_admin = obtener_config_int(interaction.guild.id, "ROL_PANEL_ADMIN_ID", ROL_PANEL_ADMIN_ID)
        rol_perms = obtener_config_int(interaction.guild.id, "ROL_PERMS", ROL_PERMS)
        tiene_rol_admin = rol_admin and any(r.id == rol_admin for r in interaction.user.roles)
        tiene_rol_perms = rol_perms and any(r.id == rol_perms for r in interaction.user.roles)
        if not (es_staff or tiene_rol_admin or tiene_rol_perms):
            return await interaction.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)
        """
        Fallback manual para cuando el bot estaba offline al asignarse el rol @PFA,
        o para reiniciar el período de gracia ante un reingreso.

        Da el rol @Nuevo Ingresante y persiste la expiración en DB.
        """
        rol_nuevo_id = obtener_config_int(interaction.guild.id, "ROL_NUEVO_INGRESANTE_ID", ROL_NUEVO_INGRESANTE_ID)
        rol_nuevo = interaction.guild.get_role(rol_nuevo_id)
        if rol_nuevo is None:
            await interaction.response.send_message(
                "❌ Rol de Nuevo Ingresante no configurado. Verificá `ROL_NUEVO_INGRESANTE_ID` con `/configuracion`.",
                ephemeral=True,
            )
            return

        await miembro.add_roles(
            rol_nuevo,
            reason=f"Nuevo ingresante registrado manualmente por {interaction.user.display_name}"
        )
        registrar_nuevo_ingresante(miembro.id, interaction.guild.id)

        expiracion_ts = int(
            (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=DIAS_GRACIA)).timestamp()
        )
        embed = discord.Embed(
            title="✅ Nuevo ingresante registrado",
            description=(
                f"{miembro.mention} fue registrado como nuevo ingresante.\n\n"
                f"Quedará excluido de la limpieza hasta el <t:{expiracion_ts}:F>.\n"
                f"El rol se retirará automáticamente al vencer el plazo."
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"Registrado por {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

    @nuevo.error
    async def nuevo_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message(
                "⛔ No tenés los permisos necesarios para usar este comando.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PanelNuevoIngresante(bot))
