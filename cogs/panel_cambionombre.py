import discord
from discord.ext import commands
from discord import app_commands
from databases.connection import get_connection
import datetime
from utils.config import obtener_config_int, obtener_config_list

# ═══════════════════════════════════════════════════════════════════
#  PANEL DE CAMBIO DE NOMBRE — P.F.A
#  Sistema de solicitud y aprobación de cambio de nombre para oficiales
# ═══════════════════════════════════════════════════════════════════

# --- CONFIGURACIÓN ---
# Canal donde se envían las solicitudes para ser aprobadas/rechazadas
CANAL_APROBACION_NOMBRE_ID = 1389094522029477889

# Roles que pueden APROBAR o RECHAZAR los cambios de nombre
ROLES_APROBAR_NOMBRE = [1403933697576538173, 1448829419715297330, 1461995989446557777]

# Roles que pueden SOLICITAR el cambio de nombre (oficiales PFA)
ROLES_PERMITIDOS_NOMBRE = [1393678701408817284]

# Roles administrativos (Staff)
ROLES_ADMIN_STAFF = [1351228669359558809, 1390055851657789481, 1411483502142029866]

# --- BASE DE DATOS ---
db_nombres = None
cursor_nombres = None


def obtener_cursor_nombres():
    global db_nombres, cursor_nombres

    if db_nombres is None or db_nombres.closed:
        db_nombres = get_connection()
        cursor_nombres = db_nombres.cursor()
        sincronizar_secuencia_historial_nombres()

    return db_nombres, cursor_nombres


def sincronizar_secuencia_historial_nombres():
    cursor_nombres.execute(
        """
        SELECT setval(
            pg_get_serial_sequence(%s, %s),
            COALESCE((SELECT MAX(id) FROM historial_nombres), 0) + 1,
            false
        )
        """,
        ("historial_nombres", "id"),
    )
    db_nombres.commit()


def registrar_historial_nombre(user_id, nombre_anterior, nombre_nuevo, placa, estado, procesado_por, motivo):
    db, cur = obtener_cursor_nombres()
    cur.execute(
        "INSERT INTO historial_nombres (user_id, nombre_anterior, nombre_nuevo, placa, estado, procesado_por, motivo, fecha) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (user_id, nombre_anterior, nombre_nuevo, placa, estado, procesado_por, motivo, discord.utils.utcnow().strftime("%Y-%m-%d %H:%M"))
    )
    db.commit()


# ═══════════════════════════════════════════════════════════════════
#  MODAL: FORMULARIO DE CAMBIO DE NOMBRE
# ═══════════════════════════════════════════════════════════════════

class ModalCambioNombre(discord.ui.Modal, title="📝 Cambio de Nombre — P.F.A"):
    nombre_apellido = discord.ui.TextInput(
        label="Nombre y Apellido",
        placeholder="Ej: Santiago Pérez (NO TROLL)",
        min_length=3,
        max_length=50,
        required=True,
        style=discord.TextStyle.short
    )
    placa = discord.ui.TextInput(
        label="Placa (máximo 4 dígitos)",
        placeholder="Ej: 1234",
        min_length=1,
        max_length=4,
        required=True,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        # --- Validar que la placa sean solo números ---
        if not self.placa.value.isdigit():
            return await interaction.response.send_message(
                "❌ **Error:** La placa debe contener únicamente números (máximo 4 dígitos).",
                ephemeral=True
            )

        # --- Formatear el nombre resultante ---
        nombre_final = f"{self.nombre_apellido.value.strip()} - {self.placa.value.strip()}"

        # --- Buscar el canal de aprobación ---
        canal_aprobacion_id = obtener_config_int(interaction.guild.id, "CANAL_APROBACION_NOMBRE_ID", CANAL_APROBACION_NOMBRE_ID)
        canal_aprobacion = interaction.guild.get_channel(canal_aprobacion_id)
        if not canal_aprobacion:
            return await interaction.response.send_message(
                "❌ **Error interno:** El canal de aprobación no está configurado. Contacta a un administrador.",
                ephemeral=True
            )

        # --- EMBED DE SOLICITUD (enviado al canal de aprobación) ---
        embed_solicitud = discord.Embed(
            title="📋  Solicitud de Cambio de Nombre",
            color=0x2B6CB0,
            timestamp=discord.utils.utcnow()
        )

        embed_solicitud.description = (
            f"Un oficial ha solicitado actualizar su nombre en el servidor.\n"
            f"Revise los datos a continuación y tome una decisión.\n\n"
            f"**Oficial solicitante**\n"
            f"{interaction.user.mention} · `{interaction.user.id}`\n\n"
            f"**Nombre actual**\n"
            f"`{interaction.user.display_name}`\n\n"
            f"**Nuevo nombre solicitado**\n"
            f"`{nombre_final}`\n\n"
            f"**Placa**\n"
            f"`{self.placa.value.strip()}`"
        )

        embed_solicitud.set_thumbnail(url=interaction.user.display_avatar.url)

        # Footer con datos codificados para la aprobación
        embed_solicitud.set_footer(text=f"ID:{interaction.user.id}|NOMBRE:{nombre_final}")

        # --- Enviar al canal de aprobación ---
        await canal_aprobacion.send(embed=embed_solicitud, view=ViewAprobarNombre())

        # --- Confirmación al usuario ---
        embed_confirmacion = discord.Embed(
            title="✅  Solicitud Enviada",
            description=(
                f"Tu solicitud de cambio de nombre ha sido enviada correctamente.\n\n"
                f"📛 **Nombre solicitado:** `{nombre_final}`\n\n"
                f"Un superior revisará tu solicitud y serás notificado\n"
                f"por **mensaje directo** cuando sea procesada."
            ),
            color=0x2B6CB0
        )
        embed_confirmacion.set_footer(text="Equipo Administrativo — P.F.A")

        await interaction.response.send_message(embed=embed_confirmacion, ephemeral=True)


# ═══════════════════════════════════════════════════════════════════
#  MODAL: MOTIVO DE RECHAZO
# ═══════════════════════════════════════════════════════════════════

class ModalMotivoRechazo(discord.ui.Modal, title="❌ Motivo del Rechazo"):
    motivo = discord.ui.TextInput(
        label="¿Por qué se rechaza esta solicitud?",
        placeholder="Ej: Nombre no coincide con el IC, placa incorrecta...",
        style=discord.TextStyle.paragraph,
        min_length=5,
        max_length=500,
        required=True
    )

    def __init__(self, mensaje_original: discord.Message):
        super().__init__()
        self.mensaje_original = mensaje_original

    async def on_submit(self, interaction: discord.Interaction):
        embed_original = self.mensaje_original.embeds[0]

        # --- Extraer datos del footer ---
        try:
            footer_data = embed_original.footer.text.split("|")
            user_id = int(footer_data[0].split(":")[1])
            nombre_final = footer_data[1].split(":", 1)[1]
        except (IndexError, ValueError):
            return await interaction.response.send_message(
                "❌ Error al procesar los datos de la solicitud.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        # --- Obtener datos del oficial desde el embed original ---
        nombre_actual = ""
        placa = ""

        for field in embed_original.fields:
            if "Nombre actual" in field.name:
                nombre_actual = field.value.strip("`")
            elif "Placa" in field.name:
                placa = field.value.strip("`")

        # --- EMBED DE REGISTRO: DENEGADO ---
        embed_registro = discord.Embed(
            title="❌  Cambio de Nombre Denegado",
            color=0xE53E3E,
            timestamp=discord.utils.utcnow()
        )

        nombre_actual_str = f"`{nombre_actual}`" if nombre_actual else "*No disponible*"
        placa_str = f"`{placa}`" if placa else "*No disponible*"

        embed_registro.description = (
            f"La siguiente solicitud de cambio de nombre fue **rechazada**.\n\n"
            f"**Oficial**\n"
            f"<@{user_id}> · `{user_id}`\n\n"
            f"**Nombre actual**\n"
            f"{nombre_actual_str}\n\n"
            f"**Nombre solicitado**\n"
            f"`{nombre_final}`\n\n"
            f"**Placa**\n"
            f"{placa_str}\n\n"
            f"**Rechazado por**\n"
            f"{interaction.user.mention}\n\n"
            f"**Motivo**\n"
            f"{self.motivo.value}"
        )

        if embed_original.thumbnail:
            embed_registro.set_thumbnail(url=embed_original.thumbnail.url)

        embed_registro.set_footer(text="Estado: Procesado (Rechazado)")

        await self.mensaje_original.edit(embed=embed_registro, view=None)

        # --- Registrar en base de datos ---
        registrar_historial_nombre(
            user_id=user_id,
            nombre_anterior=nombre_actual,
            nombre_nuevo=nombre_final,
            placa=placa,
            estado="rechazado",
            procesado_por=interaction.user.id,
            motivo=self.motivo.value,
        )

        # --- Notificar al usuario por MD ---
        miembro = interaction.guild.get_member(user_id)
        if miembro:
            try:
                embed_dm = discord.Embed(
                    title="❌ SOLICITUD DE CAMBIO DE NOMBRE RECHAZADA",
                    description="Hola. Te informamos que tu solicitud de cambio de nombre ha sido **rechazada** por la administración.",
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow()
                )
                embed_dm.set_author(name="Policía Federal Argentina - Ibiza Roleplay", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                embed_dm.add_field(name="📛 Nombre Solicitado", value=f"`{nombre_final}`", inline=True)
                embed_dm.add_field(name="👮 Procesado por", value=f"{interaction.user.mention} (`{interaction.user.display_name}`)", inline=True)
                embed_dm.add_field(name="📝 Motivo del Rechazo", value=self.motivo.value, inline=False)
                embed_dm.set_thumbnail(url=miembro.display_avatar.url)
                embed_dm.set_footer(text="Equipo Administrativo — P.F.A")
                await miembro.send(embed=embed_dm)
            except discord.Forbidden:
                pass

        await interaction.followup.send(
            f"❌ Cambio de nombre **rechazado** para <@{user_id}>.",
            ephemeral=True
        )


# ═══════════════════════════════════════════════════════════════════
#  VIEW: BOTONES DE APROBACIÓN / RECHAZO
# ═══════════════════════════════════════════════════════════════════

class ViewAprobarNombre(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Aprobar", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_aprobar_nombre_v1")
    async def btn_aprobar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # --- Verificar permisos ---
        roles_aprobar_nombre = obtener_config_list(interaction.guild.id, "ROLES_APROBAR_NOMBRE", ROLES_APROBAR_NOMBRE)
        tiene_permiso = any(rol.id in roles_aprobar_nombre for rol in interaction.user.roles)
        if not tiene_permiso:
            return await interaction.response.send_message(
                "⛔ **Acceso Denegado:** No tienes permiso para aprobar cambios de nombre.",
                ephemeral=True
            )

        # --- Verificar si ya fue procesado ---
        embed = interaction.message.embeds[0]
        if "Procesado" in (embed.footer.text or ""):
            return await interaction.response.send_message(
                "⚠️ Esta solicitud ya fue procesada anteriormente.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        # --- Extraer datos del footer ---
        try:
            footer_data = embed.footer.text.split("|")
            user_id = int(footer_data[0].split(":")[1])
            nombre_final = footer_data[1].split(":", 1)[1]
        except (IndexError, ValueError):
            return await interaction.followup.send(
                "❌ Error al procesar los datos de la solicitud.",
                ephemeral=True
            )

        # --- Cambiar el nombre del usuario ---
        miembro = interaction.guild.get_member(user_id)
        nombre_cambiado = False

        if miembro:
            try:
                await miembro.edit(nick=nombre_final)
                nombre_cambiado = True
            except discord.Forbidden:
                pass
            except Exception as e:
                print(f"Error al cambiar nombre: {e}")

        # --- Obtener datos del embed original ---
        nombre_actual = ""
        placa = ""

        for field in embed.fields:
            if "Nombre actual" in field.name:
                nombre_actual = field.value.strip("`")
            elif "Placa" in field.name:
                placa = field.value.strip("`")

        # --- EMBED DE REGISTRO: APROBADO ---
        embed_registro = discord.Embed(
            title="✅  Cambio de Nombre Aprobado",
            color=0x38A169,
            timestamp=discord.utils.utcnow()
        )

        nombre_actual_str = f"`{nombre_actual}`" if nombre_actual else "*No disponible*"
        placa_str = f"`{placa}`" if placa else "*No disponible*"
        estado_nick = "Aplicado exitosamente ✅" if nombre_cambiado else "No se pudo aplicar automáticamente (jerarquía insuficiente) ⚠️"

        embed_registro.description = (
            f"La siguiente solicitud de cambio de nombre fue **aprobada**.\n\n"
            f"**Oficial**\n"
            f"<@{user_id}> · `{user_id}`\n\n"
            f"**Nombre anterior**\n"
            f"{nombre_actual_str}\n\n"
            f"**Nuevo nombre**\n"
            f"`{nombre_final}`\n\n"
            f"**Placa**\n"
            f"{placa_str}\n\n"
            f"**Autorizado por**\n"
            f"{interaction.user.mention}\n\n"
            f"**Estado**\n"
            f"{estado_nick}"
        )

        if embed.thumbnail:
            embed_registro.set_thumbnail(url=embed.thumbnail.url)

        embed_registro.set_footer(text="Estado: Procesado (Aprobado)")

        await interaction.message.edit(embed=embed_registro, view=None)

        # --- Registrar en base de datos ---
        registrar_historial_nombre(
            user_id=user_id,
            nombre_anterior=nombre_actual,
            nombre_nuevo=nombre_final,
            placa=placa,
            estado="aprobado",
            procesado_por=interaction.user.id,
            motivo=None,
        )

        # --- Notificar al usuario por MD ---
        if miembro:
            try:
                embed_dm = discord.Embed(
                    title="✅ SOLICITUD DE CAMBIO DE NOMBRE APROBADA",
                    description="Hola. Te informamos que tu solicitud de cambio de nombre ha sido **aprobada** por la administración y ya está vigente.",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                embed_dm.set_author(name="Policía Federal Argentina - Ibiza Roleplay", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                embed_dm.add_field(name="📛 Nuevo Nombre", value=f"`{nombre_final}`", inline=True)
                embed_dm.add_field(name="👮 Autorizado por", value=f"{interaction.user.mention} (`{interaction.user.display_name}`)", inline=True)
                
                estado_aplicado = "✅ El cambio ya fue aplicado en el servidor." if nombre_cambiado else "⚠️ El nombre no se pudo cambiar automáticamente debido a jerarquía de roles. Por favor, solicita a un superior que te lo coloque manualmente."
                embed_dm.add_field(name="📌 Estado del Servidor", value=estado_aplicado, inline=False)
                
                embed_dm.set_thumbnail(url=miembro.display_avatar.url)
                embed_dm.set_footer(text="Equipo Administrativo — P.F.A")
                await miembro.send(embed=embed_dm)
            except discord.Forbidden:
                pass

        await interaction.followup.send(
            f"✅ Cambio de nombre **aprobado** para <@{user_id}>. " +
            ("El nombre fue cambiado exitosamente." if nombre_cambiado else "⚠️ No se pudo cambiar el nombre automáticamente."),
            ephemeral=True
        )

    @discord.ui.button(label="Rechazar", style=discord.ButtonStyle.danger, emoji="❌", custom_id="btn_rechazar_nombre_v1")
    async def btn_rechazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # --- Verificar permisos ---
        roles_aprobar_nombre = obtener_config_list(interaction.guild.id, "ROLES_APROBAR_NOMBRE", ROLES_APROBAR_NOMBRE)
        tiene_permiso = any(rol.id in roles_aprobar_nombre for rol in interaction.user.roles)
        if not tiene_permiso:
            return await interaction.response.send_message(
                "⛔ **Acceso Denegado:** No tienes permiso para rechazar cambios de nombre.",
                ephemeral=True
            )

        # --- Verificar si ya fue procesado ---
        embed = interaction.message.embeds[0]
        if "Procesado" in (embed.footer.text or ""):
            return await interaction.response.send_message(
                "⚠️ Esta solicitud ya fue procesada anteriormente.",
                ephemeral=True
            )

        # --- Abrir modal pidiendo el motivo del rechazo ---
        await interaction.response.send_modal(ModalMotivoRechazo(mensaje_original=interaction.message))


# ═══════════════════════════════════════════════════════════════════
#  VIEW: PANEL PRINCIPAL (Botón "Cambiar mi nombre")
# ═══════════════════════════════════════════════════════════════════

class ViewPanelCambioNombre(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Cambiar mi nombre",
        style=discord.ButtonStyle.primary,
        emoji="✏️",
        custom_id="btn_cambiar_nombre_v1"
    )
    async def btn_cambiar_nombre(self, interaction: discord.Interaction, button: discord.ui.Button):
        # --- Verificar rol ---
        roles_permitidos_nombre = obtener_config_list(interaction.guild.id, "ROLES_PERMITIDOS_NOMBRE", ROLES_PERMITIDOS_NOMBRE)
        roles_admin_staff = obtener_config_list(interaction.guild.id, "ROLES_ADMIN_STAFF", ROLES_ADMIN_STAFF)
        tiene_rol = any(rol.id in roles_permitidos_nombre for rol in interaction.user.roles)
        es_staff = any(rol.id in roles_admin_staff for rol in interaction.user.roles)

        if not tiene_rol and not es_staff:
            return await interaction.response.send_message(
                "⛔ **Acceso Denegado:** No tienes el rango necesario para solicitar un cambio de nombre.",
                ephemeral=True
            )

        # --- Abrir el formulario ---
        try:
            await interaction.response.send_modal(ModalCambioNombre())
        except Exception as exc:
            print(f"Error al abrir modal de cambio de nombre: {exc}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ No se pudo abrir el formulario de cambio de nombre. Contacta a un administrador.",
                    ephemeral=True,
                )


# ═══════════════════════════════════════════════════════════════════
#  COG: EXTENSIÓN DEL BOT
# ═══════════════════════════════════════════════════════════════════

class CambioNombreCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Registrar vistas persistentes
        self.bot.add_view(ViewPanelCambioNombre())
        self.bot.add_view(ViewAprobarNombre())
        print("✅ Panel de Cambio de Nombre: Vistas persistentes registradas.")

    @app_commands.command(name="panelcambionombre", description="Despliega el panel para solicitar cambio de nombre de oficial.")
    async def panelcambionombre(self, interaction: discord.Interaction):
        es_staff = interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator
        roles_admin_staff = obtener_config_list(interaction.guild.id, "ROLES_ADMIN_STAFF", ROLES_ADMIN_STAFF)
        if not (es_staff or any(r.id in roles_admin_staff for r in interaction.user.roles)):
            return await interaction.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)

        # --- EMBED PRINCIPAL DEL PANEL ---
        embed = discord.Embed(
            color=0x2B6CB0,
            timestamp=discord.utils.utcnow()
        )

        embed.description = (
            "## Cambio de Nombre — P.F.A\n\n"
            "**¡Hola, oficial!**\n\n"
            "Este panel te permite solicitar un cambio de nombre / cambio de placa en el servidor.\n\n"

            "✏️ **Cambiar mi nombre:** Presiona el botón de abajo para iniciar.\n"
            "📝 **Nombre y Apellido:** Completa tu nombre IC (Corroborar ortografía).\n"
            "🔢 **Placa:** Ingresa tu número de placa (máx. 4 dígitos).\n"
            "⏳ **Aprobación:** Un superior revisará tu solicitud.\n\n"

            "🚨 **Los nombres troll o inapropiados serán rechazados y sancionados.**\n\n"

            "Se te notificará por MD cuando tu solicitud sea procesada."
        )

        embed.set_footer(text="PFA – Ibiza Roleplay")

        await interaction.channel.send(embed=embed, view=ViewPanelCambioNombre())
        await interaction.response.send_message("✅ Panel de Cambio de Nombre desplegado correctamente.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(CambioNombreCog(bot))
