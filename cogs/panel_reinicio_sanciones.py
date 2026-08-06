import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

from cogs.panel_strikes import (
    contar_strikes_usuario,
    obtener_strikes_usuario,
    eliminar_strike_con_motivo,
)
from cogs.panel_advertencias import (
    contar_warns,
    obtener_warns_usuario,
    eliminar_warn,
)
from utils.config import obtener_config_int, safe_env_int

load_dotenv()

# --- CONFIGURACIÓN VIA .ENV ---
ROL_PFA_ID         = safe_env_int("ROL_PFA_ID", 0)
ROL_HEAD_PFA_ID    = safe_env_int("ROL_HEAD_PFA_ID", 0)
ROL_PANEL_ADMIN_ID = safe_env_int("ROL_PANEL_ADMIN_ID", 0)
ROL_PERMS          = safe_env_int("ROL_PERMS", 0)

# Canal donde se envía la confirmación (ID provisto directamente)
CANAL_REINICIO_ID = 1438875464256192582

# Motivo que queda registrado en strikes_historial / advertencias_historial
MOTIVO_REINICIO = "Retiro de facción"


def _tiene_permiso(miembro: discord.Member) -> bool:
    """
    Verifica si el miembro que interactúa tiene permiso para confirmar
    o descartar el reinicio de sanciones.

    Se consideran autorizados: Head PFA, Panel Admin y el rol de permisos generales.
    """
    if miembro.id == miembro.guild.owner_id or miembro.guild_permissions.administrator:
        return True
    guild_id = miembro.guild.id
    rol_head = obtener_config_int(guild_id, "ROL_HEAD_PFA_ID", ROL_HEAD_PFA_ID)
    rol_admin = obtener_config_int(guild_id, "ROL_PANEL_ADMIN_ID", ROL_PANEL_ADMIN_ID)
    rol_perms = obtener_config_int(guild_id, "ROL_PERMS", ROL_PERMS)
    ids_roles = {r.id for r in miembro.roles}
    return bool(ids_roles & {rol_head, rol_admin, rol_perms})


class ViewReinicioSanciones(discord.ui.View):
    """
    View con dos botones para confirmar o descartar el reinicio de sanciones
    de un oficial retirado de la PFA.

    No es un panel persistente — tiene un timeout de 10 minutos ya que
    requiere una decisión inmediata al momento del retiro.
    """

    def __init__(self, miembro: discord.Member, n_strikes: int, n_warns: int):
        super().__init__(timeout=600)
        self.miembro   = miembro
        self.n_strikes = n_strikes
        self.n_warns   = n_warns

    def _deshabilitar_botones(self) -> None:
        """Deshabilita todos los botones para prevenir interacciones adicionales."""
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="Sí, eliminar sanciones", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def btn_confirmar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """
        Elimina todos los strikes y advertencias activas del oficial retirado.
        Cada sanción queda registrada en el historial con motivo "Retiro de facción".
        """
        if not _tiene_permiso(interaction.user):
            return await interaction.response.send_message(
                "⛔ No tenés permiso para confirmar esta acción.", ephemeral=True
            )

        await interaction.response.defer()

        # Obtener listas actuales para el conteo real al momento de confirmar
        strikes = obtener_strikes_usuario(self.miembro.id)
        warns   = obtener_warns_usuario(self.miembro.id)

        # Eliminar strikes activos — cada llamada loggea en strikes_historial
        for (strike_id, *_) in strikes:
            eliminar_strike_con_motivo(strike_id, interaction.user.id, MOTIVO_REINICIO)

        # Eliminar advertencias activas — cada llamada loggea en advertencias_historial
        for (warn_id, *_) in warns:
            eliminar_warn(warn_id, interaction.user.id, MOTIVO_REINICIO)

        self._deshabilitar_botones()

        embed = discord.Embed(
            title="✅ Sanciones eliminadas",
            description=(
                f"Las sanciones de **{self.miembro.display_name}** fueron eliminadas y "
                f"registradas en el historial.\n\n"
                f"🗑️ Strikes eliminados: **{len(strikes)}**\n"
                f"🗑️ Advertencias eliminadas: **{len(warns)}**"
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(
            text=f"Ejecutado por {interaction.user.display_name}  •  ID oficial: {self.miembro.id}"
        )
        await interaction.message.edit(content="", embed=embed, view=self)

    @discord.ui.button(label="No, conservar", style=discord.ButtonStyle.secondary, emoji="❎")
    async def btn_cancelar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Descarta el reinicio de sanciones. La DB no se modifica."""
        if not _tiene_permiso(interaction.user):
            return await interaction.response.send_message(
                "⛔ No tenés permiso para responder esta acción.", ephemeral=True
            )

        await interaction.response.defer()
        self._deshabilitar_botones()

        embed = discord.Embed(
            title="❎ Sanciones conservadas",
            description=(
                f"Las sanciones de **{self.miembro.display_name}** fueron conservadas.\n\n"
                f"🔴 Strikes activos: **{self.n_strikes}**\n"
                f"🟡 Advertencias activas: **{self.n_warns}**"
            ),
            color=discord.Color.light_grey(),
        )
        embed.set_footer(
            text=f"Decidido por {interaction.user.display_name}  •  ID oficial: {self.miembro.id}"
        )
        await interaction.message.edit(content="", embed=embed, view=self)

    async def on_timeout(self) -> None:
        """Al vencer el timeout deshabilitar botones para que no queden activos."""
        self._deshabilitar_botones()
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class ReinicioSanciones(commands.Cog):
    """
    Cog que detecta la remoción del rol @PFA de un miembro y ofrece al Head PFA
    la opción de limpiar sus sanciones activas para un posible reingreso limpio.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """
        Se activa con cada cambio de roles en el servidor.

        Si se detecta que se quitó el rol ROL_PFA_ID y el miembro tiene sanciones
        activas, envía un embed de confirmación al canal de reinicio mencionando @headpfa.
        Si no tiene sanciones activas, no hace nada.
        """
        guild_id = after.guild.id
        roles_quitados = set(before.roles) - set(after.roles)
        rol_pfa_id = obtener_config_int(guild_id, "ROL_PFA_ID", ROL_PFA_ID)
        rol_pfa = after.guild.get_role(rol_pfa_id)

        if rol_pfa is None or rol_pfa not in roles_quitados:
            return

        # Consultar sanciones activas — ambas son queries ligeras (una por tabla)
        n_strikes = contar_strikes_usuario(after.id)
        n_warns   = contar_warns(after.id)

        if n_strikes == 0 and n_warns == 0:
            return  # Sin sanciones, no hay nada que ofrecer limpiar

        canal_reinicio_id = obtener_config_int(guild_id, "CANAL_REINICIO_ID", CANAL_REINICIO_ID)
        canal = after.guild.get_channel(canal_reinicio_id)
        if canal is None:
            return

        # Construir la mención al rol Head PFA (vacía si no está configurado)
        rol_head_id = obtener_config_int(guild_id, "ROL_HEAD_PFA_ID", ROL_HEAD_PFA_ID)
        mencion_head = f"<@&{rol_head_id}>" if rol_head_id else ""

        embed = discord.Embed(
            title="⚠️ Oficial retirado de la PFA",
            description=(
                f"El oficial **{after.display_name}** (<@{after.id}>) fue retirado de la facción.\n\n"
                f"🔴 Strikes activos: **{n_strikes}**\n"
                f"🟡 Advertencias activas: **{n_warns}**\n\n"
                f"¿Deseás eliminar todas sus sanciones?\n"
                f"*(Quedarán registradas en el historial con motivo: \"{MOTIVO_REINICIO}\")*"
            ),
            color=discord.Color.orange(),
        )
        embed.set_footer(text=f"ID del oficial: {after.id}")

        view = ViewReinicioSanciones(after, n_strikes, n_warns)
        msg = await canal.send(content=mencion_head, embed=embed, view=view)

        # Asignar el mensaje al view para que on_timeout pueda editarlo
        view.message = msg


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReinicioSanciones(bot))
