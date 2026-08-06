import discord
from discord.ext import commands
from discord import app_commands
import os
from databases.connection import get_connection
import psycopg2
import string
import random
from dotenv import load_dotenv
import datetime
from cogs.panel_farmeo import es_motivo_farmeo, procesar_sancion_farmeo
from utils.config import obtener_config_int, safe_env_int

load_dotenv()

# --- CONFIGURACIÓN VIA .ENV ---
ROL_PANEL_ADMIN_ID = safe_env_int("ROL_PANEL_ADMIN_ID", 0)
ROL_PERMS = safe_env_int("ROL_PERMS", 0)
CANAL_ADVERTENCIAS_ID = safe_env_int("CANAL_ADVERTENCIAS_ID", 0)
CANAL_STRIKES_ID = safe_env_int("CANAL_STRIKES_ID", 0)
CANAL_TICKETS_ID = safe_env_int("CANAL_TICKETS_ID", 0)

# --- BASE DE DATOS (separada de strikes) ---
conn = get_connection()
cur = conn.cursor()


# --- HELPERS ---
def sincronizar_secuencia(tabla, columna="id"):
    if tabla not in {"advertencias_historial"}:
        raise ValueError("Tabla no permitida para sincronizar secuencia.")

    cur.execute(
        f"""
        SELECT setval(
            pg_get_serial_sequence(%s, %s),
            COALESCE((SELECT MAX({columna}) FROM {tabla}), 0) + 1,
            false
        )
        """,
        (tabla, columna),
    )
    conn.commit()


def reparar_secuencias():
    sincronizar_secuencia("advertencias_historial")


reparar_secuencias()


def _ahora_str():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).strftime("%d/%m/%Y, %H:%M:%S")

def generar_warn_id(longitud=13):
    chars = string.ascii_letters + string.digits
    while True:
        nid = ''.join(random.choices(chars, k=longitud))
        cur.execute("SELECT 1 FROM advertencias WHERE warn_id = %s", (nid,))
        if not cur.fetchone():
            return nid

def contar_warns(user_id):
    cur.execute("SELECT COUNT(*) FROM advertencias WHERE user_id = %s", (user_id,))
    return cur.fetchone()[0]

def agregar_warn(user_id, razon, admin_id):
    wid = generar_warn_id()
    fecha = _ahora_str()
    try:
        cur.execute("INSERT INTO advertencias (warn_id, user_id, razon, admin_id, fecha) VALUES (%s,%s,%s,%s,%s)",
                    (wid, user_id, razon, admin_id, fecha))
        cur.execute("INSERT INTO advertencias_historial (warn_id, user_id, razon, admin_id, fecha, accion) VALUES (%s,%s,%s,%s,%s,%s)",
                    (wid, user_id, razon, admin_id, fecha, "AGREGADA"))
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        reparar_secuencias()
        cur.execute("INSERT INTO advertencias (warn_id, user_id, razon, admin_id, fecha) VALUES (%s,%s,%s,%s,%s)",
                    (wid, user_id, razon, admin_id, fecha))
        cur.execute("INSERT INTO advertencias_historial (warn_id, user_id, razon, admin_id, fecha, accion) VALUES (%s,%s,%s,%s,%s,%s)",
                    (wid, user_id, razon, admin_id, fecha, "AGREGADA"))
        conn.commit()
    return wid, contar_warns(user_id), fecha

def eliminar_warn(warn_id, admin_id, motivo):
    cur.execute("SELECT warn_id, user_id, razon, admin_id, fecha FROM advertencias WHERE warn_id = %s", (warn_id,))
    r = cur.fetchone()
    if not r:
        return None
    datos = {"warn_id": r[0], "user_id": r[1], "razon": r[2], "admin_id": r[3], "fecha": r[4]}
    cur.execute("DELETE FROM advertencias WHERE warn_id = %s", (warn_id,))
    fecha = _ahora_str()
    cur.execute("INSERT INTO advertencias_historial (warn_id, user_id, razon, admin_id, fecha, accion, motivo_eliminacion) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (datos["warn_id"], datos["user_id"], datos["razon"], admin_id, fecha, "ELIMINADA", motivo))
    conn.commit()
    datos["warns_restantes"] = contar_warns(datos["user_id"])
    return datos

def buscar_warn(warn_id):
    cur.execute("SELECT warn_id, user_id, razon, admin_id, fecha FROM advertencias WHERE warn_id = %s", (warn_id,))
    r = cur.fetchone()
    if not r:
        return None
    return {"warn_id": r[0], "user_id": r[1], "razon": r[2], "admin_id": r[3], "fecha": r[4]}

def obtener_warns_usuario(user_id):
    cur.execute("SELECT warn_id, razon, admin_id, fecha FROM advertencias WHERE user_id = %s ORDER BY fecha ASC, warn_id ASC", (user_id,))
    return cur.fetchall()

def obtener_historial_warns(user_id):
    cur.execute("SELECT warn_id, razon, admin_id, fecha, accion, motivo_eliminacion FROM advertencias_historial WHERE user_id = %s ORDER BY id ASC", (user_id,))
    return cur.fetchall()

# --- FUNCIÓN PARA AUTO-STRIKE AL LLEGAR A 3 WARNS ---
def _auto_strike(user_id, admin_id, guild_id):
    """Si el usuario tiene 3+ warns, las borra todas y crea 1 strike automático."""
    from cogs.panel_strikes import agregar_strike, CANAL_STRIKES_ID as STRIKES_CH_DEFAULT
    total = contar_warns(user_id)
    if total >= 3:
        # Eliminar las 3 warns del usuario
        cur.execute("SELECT warn_id FROM advertencias WHERE user_id = %s ORDER BY fecha ASC, warn_id ASC LIMIT 3", (user_id,))
        warns_a_borrar = cur.fetchall()
        fecha = _ahora_str()
        for (wid,) in warns_a_borrar:
            cur.execute("DELETE FROM advertencias WHERE warn_id = %s", (wid,))
            cur.execute("INSERT INTO advertencias_historial (warn_id, user_id, razon, admin_id, fecha, accion, motivo_eliminacion) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (wid, user_id, "Auto-convertida a Strike", admin_id, fecha, "CONVERTIDA", "3 advertencias acumuladas"))
        conn.commit()
        # Crear strike automático
        strike_id, total_strikes, fecha_strike = agregar_strike(user_id, "Acumulación de 3 advertencias", admin_id)
        canal_strikes_id = obtener_config_int(guild_id, "CANAL_STRIKES_ID", STRIKES_CH_DEFAULT)
        return strike_id, total_strikes, fecha_strike, canal_strikes_id
    return None


# =====================================================
# MOTIVOS PREDEFINIDOS DE ADVERTENCIA (faltas leves)
# =====================================================
MOTIVOS_WARN = [
    "Ausencia injustificada a un turno u oposición",
    "Uso indebido del uniforme o indumentaria oficial",
    "Falta de respeto a un superior o compañero de facción",
    "Farmeo de horas (bitácora abierta estando AFK)",
    "Otro (especificar motivo)",
]


async def _finalizar_warn(
    interaction: discord.Interaction,
    target_id: int,
    miembro: discord.Member,
    razon_texto: str,
) -> None:
    """
    Registra la advertencia ya con el motivo confirmado (preset o personalizado).
    Requiere que la respuesta inicial de la interacción ya haya sido consumida
    (vía defer o edit_message), ya que usa followup para responder.
    """
    warn_id, total_warns, fecha_str = agregar_warn(target_id, razon_texto, interaction.user.id)

    canal_advertencias_id = obtener_config_int(interaction.guild.id, "CANAL_ADVERTENCIAS_ID", CANAL_ADVERTENCIAS_ID)
    canal = interaction.guild.get_channel(canal_advertencias_id)
    if canal:
        embed = discord.Embed(
            title=f"⚠️ Nueva Advertencia ({total_warns}/3)",
            description=(
                f"**Usuario:** {miembro.mention} ({target_id})\n"
                f"**Razón:** {razon_texto}\n"
                f"**Warn ID:** {warn_id}\n"
                f"**Administrador:** {interaction.user.mention}\n"
                f"**Fecha:** {fecha_str}"
            ),
            color=discord.Color.orange(),
        )
        embed.set_footer(text="PFA - Ibiza Roleplay • Sistema de Advertencias")
        await canal.send(embed=embed)

    nota_farmeo = ""
    if es_motivo_farmeo(razon_texto):
        conteo_farmeo = await procesar_sancion_farmeo(interaction.guild, miembro)
        nota_farmeo = f"\n🚜 **Rol de Farmero actualizado:** nivel {min(conteo_farmeo, 3)} (sanción #{conteo_farmeo} de la semana)."

    await interaction.followup.send(
        f"✅ **Advertencia registrada.**\n👤 {miembro.mention}\n🆔 `{warn_id}`\n📊 {total_warns}/3\n📝 {razon_texto}"
        f"{nota_farmeo}",
        ephemeral=True,
    )

    try:
        dm_embed = discord.Embed(
            title="⚠️ Has recibido una Advertencia",
            description=(
                f"Se te ha asignado una **Advertencia** en **PFA - Ibiza Roleplay**.\n\n"
                f"**Warn ID:** `{warn_id}`\n"
                f"**Razón:** {razon_texto}\n"
                f"**Advertencias acumuladas:** {total_warns}/3\n"
                f"**Fecha:** {fecha_str}\n\n"
                "⚠️ **Recuerda:** Al acumular **3 advertencias** se genera automáticamente **1 Strike**.\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**¿Cómo apelar?**\n"
                "Si consideras que esta sanción fue injusta, haz clic en el botón de abajo "
                "para abrir un ticket de apelación."
            ),
            color=discord.Color.orange(),
        )
        dm_embed.set_footer(text="PFA - Ibiza Roleplay • Sistema de Advertencias")
        canal_tickets_id = obtener_config_int(interaction.guild.id, "CANAL_TICKETS_ID", CANAL_TICKETS_ID)
        ticket_url = f"https://discord.com/channels/{interaction.guild.id}/{canal_tickets_id}"
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="🎫 Abrir Ticket de Apelación", style=discord.ButtonStyle.link, url=ticket_url))
        await miembro.send(embed=dm_embed, view=view)
    except (discord.Forbidden, discord.HTTPException):
        pass  # El usuario tiene DMs cerrados

    # --- CHECK AUTO-STRIKE ---
    resultado_strike = _auto_strike(target_id, interaction.user.id, interaction.guild.id)
    if resultado_strike:
        strike_id, total_strikes, fecha_strike, strikes_ch_id = resultado_strike
        # Notificar en canal de advertencias
        if canal:
            embed_auto = discord.Embed(
                title="🚨 AUTO-STRIKE GENERADO",
                description=(
                    f"El usuario {miembro.mention} acumuló **3 advertencias** y se le ha asignado un **Strike automático**.\n\n"
                    f"**Strike ID:** {strike_id}\n"
                    f"**Total Strikes:** {total_strikes}/3\n"
                    f"**Advertencias eliminadas:** 3\n"
                    f"**Fecha:** {fecha_strike}"
                ),
                color=discord.Color.dark_red(),
            )
            embed_auto.set_footer(text="PFA - Ibiza Roleplay • Sistema de Advertencias → Strikes")
            await canal.send(embed=embed_auto)

        # Notificar en canal de strikes
        canal_strikes = interaction.guild.get_channel(strikes_ch_id)
        if canal_strikes:
            embed_strike = discord.Embed(
                title=f"⚠️ Nuevo Strike ({total_strikes}/3)",
                description=(
                    f"**Usuario:** {miembro.mention} ({target_id})\n"
                    f"**Razón:** Acumulación de 3 advertencias\n"
                    f"**Strike ID:** {strike_id}\n"
                    f"**Administrador:** Automático (3 advertencias)\n"
                    f"**Fecha:** {fecha_strike}"
                ),
                color=discord.Color.red(),
            )
            embed_strike.set_footer(text="PFA - Ibiza Roleplay • Sistema de Strikes")
            await canal_strikes.send(embed=embed_strike)

        await interaction.followup.send(
            f"🚨 **AUTO-STRIKE:** {miembro.mention} acumuló 3 advertencias → Strike `{strike_id}` generado automáticamente.",
            ephemeral=True,
        )


# =====================================================
# SELECT + MODAL: MOTIVO DE LA ADVERTENCIA
# =====================================================
class SelectMotivoWarn(discord.ui.Select):
    def __init__(self, target_id: int, miembro: discord.Member):
        self.target_id = target_id
        self.miembro = miembro
        options = [
            discord.SelectOption(label=motivo[:100], value=str(i))
            for i, motivo in enumerate(MOTIVOS_WARN)
        ]
        super().__init__(
            placeholder="Selecciona el motivo de la advertencia...",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        motivo = MOTIVOS_WARN[int(self.values[0])]

        if motivo.startswith("Otro"):
            return await interaction.response.send_modal(
                ModalMotivoPersonalizadoWarn(self.target_id, self.miembro)
            )

        await interaction.response.edit_message(
            content=f"⏳ Registrando advertencia para {self.miembro.mention}...", view=None
        )
        await _finalizar_warn(interaction, self.target_id, self.miembro, motivo)


class ViewSeleccionMotivoWarn(discord.ui.View):
    def __init__(self, target_id: int, miembro: discord.Member):
        super().__init__(timeout=120)
        self.add_item(SelectMotivoWarn(target_id, miembro))


class ModalMotivoPersonalizadoWarn(discord.ui.Modal):
    def __init__(self, target_id: int, miembro: discord.Member):
        super().__init__(title="Motivo de la Advertencia")
        self.target_id = target_id
        self.miembro = miembro
        self.razon = discord.ui.TextInput(
            label="Especificá el motivo *",
            style=discord.TextStyle.paragraph,
            placeholder="Explica la razón de la advertencia...",
            required=True,
        )
        self.add_item(self.razon)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await _finalizar_warn(interaction, self.target_id, self.miembro, self.razon.value.strip())


# =====================================================
# MODAL: AÑADIR ADVERTENCIA (paso 1 — solo ID)
# =====================================================
class ModalAddWarn(discord.ui.Modal, title="Añadir Advertencia"):
    discord_id = discord.ui.TextInput(label="Discord ID *", placeholder="Ingresa el Discord ID del usuario...", min_length=17, max_length=21, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_id = int(self.discord_id.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID inválido.", ephemeral=True)

        miembro = interaction.guild.get_member(target_id)
        if not miembro:
            try:
                miembro = await interaction.guild.fetch_member(target_id)
            except:
                return await interaction.response.send_message(f"❌ No se encontró al usuario `{target_id}` en el servidor.", ephemeral=True)

        await interaction.response.send_message(
            f"📝 Seleccioná el motivo de la advertencia para {miembro.mention}:",
            view=ViewSeleccionMotivoWarn(target_id, miembro),
            ephemeral=True,
        )


# =====================================================
# MODAL: ELIMINAR ADVERTENCIA
# =====================================================
class ModalRemoveWarn(discord.ui.Modal, title="Eliminar Advertencia"):
    warn_id_input = discord.ui.TextInput(label="Warn ID *", placeholder="Ingresa el ID de la advertencia...", min_length=1, max_length=20, required=True)
    motivo = discord.ui.TextInput(label="Motivo *", style=discord.TextStyle.paragraph, placeholder="Motivo de eliminación...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        wid = self.warn_id_input.value.strip()
        motivo_txt = self.motivo.value.strip()
        datos = eliminar_warn(wid, interaction.user.id, motivo_txt)
        if not datos:
            return await interaction.response.send_message(f"❌ No se encontró advertencia con ID `{wid}`.", ephemeral=True)

        miembro = interaction.guild.get_member(datos["user_id"])
        if not miembro:
            try: miembro = await interaction.guild.fetch_member(datos["user_id"])
            except: miembro = None
        usuario_texto = miembro.mention if miembro else f"<@{datos['user_id']}>"
        fecha = _ahora_str()

        canal_advertencias_id = obtener_config_int(interaction.guild.id, "CANAL_ADVERTENCIAS_ID", CANAL_ADVERTENCIAS_ID)
        canal = interaction.guild.get_channel(canal_advertencias_id)
        if canal:
            embed = discord.Embed(
                title=f"✅ Advertencia Eliminada ({datos['warns_restantes']}/3)",
                description=(
                    f"**Warn ID:** {datos['warn_id']}\n"
                    f"**Usuario:** {usuario_texto}\n"
                    f"**Administrador que eliminó:** {interaction.user.mention}\n"
                    f"**Motivo:** {motivo_txt}\n"
                    f"**Fecha de eliminación:** {fecha}"
                ),
                color=discord.Color.brand_green(),
            )
            embed.set_footer(text="PFA - Ibiza Roleplay • Sistema de Advertencias")
            await canal.send(embed=embed)

        await interaction.response.send_message(
            f"✅ **Advertencia eliminada.**\n🆔 `{datos['warn_id']}`\n👤 {usuario_texto}\n📊 Restantes: {datos['warns_restantes']}/3\n📝 {motivo_txt}",
            ephemeral=True,
        )


# =====================================================
# MODAL: BUSCAR ADVERTENCIA
# =====================================================
class ModalSearchWarn(discord.ui.Modal, title="Buscar Advertencia"):
    warn_id_input = discord.ui.TextInput(label="Warn ID *", placeholder="Ingresa el ID de la advertencia...", min_length=1, max_length=20, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        datos = buscar_warn(self.warn_id_input.value.strip())
        if not datos:
            return await interaction.response.send_message(f"❌ No se encontró advertencia con ese ID.", ephemeral=True)

        miembro = interaction.guild.get_member(datos["user_id"])
        admin = interaction.guild.get_member(datos["admin_id"])
        usuario_texto = f"{miembro.mention} ({miembro.name})" if miembro else f"<@{datos['user_id']}>"
        admin_texto = f"{admin.mention} ({admin.name})" if admin else f"<@{datos['admin_id']}>"

        embed = discord.Embed(
            title=f"🔍 Información de Advertencia: {datos['warn_id']}",
            description=(
                f"**Usuario:** {usuario_texto}\n"
                f"**Razón:** {datos['razon']}\n"
                f"**Administrador:** {admin_texto}\n"
                f"**Fecha:** {datos['fecha']}"
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="PFA - Ibiza Roleplay • Sistema de Advertencias")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# =====================================================
# MODAL: BUSCAR WARNS DE USUARIO
# =====================================================
class ModalSearchUserWarn(discord.ui.Modal, title="Buscar Advertencias de Usuario"):
    discord_id = discord.ui.TextInput(label="Discord ID *", placeholder="Ingresa el Discord ID del usuario...", min_length=17, max_length=21, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_id = int(self.discord_id.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID inválido.", ephemeral=True)

        miembro = interaction.guild.get_member(target_id)
        if not miembro:
            try: miembro = await interaction.guild.fetch_member(target_id)
            except: miembro = None

        nombre = miembro.name if miembro else str(target_id)
        usuario_texto = f"{miembro.mention} ({miembro.name})" if miembro else f"<@{target_id}>"
        warns = obtener_warns_usuario(target_id)
        total = len(warns)

        embed = discord.Embed(title=f"🔍 Advertencias de {nombre} ({total}/3)", color=discord.Color.orange())
        embed.description = f"**Usuario:** {usuario_texto}\n**Total de advertencias:** {total}/3\n"

        if total == 0:
            embed.description += "\n✅ Este usuario no tiene advertencias activas."
        else:
            for i, (wid, razon, admin_id, fecha) in enumerate(warns, start=1):
                admin = interaction.guild.get_member(admin_id)
                admin_txt = admin.mention if admin else f"<@{admin_id}>"
                embed.description += f"\n**{i}. Warn ID:**\n{wid}\n**Razón:** {razon}\n**Fecha:** {fecha}\n**Administrador:** {admin_txt}\n"

        embed.set_footer(text="PFA - Ibiza Roleplay • Sistema de Advertencias")
        await interaction.response.send_message(embed=embed, view=ViewHistorialWarn(target_id), ephemeral=True)


# =====================================================
# VIEW: BOTÓN HISTORIAL COMPLETO
# =====================================================
class ViewHistorialWarn(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id

    @discord.ui.button(label="Ver Historial Completo", style=discord.ButtonStyle.secondary, emoji="📜")
    async def btn_historial(self, interaction: discord.Interaction, button: discord.ui.Button):
        historial = obtener_historial_warns(self.user_id)
        if not historial:
            return await interaction.response.send_message("📭 No hay registros en el historial.", ephemeral=True)

        miembro = interaction.guild.get_member(self.user_id)
        nombre = miembro.name if miembro else str(self.user_id)

        embed = discord.Embed(title=f"📜 Historial de Advertencias de {nombre}", color=discord.Color.dark_grey())
        desc = ""
        for i, (wid, razon, admin_id, fecha, accion, motivo_elim) in enumerate(historial, start=1):
            admin = interaction.guild.get_member(admin_id)
            admin_txt = admin.mention if admin else f"<@{admin_id}>"
            if accion == "AGREGADA":
                desc += f"🟠 **{i}. ADVERTENCIA AGREGADA**\nID: `{wid}`\nRazón: {razon}\nAdmin: {admin_txt}\nFecha: {fecha}\n\n"
            elif accion == "CONVERTIDA":
                desc += f"🔴 **{i}. CONVERTIDA A STRIKE**\nID: `{wid}`\nAdmin: {admin_txt}\nFecha: {fecha}\n\n"
            else:
                motivo = motivo_elim or "Sin especificar"
                desc += f"🟢 **{i}. ADVERTENCIA ELIMINADA**\nID: `{wid}`\nRazón original: {razon}\nMotivo: {motivo}\nAdmin: {admin_txt}\nFecha: {fecha}\n\n"

        if len(desc) > 4000:
            desc = desc[:3900] + "\n... (truncado)"
        embed.description = desc
        embed.set_footer(text="PFA - Ibiza Roleplay • Sistema de Advertencias")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# =====================================================
# VIEW: PANEL DE ADVERTENCIAS PFA
# =====================================================
class ViewPanelAdvertenciasPFA(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def _tiene_permiso(self, interaction):
        if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator:
            return True
        rol_admin = obtener_config_int(interaction.guild.id, "ROL_PANEL_ADMIN_ID", ROL_PANEL_ADMIN_ID)
        rol_perms = obtener_config_int(interaction.guild.id, "ROL_PERMS", ROL_PERMS)
        return any(rol.id in (rol_admin, rol_perms) for rol in interaction.user.roles)

    @discord.ui.button(label="Add Warn", style=discord.ButtonStyle.danger, custom_id="panel_warns_add_v1", emoji="⚠️", row=0)
    async def btn_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalAddWarn())

    @discord.ui.button(label="Remove Warn", style=discord.ButtonStyle.danger, custom_id="panel_warns_remove_v1", row=0)
    async def btn_remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalRemoveWarn())

    @discord.ui.button(label="Search Warn", style=discord.ButtonStyle.primary, custom_id="panel_warns_search_v1", emoji="🔍", row=0)
    async def btn_search(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalSearchWarn())

    @discord.ui.button(label="Search User", style=discord.ButtonStyle.success, custom_id="panel_warns_search_user_v1", emoji="👤", row=0)
    async def btn_search_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalSearchUserWarn())


# =====================================================
# COG
# =====================================================
class AdvertenciasPFA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(ViewPanelAdvertenciasPFA())
        print("✅ [Cog] Panel de Advertencias PFA cargado.")

    @app_commands.command(name="paneladvertencias", description="Despliega el Panel de Advertencias PFA.")
    async def paneladvertencias(self, interaction: discord.Interaction):
        if not ViewPanelAdvertenciasPFA()._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)

        ahora = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3)))
        fecha_str = ahora.strftime("%d/%m/%Y %H:%M:%S")

        embed = discord.Embed(
            title="Bienvenido al Panel Oficial de Advertencias",
            description=(
                "**¡Hola, encargado!**\n\n"
                "Este panel te permitirá gestionar las advertencias de los usuarios.\n\n"
                "⚠️ **Add Warn:** Añade una advertencia a un usuario. Primero pide el ID y luego "
                "el motivo mediante un menú desplegable (incluye la opción \"Otro\" para "
                "especificar un motivo que no esté en la lista).\n"
                "❌ **Remove Warn:** Elimina una advertencia de un usuario.\n"
                "🔍 **Search Warn:** Busca una advertencia por su ID.\n"
                "👤 **Search User:** Busca las advertencias de un usuario.\n\n"
                "🚨 **Al acumular 3 advertencias, se genera automáticamente 1 Strike.**\n\n"
                "Utiliza estos botones de forma responsable.\n\n"
                f"PFA – Ibiza Roleplay • {fecha_str}"
            ),
            color=discord.Color.orange(),
        )
        await interaction.channel.send(embed=embed, view=ViewPanelAdvertenciasPFA())
        await interaction.response.send_message("✅ Panel de Advertencias desplegado.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdvertenciasPFA(bot))
