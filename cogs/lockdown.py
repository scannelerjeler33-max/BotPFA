import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

LOCKDOWN_STATE_PATH = Path(__file__).with_name("lockdown_state.json")


class Lockdown(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lockdowns = self._cargar_lockdowns()

    @commands.Cog.listener()
    async def on_ready(self):
        print("[Cog] Lockdown cargado.")

    # ------------------------------------------------------------------
    # /lock [canal]
    # ------------------------------------------------------------------
    @app_commands.command(name="lock", description="Cierra un canal para que nadie pueda escribir.")
    @app_commands.describe(canal="Canal a cerrar (por defecto: el canal actual)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        canal = canal or interaction.channel

        if str(canal.id) in self.lockdowns:
            return await interaction.response.send_message(
                f"{canal.mention} ya está cerrado.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        await self._lock_canal(canal, interaction.user)

        embed = discord.Embed(
            title="🔒 Canal cerrado",
            description="Este canal fue cerrado temporalmente. Solo administradores pueden escribir.",
            color=0x2B2D31,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Canal", value=canal.mention, inline=True)
        embed.add_field(name="Moderador", value=interaction.user.mention, inline=True)
        embed.set_footer(text="Sistema de lockdown · PFA")
        await canal.send(embed=embed)

        await interaction.followup.send(f"✅ {canal.mention} cerrado.", ephemeral=True)

    # ------------------------------------------------------------------
    # /unlock [canal]
    # ------------------------------------------------------------------
    @app_commands.command(name="unlock", description="Abre un canal cerrado.")
    @app_commands.describe(canal="Canal a abrir (por defecto: el canal actual)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        canal = canal or interaction.channel

        if str(canal.id) not in self.lockdowns:
            return await interaction.response.send_message(
                f"{canal.mention} no está en lockdown.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        await self._unlock_canal(canal, interaction.guild, interaction.user)

        embed = discord.Embed(
            title="🔓 Canal abierto",
            description="Este canal fue abierto nuevamente.",
            color=0x57F287,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Canal", value=canal.mention, inline=True)
        embed.add_field(name="Moderador", value=interaction.user.mention, inline=True)
        embed.set_footer(text="Sistema de lockdown · PFA")
        await canal.send(embed=embed)

        await interaction.followup.send(f"✅ {canal.mention} abierto.", ephemeral=True)

    # ------------------------------------------------------------------
    # /lockdown [razon]
    # ------------------------------------------------------------------
    @app_commands.command(name="lockdown", description="Cierra TODOS los canales de texto del servidor.")
    @app_commands.describe(razon="Motivo del lockdown (opcional)")
    async def lockdown(self, interaction: discord.Interaction, razon: str = "Sin motivo especificado"):
        es_staff = (
            interaction.user.id == interaction.guild.owner_id or
            interaction.user.guild_permissions.administrator
        )
        from utils.config import obtener_config_int
        rol_admin = obtener_config_int(interaction.guild.id, "ROL_PANEL_ADMIN_ID")
        rol_perms = obtener_config_int(interaction.guild.id, "ROL_PERMS")
        tiene_rol_admin = rol_admin and any(r.id == rol_admin for r in interaction.user.roles)
        tiene_rol_perms = rol_perms and any(r.id == rol_perms for r in interaction.user.roles)
        if not (es_staff or tiene_rol_admin or tiene_rol_perms):
            return await interaction.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        canales = [
            c for c in interaction.guild.text_channels
            if str(c.id) not in self.lockdowns
        ]

        if not canales:
            return await interaction.followup.send(
                "Todos los canales de texto ya están cerrados.", ephemeral=True
            )

        for canal in canales:
            await self._lock_canal(canal, interaction.user)

        embed = discord.Embed(
            title="🔒 LOCKDOWN ACTIVADO",
            description=f"**Todos los canales han sido cerrados.**\n\n**Motivo:** {razon}",
            color=0x2B2D31,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Moderador", value=interaction.user.mention, inline=True)
        embed.add_field(name="Canales afectados", value=str(len(canales)), inline=True)
        embed.set_footer(text="Sistema de lockdown · PFA")
        await interaction.channel.send(embed=embed)

        await interaction.followup.send(
            f"✅ Lockdown activado en **{len(canales)}** canales.", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /unlockdown
    # ------------------------------------------------------------------
    @app_commands.command(name="unlockdown", description="Levanta el lockdown y abre todos los canales cerrados.")
    async def unlockdown(self, interaction: discord.Interaction):
        es_staff = (
            interaction.user.id == interaction.guild.owner_id or
            interaction.user.guild_permissions.administrator
        )
        from utils.config import obtener_config_int
        rol_admin = obtener_config_int(interaction.guild.id, "ROL_PANEL_ADMIN_ID")
        rol_perms = obtener_config_int(interaction.guild.id, "ROL_PERMS")
        tiene_rol_admin = rol_admin and any(r.id == rol_admin for r in interaction.user.roles)
        tiene_rol_perms = rol_perms and any(r.id == rol_perms for r in interaction.user.roles)
        if not (es_staff or tiene_rol_admin or tiene_rol_perms):
            return await interaction.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        ids_locked = list(self.lockdowns.keys())

        if not ids_locked:
            return await interaction.followup.send(
                "No hay canales en lockdown actualmente.", ephemeral=True
            )

        abiertos = 0
        for canal_id in ids_locked:
            canal = interaction.guild.get_channel(int(canal_id))
            if canal:
                await self._unlock_canal(canal, interaction.guild, interaction.user)
                abiertos += 1

        embed = discord.Embed(
            title="🔓 LOCKDOWN LEVANTADO",
            description=f"**{abiertos}** canales han sido abiertos nuevamente.",
            color=0x57F287,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Moderador", value=interaction.user.mention, inline=True)
        embed.set_footer(text="Sistema de lockdown · PFA")
        await interaction.channel.send(embed=embed)

        await interaction.followup.send(
            f"✅ Lockdown levantado en **{abiertos}** canales.", ephemeral=True
        )

    # ------------------------------------------------------------------
    # Manejo de errores
    # ------------------------------------------------------------------
    @lock.error
    @unlock.error
    @lockdown.error
    @unlockdown.error
    async def lockdown_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "No tenés permiso para gestionar canales."
        else:
            msg = "Ocurrió un error al ejecutar el comando."

        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------
    async def _lock_canal(self, canal: discord.TextChannel, moderador: discord.Member) -> None:
        cambios = []
        for target in self._obtener_targets_lock(canal):
            overwrite = canal.overwrites_for(target)
            cambios.append(self._serializar_overwrite(target, overwrite.send_messages))
            overwrite.send_messages = False
            await canal.set_permissions(
                target,
                overwrite=overwrite,
                reason=f"Lockdown por {moderador} ({moderador.id})",
            )
        self.lockdowns[str(canal.id)] = cambios
        self._guardar_lockdowns()

    async def _unlock_canal(
        self, canal: discord.TextChannel, guild: discord.Guild, moderador: discord.Member
    ) -> None:
        cambios = self.lockdowns.pop(str(canal.id), [])
        for cambio in cambios:
            target = self._obtener_target_guardado(guild, cambio)
            if target is None:
                continue
            overwrite = canal.overwrites_for(target)
            overwrite.send_messages = cambio["send_messages"]
            # Si el overwrite quedó completamente vacío, lo eliminamos para no dejar basura
            if overwrite.is_empty():
                await canal.set_permissions(
                    target,
                    overwrite=None,
                    reason=f"Unlock por {moderador} ({moderador.id})",
                )
            else:
                await canal.set_permissions(
                    target,
                    overwrite=overwrite,
                    reason=f"Unlock por {moderador} ({moderador.id})",
                )
        self._guardar_lockdowns()

    def _obtener_targets_lock(self, canal: discord.TextChannel) -> list:
        """Retorna todos los roles/miembros no-admin que pueden escribir en el canal."""
        targets = [canal.guild.default_role]
        agregados = {canal.guild.default_role.id}

        for rol in canal.guild.roles:
            if rol.id in agregados or rol.permissions.administrator:
                continue
            permisos = canal.permissions_for(rol)
            if permisos.view_channel and permisos.send_messages:
                targets.append(rol)
                agregados.add(rol.id)

        for target in canal.overwrites:
            if isinstance(target, discord.Member):
                permisos = canal.permissions_for(target)
                if permisos.administrator or target.id in agregados:
                    continue
                targets.append(target)
                agregados.add(target.id)

        return targets

    def _serializar_overwrite(self, target, send_messages) -> dict:
        return {
            "type": "role" if isinstance(target, discord.Role) else "member",
            "id": target.id,
            "send_messages": send_messages,
        }

    def _obtener_target_guardado(self, guild: discord.Guild, cambio: dict):
        if cambio["type"] == "role":
            return guild.get_role(cambio["id"])
        return guild.get_member(cambio["id"])

    def _cargar_lockdowns(self) -> dict:
        if not LOCKDOWN_STATE_PATH.exists():
            return {}
        try:
            with LOCKDOWN_STATE_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _guardar_lockdowns(self) -> None:
        with LOCKDOWN_STATE_PATH.open("w", encoding="utf-8") as f:
            json.dump(self.lockdowns, f, indent=2)


async def setup(bot):
    await bot.add_cog(Lockdown(bot))
