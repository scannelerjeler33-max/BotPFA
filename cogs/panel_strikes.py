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
CANAL_STRIKES_ID = safe_env_int("CANAL_STRIKES_ID", 0)
CANAL_TICKETS_ID = safe_env_int("CANAL_TICKETS_ID", 0)

# --- BASE DE DATOS DE STRIKES ---
conn_strikes = get_connection()
cursor_strikes = conn_strikes.cursor()


def sincronizar_secuencia(tabla, columna="id"):
    if tabla not in {"strikes_historial"}:
        raise ValueError("Tabla no permitida para sincronizar secuencia.")

    cursor_strikes.execute(
        f"""
        SELECT setval(
            pg_get_serial_sequence(%s, %s),
            COALESCE((SELECT MAX({columna}) FROM {tabla}), 0) + 1,
            false
        )
        """,
        (tabla, columna),
    )
    conn_strikes.commit()


def reparar_secuencias():
    sincronizar_secuencia("strikes_historial")


reparar_secuencias()


def generar_strike_id(longitud=13):
    """Genera un ID alfanumérico aleatorio único para cada strike."""
    caracteres = string.ascii_letters + string.digits
    while True:
        nuevo_id = ''.join(random.choices(caracteres, k=longitud))
        cursor_strikes.execute("SELECT 1 FROM strikes WHERE strike_id = %s", (nuevo_id,))
        if not cursor_strikes.fetchone():
            return nuevo_id


def contar_strikes_usuario(user_id: int) -> int:
    """Retorna la cantidad total de strikes activos de un usuario."""
    cursor_strikes.execute("SELECT COUNT(*) FROM strikes WHERE user_id = %s", (user_id,))
    return cursor_strikes.fetchone()[0]


def agregar_strike(user_id: int, razon: str, admin_id: int) -> tuple:
    """Agrega un strike a la base de datos. Retorna (strike_id, total_strikes)."""
    strike_id = generar_strike_id()
    ahora = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3)))
    fecha_str = ahora.strftime("%d/%m/%Y, %H:%M:%S")

    try:
        cursor_strikes.execute(
            "INSERT INTO strikes (strike_id, user_id, razon, admin_id, fecha) VALUES (%s, %s, %s, %s, %s)",
            (strike_id, user_id, razon, admin_id, fecha_str),
        )
        # Registrar en historial
        cursor_strikes.execute(
            "INSERT INTO strikes_historial (strike_id, user_id, razon, admin_id, fecha, accion) VALUES (%s, %s, %s, %s, %s, %s)",
            (strike_id, user_id, razon, admin_id, fecha_str, "AGREGADO"),
        )
        conn_strikes.commit()
    except psycopg2.errors.UniqueViolation:
        conn_strikes.rollback()
        reparar_secuencias()
        cursor_strikes.execute(
            "INSERT INTO strikes (strike_id, user_id, razon, admin_id, fecha) VALUES (%s, %s, %s, %s, %s)",
            (strike_id, user_id, razon, admin_id, fecha_str),
        )
        cursor_strikes.execute(
            "INSERT INTO strikes_historial (strike_id, user_id, razon, admin_id, fecha, accion) VALUES (%s, %s, %s, %s, %s, %s)",
            (strike_id, user_id, razon, admin_id, fecha_str, "AGREGADO"),
        )
        conn_strikes.commit()

    total = contar_strikes_usuario(user_id)
    return strike_id, total, fecha_str


def eliminar_strike(strike_id: str) -> dict | None:
    """Elimina un strike por su ID. Retorna los datos del strike eliminado o None si no existe."""
    cursor_strikes.execute("SELECT strike_id, user_id, razon, admin_id, fecha FROM strikes WHERE strike_id = %s", (strike_id,))
    resultado = cursor_strikes.fetchone()
    if not resultado:
        return None

    datos = {
        "strike_id": resultado[0],
        "user_id": resultado[1],
        "razon": resultado[2],
        "admin_id": resultado[3],
        "fecha": resultado[4],
    }

    cursor_strikes.execute("DELETE FROM strikes WHERE strike_id = %s", (strike_id,))
    conn_strikes.commit()

    datos["strikes_restantes"] = contar_strikes_usuario(datos["user_id"])
    return datos


def eliminar_strike_con_motivo(strike_id: str, admin_eliminacion_id: int, motivo_eliminacion: str) -> dict | None:
    """Elimina un strike y registra el motivo en el historial."""
    datos = eliminar_strike(strike_id)
    if datos:
        ahora = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3)))
        fecha_str = ahora.strftime("%d/%m/%Y, %H:%M:%S")
        cursor_strikes.execute(
            "INSERT INTO strikes_historial (strike_id, user_id, razon, admin_id, fecha, accion, motivo_eliminacion) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (datos["strike_id"], datos["user_id"], datos["razon"], admin_eliminacion_id, fecha_str, "ELIMINADO", motivo_eliminacion),
        )
        conn_strikes.commit()
    return datos


def buscar_strike(strike_id: str) -> dict | None:
    """Busca un strike por su ID sin eliminarlo. Retorna los datos o None."""
    cursor_strikes.execute("SELECT strike_id, user_id, razon, admin_id, fecha FROM strikes WHERE strike_id = %s", (strike_id,))
    resultado = cursor_strikes.fetchone()
    if not resultado:
        return None
    return {
        "strike_id": resultado[0],
        "user_id": resultado[1],
        "razon": resultado[2],
        "admin_id": resultado[3],
        "fecha": resultado[4],
    }


def obtener_strikes_usuario(user_id: int) -> list:
    """Retorna todos los strikes activos de un usuario."""
    cursor_strikes.execute(
        "SELECT strike_id, razon, admin_id, fecha FROM strikes WHERE user_id = %s ORDER BY strike_id ASC",
        (user_id,),
    )
    return cursor_strikes.fetchall()

def obtener_historial_usuario(user_id: int) -> list:
    """Retorna el historial completo de strikes de un usuario (agregados y eliminados)."""
    cursor_strikes.execute(
        "SELECT strike_id, razon, admin_id, fecha, accion, motivo_eliminacion FROM strikes_historial WHERE user_id = %s ORDER BY id ASC",
        (user_id,),
    )
    return cursor_strikes.fetchall()


# =====================================================
# MOTIVOS PREDEFINIDOS DE STRIKE (faltas graves)
# =====================================================
MOTIVOS_STRIKE = [
    "Farmeo de horas (bitácora abierta estando AFK)",
    "Insultos graves o faltas de respeto a un superior u oficial PFA",
    "No acatar órdenes de un superior",
    "Abuso de autoridad o mal uso de las facultades del rol",
    "Uso indebido de armamento, vehículos o equipamiento oficial",
    "Doble facción no autorizada o incumplimiento de su normativa",
    "Reincidencia tras una advertencia previa",
    "Otro (especificar motivo)",
]


async def _finalizar_strike(
    interaction: discord.Interaction,
    target_id: int,
    miembro: discord.Member,
    razon_texto: str,
) -> None:
    """
    Registra el strike ya con el motivo confirmado (preset o personalizado).
    Requiere que la respuesta inicial de la interacción ya haya sido consumida
    (vía defer o edit_message), ya que usa followup para responder.
    """
    strike_id, total_strikes, fecha_str = agregar_strike(
        user_id=target_id,
        razon=razon_texto,
        admin_id=interaction.user.id,
    )

    canal_strikes_id = obtener_config_int(interaction.guild.id, "CANAL_STRIKES_ID", CANAL_STRIKES_ID)
    canal_strikes = interaction.guild.get_channel(canal_strikes_id)
    if canal_strikes:
        embed = discord.Embed(
            title=f"⚠️ Nuevo Strike ({total_strikes}/3)",
            description=(
                f"**Usuario:** {miembro.mention} ({target_id})\n"
                f"**Razón:** {razon_texto}\n"
                f"**Strike ID:** {strike_id}\n"
                f"**Administrador:** {interaction.user.mention}\n"
                f"**Fecha:** {fecha_str}"
            ),
            color=discord.Color.red(),
        )
        embed.set_footer(text="PFA - Ibiza Roleplay • Sistema de Strikes")
        await canal_strikes.send(embed=embed)

    nota_farmeo = ""
    if es_motivo_farmeo(razon_texto):
        conteo_farmeo = await procesar_sancion_farmeo(interaction.guild, miembro)
        nota_farmeo = f"\n🚜 **Rol de Farmero actualizado:** nivel {min(conteo_farmeo, 3)} (sanción #{conteo_farmeo} de la semana)."

    await interaction.followup.send(
        f"✅ **Strike registrado correctamente.**\n\n"
        f"👤 **Usuario:** {miembro.mention}\n"
        f"🆔 **Strike ID:** `{strike_id}`\n"
        f"📊 **Total strikes:** {total_strikes}/3\n"
        f"📝 **Razón:** {razon_texto}"
        f"{nota_farmeo}",
        ephemeral=True,
    )

    try:
        dm_embed = discord.Embed(
            title="🚨 Has recibido un Strike",
            description=(
                f"Se te ha asignado un **Strike** en **PFA - Ibiza Roleplay**.\n\n"
                f"**Strike ID:** `{strike_id}`\n"
                f"**Razón:** {razon_texto}\n"
                f"**Strikes acumulados:** {total_strikes}/3\n"
                f"**Fecha:** {fecha_str}\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "**¿Cómo apelar?**\n"
                "Si consideras que esta sanción fue injusta, haz clic en el botón de abajo "
                "para abrir un ticket de apelación."
            ),
            color=discord.Color.red(),
        )
        dm_embed.set_footer(text="PFA - Ibiza Roleplay • Sistema de Strikes")
        canal_tickets_id = obtener_config_int(interaction.guild.id, "CANAL_TICKETS_ID", CANAL_TICKETS_ID)
        ticket_url = f"https://discord.com/channels/{interaction.guild.id}/{canal_tickets_id}"
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="🎫 Abrir Ticket de Apelación", style=discord.ButtonStyle.link, url=ticket_url))
        await miembro.send(embed=dm_embed, view=view)
    except (discord.Forbidden, discord.HTTPException):
        pass  # El usuario tiene DMs cerrados


# =====================================================
# SELECT + MODAL: MOTIVO DEL STRIKE
# =====================================================
class SelectMotivoStrike(discord.ui.Select):
    def __init__(self, target_id: int, miembro: discord.Member):
        self.target_id = target_id
        self.miembro = miembro
        options = [
            discord.SelectOption(label=motivo[:100], value=str(i))
            for i, motivo in enumerate(MOTIVOS_STRIKE)
        ]
        super().__init__(
            placeholder="Selecciona el motivo del strike...",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        motivo = MOTIVOS_STRIKE[int(self.values[0])]

        if motivo.startswith("Otro"):
            return await interaction.response.send_modal(
                ModalMotivoPersonalizadoStrike(self.target_id, self.miembro)
            )

        await interaction.response.edit_message(
            content=f"⏳ Registrando strike para {self.miembro.mention}...", view=None
        )
        await _finalizar_strike(interaction, self.target_id, self.miembro, motivo)


class ViewSeleccionMotivoStrike(discord.ui.View):
    def __init__(self, target_id: int, miembro: discord.Member):
        super().__init__(timeout=120)
        self.add_item(SelectMotivoStrike(target_id, miembro))


class ModalMotivoPersonalizadoStrike(discord.ui.Modal):
    def __init__(self, target_id: int, miembro: discord.Member):
        super().__init__(title="Motivo del Strike")
        self.target_id = target_id
        self.miembro = miembro
        self.razon = discord.ui.TextInput(
            label="Especificá el motivo *",
            style=discord.TextStyle.paragraph,
            placeholder="Explica la razón del strike...",
            required=True,
        )
        self.add_item(self.razon)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await _finalizar_strike(interaction, self.target_id, self.miembro, self.razon.value.strip())


# =====================================================
# MODAL: AÑADIR STRIKE (paso 1 — solo ID)
# =====================================================
class ModalAddStrike(discord.ui.Modal, title="Añadir Strike"):
    discord_id = discord.ui.TextInput(
        label="Discord ID *",
        placeholder="Ingresa el Discord ID del usuario...",
        min_length=17,
        max_length=21,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Validar ID
        try:
            target_id = int(self.discord_id.value.strip())
        except ValueError:
            return await interaction.response.send_message(
                "❌ El ID ingresado no es válido. Debe ser un número.", ephemeral=True
            )

        # 2. Buscar al miembro en el servidor
        miembro = interaction.guild.get_member(target_id)
        if not miembro:
            try:
                miembro = await interaction.guild.fetch_member(target_id)
            except discord.NotFound:
                return await interaction.response.send_message(
                    f"❌ No se encontró ningún usuario con el ID `{target_id}` en este servidor.",
                    ephemeral=True,
                )
            except discord.HTTPException:
                return await interaction.response.send_message(
                    "❌ Error al buscar al usuario. Verifica el ID e inténtalo de nuevo.",
                    ephemeral=True,
                )

        # 3. Pedir el motivo del strike mediante un menú desplegable
        await interaction.response.send_message(
            f"📝 Seleccioná el motivo del strike para {miembro.mention}:",
            view=ViewSeleccionMotivoStrike(target_id, miembro),
            ephemeral=True,
        )


# =====================================================
# MODAL: ELIMINAR STRIKE
# =====================================================
class ModalRemoveStrike(discord.ui.Modal, title="Eliminar Strike"):
    strike_id_input = discord.ui.TextInput(
        label="Strike ID *",
        placeholder="Ingresa el ID del strike a eliminar...",
        min_length=1,
        max_length=20,
        required=True,
    )
    motivo = discord.ui.TextInput(
        label="Motivo *",
        style=discord.TextStyle.paragraph,
        placeholder="Motivo por el cual se retira el strike...",
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        strike_id = self.strike_id_input.value.strip()
        motivo_texto = self.motivo.value.strip()

        # 1. Buscar y eliminar el strike (con registro en historial)
        datos = eliminar_strike_con_motivo(strike_id, interaction.user.id, motivo_texto)
        if not datos:
            return await interaction.response.send_message(
                f"❌ No se encontró ningún strike con el ID `{strike_id}`.",
                ephemeral=True,
            )

        # 2. Intentar obtener el miembro
        miembro = interaction.guild.get_member(datos["user_id"])
        if not miembro:
            try:
                miembro = await interaction.guild.fetch_member(datos["user_id"])
            except Exception:
                miembro = None

        usuario_texto = miembro.mention if miembro else f"<@{datos['user_id']}>"
        ahora = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3)))
        fecha_str = ahora.strftime("%d/%m/%Y, %H:%M:%S")

        # 3. Enviar embed al canal de strikes
        canal_strikes_id = obtener_config_int(interaction.guild.id, "CANAL_STRIKES_ID", CANAL_STRIKES_ID)
        canal_strikes = interaction.guild.get_channel(canal_strikes_id)
        if canal_strikes:
            embed = discord.Embed(
                title=f"✅ Strike Eliminado ({datos['strikes_restantes']}/3)",
                description=(
                    f"**Strike ID:** {datos['strike_id']}\n"
                    f"**Usuario:** {usuario_texto}\n"
                    f"**Administrador que eliminó:** {interaction.user.mention}\n"
                    f"**Motivo:** {motivo_texto}\n"
                    f"**Fecha de eliminación:** {fecha_str}"
                ),
                color=discord.Color.brand_green(),
            )
            embed.set_footer(text="PFA - Ibiza Roleplay • Sistema de Strikes")
            await canal_strikes.send(embed=embed)

        # 4. Confirmar al administrador
        await interaction.response.send_message(
            f"✅ **Strike eliminado correctamente.**\n\n"
            f"🆔 **Strike ID:** `{datos['strike_id']}`\n"
            f"👤 **Usuario:** {usuario_texto}\n"
            f"📊 **Strikes restantes:** {datos['strikes_restantes']}/3\n"
            f"📝 **Motivo:** {motivo_texto}",
            ephemeral=True,
        )


# =====================================================
# MODAL: BUSCAR STRIKE
# =====================================================
class ModalSearchStrike(discord.ui.Modal, title="Buscar Strike"):
    strike_id_input = discord.ui.TextInput(
        label="Strike ID *",
        placeholder="Ingresa el ID del strike a buscar...",
        min_length=1,
        max_length=20,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        strike_id = self.strike_id_input.value.strip()

        # 1. Buscar el strike en la BDD
        datos = buscar_strike(strike_id)
        if not datos:
            return await interaction.response.send_message(
                f"❌ No se encontró ningún strike con el ID `{strike_id}`.",
                ephemeral=True,
            )

        # 2. Obtener datos del usuario y admin
        miembro = interaction.guild.get_member(datos["user_id"])
        if not miembro:
            try:
                miembro = await interaction.guild.fetch_member(datos["user_id"])
            except Exception:
                miembro = None

        admin = interaction.guild.get_member(datos["admin_id"])
        if not admin:
            try:
                admin = await interaction.guild.fetch_member(datos["admin_id"])
            except Exception:
                admin = None

        usuario_texto = f"{miembro.mention} ({miembro.name})" if miembro else f"<@{datos['user_id']}>"
        admin_texto = f"{admin.mention} ({admin.name})" if admin else f"<@{datos['admin_id']}>"

        # 3. Responder ephemeral con el embed
        embed = discord.Embed(
            title=f"🔍 Información del Strike: {datos['strike_id']}",
            description=(
                f"**Usuario:** {usuario_texto}\n"
                f"**Razón:** {datos['razon']}\n"
                f"**Administrador:** {admin_texto}\n"
                f"**Fecha:** {datos['fecha']}"
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="PFA - Ibiza Roleplay • Sistema de Strikes")

        await interaction.response.send_message(embed=embed, ephemeral=True)



# =====================================================
# MODAL: BUSCAR STRIKES DE USUARIO
# =====================================================
class ModalSearchUser(discord.ui.Modal, title="Buscar Strikes de Usuario"):
    discord_id = discord.ui.TextInput(
        label="Discord ID *",
        placeholder="Ingresa el Discord ID del usuario...",
        min_length=17,
        max_length=21,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Validar ID
        try:
            target_id = int(self.discord_id.value.strip())
        except ValueError:
            return await interaction.response.send_message(
                "❌ El ID ingresado no es válido. Debe ser un número.", ephemeral=True
            )

        # 2. Buscar al miembro
        miembro = interaction.guild.get_member(target_id)
        if not miembro:
            try:
                miembro = await interaction.guild.fetch_member(target_id)
            except Exception:
                miembro = None

        usuario_nombre = miembro.name if miembro else str(target_id)
        usuario_texto = f"{miembro.mention} ({miembro.name})" if miembro else f"<@{target_id}>"

        # 3. Obtener strikes activos
        strikes = obtener_strikes_usuario(target_id)
        total = len(strikes)

        # 4. Construir el embed
        embed = discord.Embed(
            title=f"🔍 Strikes de {usuario_nombre} ({total}/3)",
            color=discord.Color.blue(),
        )
        embed.description = f"**Usuario:** {usuario_texto}\n**Total de strikes:** {total}/3\n"

        if total == 0:
            embed.description += "\n✅ Este usuario no tiene strikes activos."
        else:
            for i, (sid, razon, admin_id, fecha) in enumerate(strikes, start=1):
                admin = interaction.guild.get_member(admin_id)
                admin_texto = admin.mention if admin else f"<@{admin_id}>"
                embed.description += (
                    f"\n**{i}. Strike ID:**\n"
                    f"{sid}\n"
                    f"**Razón:** {razon}\n"
                    f"**Fecha:** {fecha}\n"
                    f"**Administrador:** {admin_texto}\n"
                )

        embed.set_footer(text="PFA - Ibiza Roleplay • Sistema de Strikes")

        # 5. Responder con embed + botón de historial
        await interaction.response.send_message(
            embed=embed,
            view=ViewHistorialStrike(target_id),
            ephemeral=True,
        )


# =====================================================
# VIEW: BOTÓN VER HISTORIAL COMPLETO
# =====================================================
class ViewHistorialStrike(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    @discord.ui.button(
        label="Ver Historial Completo",
        style=discord.ButtonStyle.secondary,
        emoji="📜",
    )
    async def btn_historial(self, interaction: discord.Interaction, button: discord.ui.Button):
        historial = obtener_historial_usuario(self.user_id)

        if not historial:
            return await interaction.response.send_message(
                "📭 No hay registros en el historial de este usuario.", ephemeral=True
            )

        miembro = interaction.guild.get_member(self.user_id)
        usuario_nombre = miembro.name if miembro else str(self.user_id)

        embed = discord.Embed(
            title=f"📜 Historial Completo de {usuario_nombre}",
            color=discord.Color.dark_grey(),
        )

        descripcion = ""
        for i, (sid, razon, admin_id, fecha, accion, motivo_elim) in enumerate(historial, start=1):
            admin = interaction.guild.get_member(admin_id)
            admin_texto = admin.mention if admin else f"<@{admin_id}>"

            if accion == "AGREGADO":
                emoji = "🔴"
                descripcion += (
                    f"{emoji} **{i}. STRIKE AGREGADO**\n"
                    f"ID: `{sid}`\n"
                    f"Razón: {razon}\n"
                    f"Admin: {admin_texto}\n"
                    f"Fecha: {fecha}\n\n"
                )
            else:
                emoji = "🟢"
                motivo_txt = motivo_elim if motivo_elim else "Sin especificar"
                descripcion += (
                    f"{emoji} **{i}. STRIKE ELIMINADO**\n"
                    f"ID: `{sid}`\n"
                    f"Razón original: {razon}\n"
                    f"Motivo eliminación: {motivo_txt}\n"
                    f"Admin: {admin_texto}\n"
                    f"Fecha: {fecha}\n\n"
                )

        # Truncar si es muy largo
        if len(descripcion) > 4000:
            descripcion = descripcion[:3900] + "\n... (historial truncado)"

        embed.description = descripcion
        embed.set_footer(text="PFA - Ibiza Roleplay • Sistema de Strikes")

        await interaction.response.send_message(embed=embed, ephemeral=True)


# =====================================================
# VIEW: PANEL DE STRIKES PFA
# =====================================================
class ViewPanelStrikesPFA(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def _tiene_permiso(self, interaction: discord.Interaction) -> bool:
        """Verifica si el usuario tiene el rol de administrador del panel."""
        if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator:
            return True
        rol_admin = obtener_config_int(interaction.guild.id, "ROL_PANEL_ADMIN_ID", ROL_PANEL_ADMIN_ID)
        rol_perms = obtener_config_int(interaction.guild.id, "ROL_PERMS", ROL_PERMS)
        return any(rol.id in (rol_admin, rol_perms) for rol in interaction.user.roles)

    # --- BOTÓN ADD STRIKE ---
    @discord.ui.button(
        label="Add Strike",
        style=discord.ButtonStyle.danger,
        custom_id="panel_strikes_add_v1",
        emoji="⚠️",
        row=0,
    )
    async def btn_add_strike(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message(
                "⛔ No tienes permiso para usar este panel.", ephemeral=True
            )
        await interaction.response.send_modal(ModalAddStrike())

    # --- BOTÓN REMOVE STRIKE ---
    @discord.ui.button(
        label="Remove Strike",
        style=discord.ButtonStyle.danger,
        custom_id="panel_strikes_remove_v1",
        row=0,
    )
    async def btn_remove_strike(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message(
                "⛔ No tienes permiso para usar este panel.", ephemeral=True
            )
        await interaction.response.send_modal(ModalRemoveStrike())

    # --- BOTÓN SEARCH STRIKE ---
    @discord.ui.button(
        label="Search Strike",
        style=discord.ButtonStyle.primary,
        custom_id="panel_strikes_search_v1",
        emoji="🔍",
        row=0,
    )
    async def btn_search_strike(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message(
                "⛔ No tienes permiso para usar este panel.", ephemeral=True
            )
        await interaction.response.send_modal(ModalSearchStrike())

    # --- BOTÓN SEARCH USER ---
    @discord.ui.button(
        label="Search User",
        style=discord.ButtonStyle.success,
        custom_id="panel_strikes_search_user_v1",
        emoji="🔎",
        row=0,
    )
    async def btn_search_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message(
                "⛔ No tienes permiso para usar este panel.", ephemeral=True
            )
        await interaction.response.send_modal(ModalSearchUser())


# =====================================================
# COG: PANEL STRIKES PFA
# =====================================================
class StrikesPFA(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(ViewPanelStrikesPFA())
        print("✅ [Cog] Panel de Strikes PFA cargado y vista persistente registrada.")

    @app_commands.command(name="panelstrikes", description="Despliega el Panel de Gestión de Strikes PFA.")
    async def panelstrikes(self, interaction: discord.Interaction):
        if not ViewPanelStrikesPFA()._tiene_permiso(interaction):
            return await interaction.response.send_message(
                "⛔ No tienes permiso para desplegar este panel.", ephemeral=True
            )

        ahora = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3)))
        fecha_str = ahora.strftime("%d/%m/%Y %H:%M:%S")

        embed = discord.Embed(
            title="Bienvenido al Panel Oficial de Strikes - P.F.A",
            description=(
                "**¡Hola, encargado!**\n\n"
                "Este panel te permitirá gestionar los strikes de los usuarios de manera eficiente. "
                "Aquí tienes una descripción de las funciones de cada botón:\n\n"
                "⚠️ **Add Strike:** Añade un strike a un usuario. Primero pide el ID y luego "
                "el motivo mediante un menú desplegable (incluye la opción \"Otro\" para "
                "especificar un motivo que no esté en la lista).\n"
                "❌ **Remove Strike:** Elimina un strike de un usuario.\n"
                "🔍 **Search Strike:** Busca un strike por su ID.\n"
                "🔎 **Search User:** Busca los strikes de un usuario por su Discord ID.\n\n"
                "Utiliza estos botones de forma responsable para mantener el orden y la disciplina "
                "en la comunidad. ¡Gracias por tu dedicación!\n\n"
                f"PFA – Ibiza Roleplay • {fecha_str}"
            ),
            color=discord.Color.red(),
        )

        await interaction.channel.send(embed=embed, view=ViewPanelStrikesPFA())
        await interaction.response.send_message("✅ Panel de Strikes PFA desplegado.", ephemeral=True)


# --- SETUP FUNCTION (requerida para cargar como extensión) ---
async def setup(bot: commands.Bot):
    await bot.add_cog(StrikesPFA(bot))
