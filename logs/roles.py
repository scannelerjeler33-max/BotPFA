import asyncio
import datetime
import os
import re

import discord
from discord.ext import commands
from dotenv import load_dotenv
from utils.config import obtener_config_int

load_dotenv()


# Canales donde se enviaran los logs de cambios de roles.
# CANAL_LOGS_ROLES_ID queda como respaldo si no configuras los separados.
# CANAL_LOGS_ROLES_USUARIOS_ID: cambios hechos por usuarios/staff.
# CANAL_LOGS_ROLES_BOTS_ID: cambios hechos por bots.
CANAL_LOGS_ROLES_ID = int(os.getenv("CANAL_LOGS_ROLES_ID", "0") or 0)
CANAL_LOGS_ROLES_USUARIOS_ID = int(os.getenv("CANAL_LOGS_ROLES_USUARIOS_ID", "0") or 0)
CANAL_LOGS_ROLES_BOTS_ID = int(os.getenv("CANAL_LOGS_ROLES_BOTS_ID", "0") or 0)
PROPIETARIO_LOGS_ID = int(os.getenv("PROPIETARIO_LOGS_ID", "0") or 0)

TITULO_ROLES_AGREGADOS = "\u2795 Roles agregados"
TITULO_ROLES_QUITADOS = "\u2796 Roles quitados"


class LogsRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Backup de logs enviados (para detectar borrados)
        self.logs_guardados = {}
        # Set de audit entry IDs ya procesados (nunca se re-envian)
        self._audit_ids_procesados = set()
        # Timestamp del ultimo audit ID procesado para limpieza
        self._audit_ids_timestamps = {}

    @commands.Cog.listener()
    async def on_ready(self):
        print("[Logs] Roles cargado.")

    # ------------------------------------------------------------------ #
    #  UNICA FUENTE DE DETECCION: on_member_update                        #
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles == after.roles:
            return

        roles_agregados = self._ordenar_roles(set(after.roles) - set(before.roles))
        roles_quitados = self._ordenar_roles(set(before.roles) - set(after.roles))
        if not roles_agregados and not roles_quitados:
            return

        # Buscar en audit log QUIEN hizo el cambio (no para detectar el cambio)
        entrada_audit = await self._buscar_entrada_audit(
            guild=after.guild,
            miembro=after,
            roles_agregados=roles_agregados,
            roles_quitados=roles_quitados,
        )

        # Si tenemos audit log y ya procesamos este entry ID, ignorar (duplicado)
        if entrada_audit is not None:
            if entrada_audit.id in self._audit_ids_procesados:
                return
            self._audit_ids_procesados.add(entrada_audit.id)
            self._audit_ids_timestamps[entrada_audit.id] = discord.utils.utcnow()
            self._limpiar_audit_ids()

        # Si tiene permiso de audit log pero no encontro entrada, descartar
        if after.guild.me.guild_permissions.view_audit_log and entrada_audit is None:
            return

        administrador = entrada_audit.user if entrada_audit is not None else None
        canal_logs = self._obtener_canal_logs_roles(after.guild, administrador)
        if canal_logs is None:
            return

        await self._enviar_logs_roles(
            canal_logs=canal_logs,
            miembro=after,
            administrador=administrador,
            roles_agregados=roles_agregados,
            roles_quitados=roles_quitados,
        )

    # ------------------------------------------------------------------ #
    #  PROTECCION: Detectar si alguien borra un log                       #
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None:
            return
        if message.channel.id not in self._obtener_ids_canales_logs_roles(message.guild):
            return
        if message.author.id != self.bot.user.id:
            return

        propietario = await self._obtener_propietario_logs(message.guild)
        if propietario is None:
            return

        administrador = await self._buscar_eliminador_log(message)

        embed_alerta = discord.Embed(
            title="Log eliminado",
            color=0xE53E3E,
            timestamp=discord.utils.utcnow(),
        )
        embed_alerta.add_field(
            name="Canal",
            value=f"{message.channel.mention}\n`{message.channel.id}`",
            inline=True,
        )
        embed_alerta.add_field(
            name="Administrador",
            value=self._formatear_administrador(administrador),
            inline=True,
        )
        embed_alerta.set_footer(text=f"Mensaje eliminado: {message.id}")

        try:
            await propietario.send(embed=embed_alerta)
            embed_snapshot = self._crear_snapshot_log_eliminado(message)
            if embed_snapshot is not None:
                await propietario.send(embed=embed_snapshot)
        except discord.Forbidden:
            pass

    # ------------------------------------------------------------------ #
    #  ENVIAR LOGS                                                        #
    # ------------------------------------------------------------------ #
    async def _enviar_logs_roles(self, canal_logs, miembro, administrador, roles_agregados, roles_quitados):
        origen = self._obtener_origen_administrador(administrador)

        if roles_agregados:
            embed_agregados = self._crear_embed_roles(
                titulo=TITULO_ROLES_AGREGADOS,
                color=0x38A169,
                miembro=miembro,
                administrador=administrador,
                roles=roles_agregados,
                origen=origen,
            )
            mensaje = await canal_logs.send(embed=embed_agregados)
            self._guardar_log(
                mensaje,
                titulo=TITULO_ROLES_AGREGADOS,
                color=0x38A169,
                miembro=miembro,
                administrador=administrador,
                roles=roles_agregados,
                origen=origen,
            )

        if roles_quitados:
            embed_quitados = self._crear_embed_roles(
                titulo=TITULO_ROLES_QUITADOS,
                color=0xE53E3E,
                miembro=miembro,
                administrador=administrador,
                roles=roles_quitados,
                origen=origen,
            )
            mensaje = await canal_logs.send(embed=embed_quitados)
            self._guardar_log(
                mensaje,
                titulo=TITULO_ROLES_QUITADOS,
                color=0xE53E3E,
                miembro=miembro,
                administrador=administrador,
                roles=roles_quitados,
                origen=origen,
            )

    # ------------------------------------------------------------------ #
    #  BUSCAR EN AUDIT LOG (solo para identificar al admin)               #
    # ------------------------------------------------------------------ #
    async def _buscar_entrada_audit(self, guild, miembro, roles_agregados, roles_quitados):
        if not guild.me.guild_permissions.view_audit_log:
            return None

        # Esperamos un momento para que Discord registre la entrada en el audit log
        await asyncio.sleep(0.5)

        ahora = discord.utils.utcnow()
        try:
            async for entrada in guild.audit_logs(
                limit=10,
                action=discord.AuditLogAction.member_role_update,
            ):
                # Solo entradas de los ultimos 30 segundos
                if ahora - entrada.created_at > datetime.timedelta(seconds=30):
                    break

                # Debe ser sobre el mismo usuario
                if not entrada.target or entrada.target.id != miembro.id:
                    continue

                # Verificar que los roles coincidan
                if self._entrada_audit_coincide(entrada, roles_agregados, roles_quitados):
                    return entrada
        except (discord.Forbidden, discord.HTTPException):
            return None

        return None

    async def _buscar_eliminador_log(self, message: discord.Message):
        if not message.guild.me.guild_permissions.view_audit_log:
            return None

        for _ in range(6):
            await asyncio.sleep(1)
            ahora = discord.utils.utcnow()

            try:
                async for entrada in message.guild.audit_logs(
                    limit=12,
                    action=discord.AuditLogAction.message_delete,
                ):
                    if ahora - entrada.created_at > datetime.timedelta(seconds=45):
                        continue

                    canal_audit = getattr(entrada.extra, "channel", None)
                    if canal_audit and canal_audit.id != message.channel.id:
                        continue

                    if entrada.target and entrada.target.id != message.author.id:
                        continue

                    return entrada.user
            except (discord.Forbidden, discord.HTTPException):
                return None

        return None

    async def _obtener_propietario_logs(self, guild):
        propietario_id = obtener_config_int(guild.id, "PROPIETARIO_LOGS_ID", PROPIETARIO_LOGS_ID)
        if propietario_id:
            usuario = self.bot.get_user(propietario_id)
            if usuario is not None:
                return usuario
            try:
                return await self.bot.fetch_user(propietario_id)
            except (discord.NotFound, discord.HTTPException):
                return None

        try:
            app_info = await self.bot.application_info()
        except discord.HTTPException:
            return None

        return app_info.owner

    # ------------------------------------------------------------------ #
    #  EMBEDS Y FORMATEO                                                  #
    # ------------------------------------------------------------------ #
    def _crear_embed_roles(self, titulo, color, miembro, administrador, roles, origen):
        embed = discord.Embed(
            title=titulo,
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="Usuario",
            value=self._formatear_usuario(miembro),
            inline=True,
        )
        embed.add_field(
            name="Administrador",
            value=self._formatear_administrador(administrador),
            inline=True,
        )
        embed.add_field(
            name="Origen",
            value=origen,
            inline=True,
        )
        embed.add_field(
            name="Roles",
            value=self._formatear_roles(roles),
            inline=False,
        )
        embed.set_footer(text="Sistema de logs - Roles")
        return embed

    def _guardar_log(self, mensaje, titulo, color, miembro, administrador, roles, origen):
        self.logs_guardados[mensaje.id] = {
            "titulo": titulo,
            "color": color,
            "usuario": self._formatear_usuario(miembro),
            "administrador": self._formatear_administrador(administrador),
            "origen": origen,
            "roles": self._formatear_roles_texto(roles),
            "fecha": discord.utils.utcnow(),
        }

        if len(self.logs_guardados) > 300:
            mensaje_mas_viejo = next(iter(self.logs_guardados))
            self.logs_guardados.pop(mensaje_mas_viejo, None)

    def _crear_snapshot_log_eliminado(self, message):
        log_guardado = self.logs_guardados.pop(message.id, None)

        if log_guardado is not None:
            embed = discord.Embed(
                title=f"Copia del log: {log_guardado['titulo']}",
                color=log_guardado["color"],
                timestamp=log_guardado["fecha"],
            )
            embed.add_field(name="Usuario", value=log_guardado["usuario"], inline=True)
            embed.add_field(name="Administrador", value=log_guardado["administrador"], inline=True)
            embed.add_field(name="Origen", value=log_guardado["origen"], inline=True)
            embed.add_field(name="Roles", value=log_guardado["roles"], inline=False)
            embed.set_footer(text="Copia guardada antes de la eliminacion")
            return embed

        if not message.embeds:
            return None

        embed_original = message.embeds[0]
        embed = discord.Embed(
            title=f"Copia del log: {embed_original.title or 'Log'}",
            color=embed_original.color or discord.Color.red(),
            timestamp=embed_original.timestamp or discord.utils.utcnow(),
        )

        for field in embed_original.fields:
            valor = self._limpiar_menciones_roles(message.guild, field.value)
            embed.add_field(name=field.name, value=valor, inline=field.inline)

        embed.set_footer(text="Copia reconstruida del mensaje eliminado")
        return embed

    # ------------------------------------------------------------------ #
    #  UTILIDADES                                                         #
    # ------------------------------------------------------------------ #
    def _entrada_audit_coincide(self, entrada, roles_agregados, roles_quitados):
        roles_audit_agregados = self._extraer_roles_audit(entrada.after)
        roles_audit_quitados = self._extraer_roles_audit(entrada.before)
        return (
            self._crear_ids_roles(roles_audit_agregados) == self._crear_ids_roles(roles_agregados)
            and self._crear_ids_roles(roles_audit_quitados) == self._crear_ids_roles(roles_quitados)
        )

    def _extraer_roles_audit(self, diff):
        roles = getattr(diff, "roles", None) or []
        return self._ordenar_roles(roles)

    def _ordenar_roles(self, roles):
        return sorted(
            roles,
            key=lambda rol: getattr(rol, "position", 0),
            reverse=True,
        )

    def _formatear_usuario(self, usuario):
        if usuario is None:
            return "No encontrado"
        return f"{usuario.mention}\n`{usuario.id}`"

    def _formatear_administrador(self, administrador):
        if administrador is None:
            return "No encontrado\n`Revisar permiso Ver registro de auditoria`"
        return f"{administrador.mention}\n`{administrador.id}`"

    def _obtener_origen_administrador(self, administrador):
        if administrador is None:
            return "No encontrado"
        return "Bot" if administrador.bot else "Usuario"

    def _obtener_canal_logs_roles(self, guild, administrador):
        canal_base_id = obtener_config_int(guild.id, "CANAL_LOGS_ROLES_ID", CANAL_LOGS_ROLES_ID)
        canal_usuarios_id = obtener_config_int(guild.id, "CANAL_LOGS_ROLES_USUARIOS_ID", CANAL_LOGS_ROLES_USUARIOS_ID)
        canal_bots_id = obtener_config_int(guild.id, "CANAL_LOGS_ROLES_BOTS_ID", CANAL_LOGS_ROLES_BOTS_ID)

        canal_id = canal_usuarios_id or canal_base_id
        if administrador is not None and administrador.bot:
            canal_id = canal_bots_id or canal_base_id

        if not canal_id:
            return None
        return guild.get_channel(canal_id)

    def _obtener_ids_canales_logs_roles(self, guild):
        canal_base_id = obtener_config_int(guild.id, "CANAL_LOGS_ROLES_ID", CANAL_LOGS_ROLES_ID)
        canal_usuarios_id = obtener_config_int(guild.id, "CANAL_LOGS_ROLES_USUARIOS_ID", CANAL_LOGS_ROLES_USUARIOS_ID)
        canal_bots_id = obtener_config_int(guild.id, "CANAL_LOGS_ROLES_BOTS_ID", CANAL_LOGS_ROLES_BOTS_ID)
        return {canal_id for canal_id in (canal_base_id, canal_usuarios_id, canal_bots_id) if canal_id}

    def _formatear_roles(self, roles):
        if not roles:
            return "Ninguno"
        return "\n".join(f"{rol.mention} (`{rol.id}`)" for rol in roles)

    def _formatear_roles_texto(self, roles):
        if not roles:
            return "Ninguno"
        return "\n".join(f"@{rol.name} (`{rol.id}`)" for rol in roles)

    def _limpiar_menciones_roles(self, guild, texto):
        if not texto:
            return "Sin datos"

        def reemplazar(match):
            rol_id = int(match.group(1))
            rol = guild.get_role(rol_id) if guild else None
            if rol is None:
                return f"@rol-eliminado (`{rol_id}`)"
            return f"@{rol.name} (`{rol.id}`)"

        return re.sub(r"<@&(\d+)>", reemplazar, texto)

    def _crear_ids_roles(self, roles):
        return tuple(sorted(rol.id for rol in roles))

    def _limpiar_audit_ids(self):
        """Limpiar audit IDs mas viejos de 2 horas para no acumular memoria."""
        ahora = discord.utils.utcnow()
        vencidos = [
            entry_id
            for entry_id, ts in self._audit_ids_timestamps.items()
            if ahora - ts > datetime.timedelta(hours=2)
        ]
        for entry_id in vencidos:
            self._audit_ids_procesados.discard(entry_id)
            self._audit_ids_timestamps.pop(entry_id, None)


async def setup(bot):
    await bot.add_cog(LogsRoles(bot))
