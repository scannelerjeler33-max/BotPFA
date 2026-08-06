import asyncio
import datetime
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv
from utils.config import obtener_config_int

load_dotenv()


# Canal donde se enviaran los logs de voz.
# Configuralo en .env como CANAL_LOGS_VOICE_ID=123456789012345678
CANAL_LOGS_VOICE_ID = int(os.getenv("CANAL_LOGS_VOICE_ID", "0") or 0)


class LogsVoice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.audit_voice_procesados = {}

    @commands.Cog.listener()
    async def on_ready(self):
        print("[Logs] Voice cargado.")

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        canal_logs_id = obtener_config_int(member.guild.id, "CANAL_LOGS_VOICE_ID", CANAL_LOGS_VOICE_ID)
        canal_logs = member.guild.get_channel(canal_logs_id)
        if canal_logs is None:
            return

        if before.channel != after.channel:
            await self._registrar_cambio_canal(canal_logs, member, before, after)

        cambios_staff = self._obtener_cambios_mute_deafen(before, after)
        if cambios_staff:
            administrador = await self._buscar_administrador(
                member,
                discord.AuditLogAction.member_update,
            )
            await self._enviar_log_mute_deafen(
                canal_logs=canal_logs,
                usuario=member,
                administrador=administrador,
                detalles=cambios_staff,
                canal=after.channel or before.channel,
            )

        self._limpiar_audits_procesados()

    async def _registrar_cambio_canal(self, canal_logs, member, before, after):
        if before.channel is None and after.channel is not None:
            await self._enviar_log_conectar(
                canal_logs=canal_logs,
                usuario=member,
                canal_nuevo=after.channel,
            )
            return

        if before.channel is not None and after.channel is None:
            administrador = await self._buscar_administrador(
                member,
                discord.AuditLogAction.member_disconnect,
                canal_relacionado=before.channel,
            )
            await self._enviar_log_desconectar(
                canal_logs=canal_logs,
                usuario=member,
                administrador=administrador,
                canal_anterior=before.channel,
            )
            return

        administrador = await self._buscar_administrador(
            member,
            discord.AuditLogAction.member_move,
            canal_relacionado=after.channel,
        )
        await self._enviar_log_mover(
            canal_logs=canal_logs,
            usuario=member,
            administrador=administrador,
            canal_anterior=before.channel,
            canal_nuevo=after.channel,
        )

    def _obtener_cambios_mute_deafen(self, before, after):
        cambios = []

        if before.mute != after.mute:
            estado = "muteado" if after.mute else "desmuteado"
            cambios.append(f"Mute de servidor: `{estado}`")

        if before.deaf != after.deaf:
            estado = "ensordecido" if after.deaf else "desensordecido"
            cambios.append(f"Deafen de servidor: `{estado}`")

        return cambios

    async def _buscar_administrador(self, member, accion, canal_relacionado=None):
        if not member.guild.me.guild_permissions.view_audit_log:
            return None

        await asyncio.sleep(1)
        ahora = discord.utils.utcnow()

        try:
            async for entrada in member.guild.audit_logs(limit=12, action=accion):
                if entrada.id in self.audit_voice_procesados:
                    continue
                if ahora - entrada.created_at > datetime.timedelta(seconds=45):
                    continue
                if not self._entrada_audit_coincide(entrada, member, canal_relacionado):
                    continue

                self.audit_voice_procesados[entrada.id] = entrada.created_at
                return entrada.user
        except (discord.Forbidden, discord.HTTPException):
            return None

        return None

    def _entrada_audit_coincide(self, entrada, member, canal_relacionado):
        if entrada.user and entrada.user.id == member.id:
            return False

        if entrada.target and getattr(entrada.target, "id", None) == member.id:
            return True

        canal_audit = getattr(entrada.extra, "channel", None)
        if canal_relacionado is not None and canal_audit is not None:
            return canal_audit.id == canal_relacionado.id

        cantidad = getattr(entrada.extra, "count", None)
        return cantidad == 1

    async def _enviar_log_conectar(self, canal_logs, usuario, canal_nuevo):
        embed = self._crear_embed_base("Conectar a canal de voz", 0x38A169)
        embed.add_field(name="Usuario", value=self._formatear_usuario(usuario), inline=True)
        embed.add_field(name="Canal", value=self._formatear_canal(canal_nuevo), inline=False)
        embed.add_field(name="Detalle", value="El usuario entro voluntariamente a un canal de voz.", inline=False)
        await canal_logs.send(embed=embed)

    async def _enviar_log_mover(self, canal_logs, usuario, administrador, canal_anterior, canal_nuevo):
        titulo = "Mover usuario de voz" if administrador else "Cambio de canal de voz"
        detalle = (
            "Un administrador movio al usuario entre canales de voz."
            if administrador
            else "El usuario cambio voluntariamente de canal de voz."
        )

        embed = self._crear_embed_base(titulo, 0x3182CE)
        embed.add_field(name="Usuario", value=self._formatear_usuario(usuario), inline=True)
        if administrador:
            embed.add_field(name="Administrador", value=self._formatear_administrador(administrador), inline=True)
        embed.add_field(
            name="Canales",
            value=self._formatear_transicion_canales(canal_anterior, canal_nuevo),
            inline=False,
        )
        embed.add_field(name="Detalle", value=detalle, inline=False)
        await canal_logs.send(embed=embed)

    async def _enviar_log_mute_deafen(self, canal_logs, usuario, administrador, detalles, canal):
        embed = self._crear_embed_base("Silenciar/deafen actualizado", 0xD69E2E)
        embed.add_field(name="Usuario", value=self._formatear_usuario(usuario), inline=True)
        embed.add_field(name="Administrador", value=self._formatear_administrador(administrador), inline=True)
        embed.add_field(name="Canal", value=self._formatear_canal(canal), inline=False)
        embed.add_field(name="Detalle", value="\n".join(detalles), inline=False)
        await canal_logs.send(embed=embed)

    async def _enviar_log_desconectar(self, canal_logs, usuario, administrador, canal_anterior):
        titulo = "Desconectar de canal de voz" if administrador else "Salida de canal de voz"
        detalle = (
            "Un administrador desconecto al usuario del canal de voz."
            if administrador
            else "El usuario salio voluntariamente del canal de voz."
        )

        embed = self._crear_embed_base(titulo, 0xE53E3E)
        embed.add_field(name="Usuario", value=self._formatear_usuario(usuario), inline=True)
        if administrador:
            embed.add_field(name="Administrador", value=self._formatear_administrador(administrador), inline=True)
        embed.add_field(name="Canal anterior", value=self._formatear_canal(canal_anterior), inline=False)
        embed.add_field(name="Detalle", value=detalle, inline=False)
        await canal_logs.send(embed=embed)

    def _crear_embed_base(self, titulo, color):
        embed = discord.Embed(
            title=titulo,
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="Sistema de logs - Voice")
        return embed

    def _formatear_usuario(self, usuario):
        if usuario is None:
            return "No encontrado"
        return f"{usuario.mention}\n`{usuario.id}`"

    def _formatear_administrador(self, administrador):
        if administrador is None:
            return "No aplica o no encontrado\n`Revisar permiso Ver registro de auditoria`"
        return f"{administrador.mention}\n`{administrador.id}`"

    def _formatear_canal(self, canal):
        if canal is None:
            return "Ninguno"
        return f"{canal.mention}\n`{canal.id}`"

    def _formatear_transicion_canales(self, canal_anterior, canal_nuevo):
        return (
            f"**Canal anterior**\n{self._formatear_canal(canal_anterior)}\n\n"
            f"**Canal nuevo**\n{self._formatear_canal(canal_nuevo)}"
        )

    def _limpiar_audits_procesados(self):
        ahora = discord.utils.utcnow()
        vencidos = [
            entrada_id
            for entrada_id, fecha in self.audit_voice_procesados.items()
            if ahora - fecha > datetime.timedelta(hours=1)
        ]
        for entrada_id in vencidos:
            self.audit_voice_procesados.pop(entrada_id, None)


async def setup(bot):
    await bot.add_cog(LogsVoice(bot))
