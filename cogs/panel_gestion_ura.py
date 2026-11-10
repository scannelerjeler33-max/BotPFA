import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import datetime
from databases.connection import get_connection

# ═══════════════════════════════════════════════════════════════════
#  PANEL DE GESTIÓN — U.R.A (Unidad Rápida de Acción)
# ═══════════════════════════════════════════════════════════════════

# --- BASE DE DATOS URA ---
conn_ura = get_connection()
conn_ura.autocommit = True
cursor_ura = conn_ura.cursor()

cursor_ura.execute("""
    CREATE TABLE IF NOT EXISTS ura_top_misiones (
        user_id BIGINT PRIMARY KEY,
        misiones INTEGER DEFAULT 0
    )
""")

# --- CONFIG ---
from utils.config import obtener_config_int

ROL_URA_ID = 1390022409381216388           # ← ID del rol base "U.R.A"
CANAL_LOGS_URA_ID = 1409352142745243688    # ← ID del canal de logs URA
ROL_PANEL_URA_ADMIN_ID = 1500032028182052955  # ← ID del rol que puede usar el panel
ROL_PERMS = 1351228669359558809

# Roles de TIER (UN solo rol por tier)
ROL_LOW_URA_ID = 1448867576246435961      # ← ID de "Low U.R.A"
ROL_HIGH_URA_ID = 1448468642059780116      # ← ID de "High U.R.A"
ROL_HEAD_URA_ID = 1390024168958857256      # ← ID de "Head U.R.A"

def _get_ura_rol_id(guild_id: int, key_or_tuple) -> int:
    if isinstance(key_or_tuple, tuple):
        raw_name = key_or_tuple[0].replace(" ", "_").replace("º", "_").replace("1", "1_").upper()
        import re
        clean_name = re.sub(r"[^A-Z0-9_]", "", raw_name)
        key = f"ROL_URA_RANGO_{clean_name}"
        fallback = key_or_tuple[1]
        return obtener_config_int(guild_id, key, fallback)
    fallback = globals().get(key_or_tuple, 0)
    return obtener_config_int(guild_id, key_or_tuple, fallback)

TIER_ROLES = {
    "low": ROL_LOW_URA_ID,
    "high": ROL_HIGH_URA_ID,
    "head": ROL_HEAD_URA_ID,
}

# --- JERARQUÍA DE RANGOS (de menor a mayor) ---
JERARQUIA_URA = [
    # --- LOW ---
    ("Piloto A Prueba",         1454678073915211838, "low"),
    ("Piloto Novato",           1390020466974130216, "low"),
    ("Piloto Instruido",        1390021029505531924, "low"),
    ("Piloto Audaz",            1390021448545992784, "low"),
    ("Piloto Avanzado",         1390023722349498518, "low"),
    ("Piloto Experto",          1390023295373676614, "low"),
    ("Piloto Senior",           1454833303466278912, "low"),
    # --- HIGH ---
    ("Piloto Élite",            1454829977588469790, "high"),
    ("Piloto Veterano",         1454676705896566846, "high"),
    ("Piloto Instructor",       1390024290258128916, "high"),
    ("Supervisor U.R.A",        1454677126476337284, "high"),
    ("Supervisor Mayor U.R.A",  1454873699655356602, "high"),
    ("Inspector U.R.A",         1454829575321419921, "high"),
    ("Inspector General U.R.A", 1454834046197698641, "high"),
    ("Coordinador U.R.A",       1454677007697969348, "high"),
    ("Sub Comandante U.R.A",    1454829546720202876, "high"),
    ("Comandante U.R.A",        1454676929864143002, "high"),
    # --- HEAD ---
    ("Sub Jefe U.R.A",          1392654416720429116, "head"),
    ("Jefe U.R.A",              1392654516737802380, "head"),
    ("Jefe Mayor U.R.A",        1454887284993429565, "head"),
    ("Sub Director General U.R.A", 1454675986565173249, "head"),
    ("Director General U.R.A",  1390025896295006341, "head"),
]


# --- HELPERS ---
def get_rango_actual(miembro, guild):
    for idx, item in enumerate(JERARQUIA_URA):
        rol_id = _get_ura_rol_id(guild.id, item)
        rol = guild.get_role(rol_id)
        if rol and rol in miembro.roles:
            return idx
    return -1


async def swap_tier_roles(miembro, guild, tier_viejo, tier_nuevo):
    if tier_viejo == tier_nuevo:
        return

    rol_low = _get_ura_rol_id(guild.id, "ROL_LOW_URA_ID")
    rol_high = _get_ura_rol_id(guild.id, "ROL_HIGH_URA_ID")
    rol_head = _get_ura_rol_id(guild.id, "ROL_HEAD_URA_ID")
    tier_roles = {
        "low": rol_low,
        "high": rol_high,
        "head": rol_head,
    }

    rol_dar_id = tier_roles.get(tier_nuevo)
    roles_quitar = []
    for tier, rol_id in tier_roles.items():
        if tier == tier_nuevo:
            continue
        r = guild.get_role(rol_id)
        if r and r in miembro.roles:
            roles_quitar.append(r)

    if roles_quitar:
        await miembro.remove_roles(*roles_quitar, reason=f"Cambio de tier URA: {tier_viejo.upper()} -> {tier_nuevo.upper()}")

    if rol_dar_id:
        r = guild.get_role(rol_dar_id)
        if r and r not in miembro.roles:
            await miembro.add_roles(r, reason=f"Cambio de tier URA: {tier_viejo.upper()} -> {tier_nuevo.upper()}")


async def buscar_miembro(interaction, raw_id):
    async def responder_error(mensaje):
        if interaction.response.is_done():
            await interaction.followup.send(mensaje, ephemeral=True)
        else:
            await interaction.response.send_message(mensaje, ephemeral=True)

    try:
        target_id = int(raw_id.strip())
    except ValueError:
        await responder_error("❌ El ID ingresado no es válido.")
        return None
    miembro = interaction.guild.get_member(target_id)
    if not miembro:
        try:
            miembro = await interaction.guild.fetch_member(target_id)
        except (discord.NotFound, discord.HTTPException):
            await responder_error(f"❌ No se encontró ningún usuario con el ID `{target_id}`.")
            return None
    return miembro


async def enviar_log(interaction, mensaje):
    canal_logs_ura_id = _get_ura_rol_id(interaction.guild.id, "CANAL_LOGS_URA_ID")
    canal = interaction.guild.get_channel(canal_logs_ura_id)
    if canal:
        await canal.send(mensaje)


def mensaje_sin_permisos_bot():
    return (
        "❌ No tengo permisos para dar o quitar esos roles.\n"
        "Subí el rol del bot por encima de los roles de U.R.A, rangos y tiers en la jerarquía de Discord."
    )


def es_panel_ura(mensaje):
    for embed in mensaje.embeds:
        texto = " ".join(
            parte or ""
            for parte in (embed.title, embed.description, embed.footer.text if embed.footer else "")
        )
        if "Gestión de Miembros" in texto and ("U.R.A" in texto or "URA" in texto):
            return True

    for fila in mensaje.components:
        for componente in fila.children:
            custom_id = getattr(componente, "custom_id", "") or ""
            if custom_id.startswith("panel_ura_"):
                return True

    return False


async def limpiar_paneles_ura(canal, bot_user):
    async for mensaje in canal.history(limit=100):
        if mensaje.author.id != bot_user.id:
            continue
        if not es_panel_ura(mensaje):
            continue
        try:
            await mensaje.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass


async def dejar_un_solo_panel_ura(canal, bot_user):
    paneles = []
    async for mensaje in canal.history(limit=100):
        if mensaje.author.id == bot_user.id and es_panel_ura(mensaje):
            paneles.append(mensaje)

    if len(paneles) <= 1:
        return

    paneles.sort(key=lambda mensaje: mensaje.created_at, reverse=True)
    for mensaje in paneles[1:]:
        try:
            await mensaje.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass


def tiene_permiso_panel_ura(miembro):
    if miembro.id == miembro.guild.owner_id or miembro.guild_permissions.administrator:
        return True
    rol_panel_ura_admin_id = _get_ura_rol_id(miembro.guild.id, "ROL_PANEL_URA_ADMIN_ID")
    rol_perms = _get_ura_rol_id(miembro.guild.id, "ROL_PERMS")
    return any(rol.id in (rol_panel_ura_admin_id, rol_perms) for rol in miembro.roles)


def tiene_permiso_desplegar(miembro):
    if miembro.id == miembro.guild.owner_id or miembro.guild_permissions.administrator:
        return True
    rol_perms = _get_ura_rol_id(miembro.guild.id, "ROL_PERMS")
    return any(rol.id == rol_perms for rol in miembro.roles)


# ═══════════════════════════════════════════════════════════════════
#  MODALES
# ═══════════════════════════════════════════════════════════════════

class ModalSumarMisionURA(discord.ui.Modal, title="Sumar Misión a U.R.A"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", placeholder="Ej: 123456789012345678", min_length=17, max_length=21, required=True)
    cantidad = discord.ui.TextInput(label="Cantidad de misiones a sumar", placeholder="Ej: 1", default="1", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_id = int(self.discord_id.value.strip())
            cant = int(self.cantidad.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID o cantidad inválida.", ephemeral=True)

        cursor_ura.execute("""
            INSERT INTO ura_top_misiones (guild_id, user_id, misiones)
            VALUES (%s, %s, %s)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET misiones = ura_top_misiones.misiones + %s
        """, (target_id, cant, cant))
        conn_ura.commit()

        await interaction.response.send_message(f"✅ Se han sumado **{cant}** misiones al oficial <@{target_id}> en el Top Semanal.", ephemeral=True)


class ModalNuevoURA(discord.ui.Modal, title="Nuevo Miembro — U.R.A"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", placeholder="Ej: 123456789012345678",
                                       min_length=17, max_length=21, required=True)
    motivo = discord.ui.TextInput(label="Motivo de ingreso (opcional)", style=discord.TextStyle.paragraph,
                                   placeholder="Ej: Aprobó las pruebas...", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        miembro = await buscar_miembro(interaction, self.discord_id.value)
        if not miembro:
            return

        guild_id = interaction.guild.id
        rol_ura_id = _get_ura_rol_id(guild_id, "ROL_URA_ID")
        rol_ura = interaction.guild.get_role(rol_ura_id)
        if rol_ura and rol_ura in miembro.roles:
            return await interaction.response.send_message(
                f"⚠️ {miembro.mention} ya tiene el rol de U.R.A.", ephemeral=True)

        roles_a_dar = []
        if rol_ura:
            roles_a_dar.append(rol_ura)
        if JERARQUIA_URA:
            primer_nombre, _, primer_tier = JERARQUIA_URA[0]
            primer_id = _get_ura_rol_id(guild_id, JERARQUIA_URA[0])
            r = interaction.guild.get_role(primer_id)
            if r:
                roles_a_dar.append(r)
            
            tier_name = {
                "low": "ROL_LOW_URA_ID",
                "high": "ROL_HIGH_URA_ID",
                "head": "ROL_HEAD_URA_ID",
            }.get(primer_tier)
            tier_rol_id = _get_ura_rol_id(guild_id, tier_name) if tier_name else 0
            if tier_rol_id:
                tr = interaction.guild.get_role(tier_rol_id)
                if tr:
                    roles_a_dar.append(tr)

        if not roles_a_dar:
            return await interaction.response.send_message(
                "❌ Error de configuración: roles no encontrados.", ephemeral=True)

        try:
            await miembro.add_roles(*roles_a_dar, reason=f"Nuevo URA — por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(mensaje_sin_permisos_bot(), ephemeral=True)

        motivo_t = self.motivo.value.strip() if self.motivo.value else "Sin especificar"
        rango_n = JERARQUIA_URA[0][0] if JERARQUIA_URA else "Miembro"

        await enviar_log(interaction,
            f"🚘✅ {miembro.mention} -> {rango_n} -> **Nuevo ingreso** "
            f"[Por: {interaction.user.mention}]. Motivo: {motivo_t}")

        await interaction.response.send_message(
            f"✅ **Miembro ingresado a U.R.A.**\n\n"
            f"👤 {miembro.mention}\n🎖️ `{rango_n}`\n📝 {motivo_t}", ephemeral=True)


class ModalRemoverURA(discord.ui.Modal, title="Remover Miembro — U.R.A"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", placeholder="Ej: 123456789012345678",
                                       min_length=17, max_length=21, required=True)
    motivo = discord.ui.TextInput(label="Motivo de remoción", style=discord.TextStyle.paragraph,
                                   placeholder="Ej: Inactividad...", min_length=5, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        miembro = await buscar_miembro(interaction, self.discord_id.value)
        if not miembro:
            return

        guild_id = interaction.guild.id
        roles_a_quitar = []
        for rol_name in ["ROL_URA_ID", "ROL_LOW_URA_ID", "ROL_HIGH_URA_ID", "ROL_HEAD_URA_ID"]:
            rol_id = _get_ura_rol_id(guild_id, rol_name)
            r = interaction.guild.get_role(rol_id)
            if r and r in miembro.roles:
                roles_a_quitar.append(r)
        for item in JERARQUIA_URA:
            rol_id = _get_ura_rol_id(guild_id, item)
            r = interaction.guild.get_role(rol_id)
            if r and r in miembro.roles:
                roles_a_quitar.append(r)

        if not roles_a_quitar:
            return await interaction.response.send_message(
                f"⚠️ {miembro.mention} no tiene roles de U.R.A.", ephemeral=True)

        try:
            await miembro.remove_roles(*roles_a_quitar, reason=f"Removido de URA por {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message(mensaje_sin_permisos_bot(), ephemeral=True)

        motivo_t = self.motivo.value.strip()

        try:
            embed_dm = discord.Embed(title="🚁  Notificación — U.R.A",
                description=f"Has sido **removido** de la **Unidad Rápida de Acción**.\n\n"
                            f"📝 **Motivo:** {motivo_t}\n"
                            f"👨‍⚖️ **Por:** {interaction.user.display_name}\n\n"
                            f"Si hubo un error, contacta a un superior.",
                color=0xE53E3E)
            embed_dm.set_footer(text="Equipo Administrativo — P.F.A")
            await miembro.send(embed=embed_dm)
        except discord.Forbidden:
            pass

        await enviar_log(interaction,
            f"🚘❌ {miembro.mention} -> **Removido de U.R.A** "
            f"[Por: {interaction.user.mention}]. Motivo: {motivo_t}")

        await interaction.response.send_message(
            f"✅ **Miembro removido de U.R.A.**\n\n"
            f"👤 {miembro.mention}\n📝 {motivo_t}\n📩 Notificado por MD.", ephemeral=True)


class ModalPromoteURA(discord.ui.Modal, title="Ascender Miembro — U.R.A"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", placeholder="Ej: 123456789012345678",
                                       min_length=17, max_length=21, required=True)
    motivo = discord.ui.TextInput(label="Motivo del ascenso (opcional)", style=discord.TextStyle.paragraph,
                                   placeholder="Ej: Buen desempeño...", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if len(JERARQUIA_URA) < 2:
            return await interaction.followup.send("❌ Jerarquía no configurada.", ephemeral=True)

        miembro = await buscar_miembro(interaction, self.discord_id.value)
        if not miembro:
            return

        idx = get_rango_actual(miembro, interaction.guild)
        if idx == -1:
            return await interaction.followup.send(
                f"⚠️ {miembro.mention} no tiene rango de U.R.A.", ephemeral=True)
        if idx >= len(JERARQUIA_URA) - 1:
            return await interaction.followup.send(
                f"⚠️ {miembro.mention} ya tiene el rango más alto (`{JERARQUIA_URA[-1][0]}`).", ephemeral=True)

        guild_id = interaction.guild.id
        viejo_nombre, _, viejo_tier = JERARQUIA_URA[idx]
        nuevo_nombre, _, nuevo_tier = JERARQUIA_URA[idx + 1]
        
        viejo_id = _get_ura_rol_id(guild_id, JERARQUIA_URA[idx])
        nuevo_id = _get_ura_rol_id(guild_id, JERARQUIA_URA[idx + 1])

        try:
            rol_v = interaction.guild.get_role(viejo_id)
            rol_n = interaction.guild.get_role(nuevo_id)
            if rol_v:
                await miembro.remove_roles(rol_v, reason=f"Promote URA por {interaction.user}")
            if rol_n:
                await miembro.add_roles(rol_n, reason=f"Promote URA por {interaction.user}")
            await swap_tier_roles(miembro, interaction.guild, viejo_tier, nuevo_tier)
        except discord.Forbidden:
            return await interaction.followup.send(mensaje_sin_permisos_bot(), ephemeral=True)

        motivo_t = self.motivo.value.strip() if self.motivo.value else "Sin especificar"
        tier_msg = f" (Tier: {viejo_tier.upper()} → {nuevo_tier.upper()})" if viejo_tier != nuevo_tier else ""

        await enviar_log(interaction,
            f"🚘⬆️ {miembro.mention} -> {viejo_nombre} → **{nuevo_nombre}**{tier_msg} "
            f"[Por: {interaction.user.mention}]. Motivo: {motivo_t}")

        await interaction.followup.send(
            f"✅ **Miembro ascendido en U.R.A.**\n\n"
            f"👤 {miembro.mention}\n📉 `{viejo_nombre}` → 📈 `{nuevo_nombre}`"
            f"{f'{chr(10)}🔄 Tier: `{viejo_tier.upper()}` → `{nuevo_tier.upper()}`' if viejo_tier != nuevo_tier else ''}"
            f"\n📝 {motivo_t}", ephemeral=True)


class ModalDemoteURA(discord.ui.Modal, title="Descender Miembro — U.R.A"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", placeholder="Ej: 123456789012345678",
                                       min_length=17, max_length=21, required=True)
    motivo = discord.ui.TextInput(label="Motivo del descenso", style=discord.TextStyle.paragraph,
                                   placeholder="Ej: Incumplimiento...", min_length=5, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if len(JERARQUIA_URA) < 2:
            return await interaction.followup.send("❌ Jerarquía no configurada.", ephemeral=True)

        miembro = await buscar_miembro(interaction, self.discord_id.value)
        if not miembro:
            return

        idx = get_rango_actual(miembro, interaction.guild)
        if idx == -1:
            return await interaction.followup.send(
                f"⚠️ {miembro.mention} no tiene rango de U.R.A.", ephemeral=True)
        if idx <= 0:
            return await interaction.followup.send(
                f"⚠️ {miembro.mention} ya tiene el rango más bajo (`{JERARQUIA_URA[0][0]}`).", ephemeral=True)

        guild_id = interaction.guild.id
        viejo_nombre, _, viejo_tier = JERARQUIA_URA[idx]
        nuevo_nombre, _, nuevo_tier = JERARQUIA_URA[idx - 1]
        
        viejo_id = _get_ura_rol_id(guild_id, JERARQUIA_URA[idx])
        nuevo_id = _get_ura_rol_id(guild_id, JERARQUIA_URA[idx - 1])

        try:
            rol_v = interaction.guild.get_role(viejo_id)
            rol_n = interaction.guild.get_role(nuevo_id)
            if rol_v:
                await miembro.remove_roles(rol_v, reason=f"Demote URA por {interaction.user}")
            if rol_n:
                await miembro.add_roles(rol_n, reason=f"Demote URA por {interaction.user}")
            await swap_tier_roles(miembro, interaction.guild, viejo_tier, nuevo_tier)
        except discord.Forbidden:
            return await interaction.followup.send(mensaje_sin_permisos_bot(), ephemeral=True)

        motivo_t = self.motivo.value.strip()
        tier_msg = f" (Tier: {viejo_tier.upper()} → {nuevo_tier.upper()})" if viejo_tier != nuevo_tier else ""

        try:
            embed_dm = discord.Embed(title="🚘  Notificación — U.R.A",
                description=f"Has sido **descendido** en la **Unidad Rápida de Acción**.\n\n"
                            f"📉 `{viejo_nombre}` → `{nuevo_nombre}`\n"
                            f"📝 **Motivo:** {motivo_t}\n\n"
                            f"Si hubo un error, contacta a un superior.",
                color=0xE5A100)
            embed_dm.set_footer(text="Equipo Administrativo — P.F.A")
            await miembro.send(embed_dm)
        except discord.Forbidden:
            pass

        await enviar_log(interaction,
            f"🚘⬇️ {miembro.mention} -> {viejo_nombre} → **{nuevo_nombre}**{tier_msg} "
            f"[Por: {interaction.user.mention}]. Motivo: {motivo_t}")

        await interaction.followup.send(
            f"✅ **Miembro descendido en U.R.A.**\n\n"
            f"👤 {miembro.mention}\n📉 `{viejo_nombre}` → `{nuevo_nombre}`"
            f"{f'{chr(10)}🔄 Tier: `{viejo_tier.upper()}` → `{nuevo_tier.upper()}`' if viejo_tier != nuevo_tier else ''}"
            f"\n📝 {motivo_t}\n📩 Notificado por MD.", ephemeral=True)


# ═══════════════════════════════════════════════════════════════════
class SelectRangoURAMultiple(discord.ui.Select):
    def __init__(self, miembro, idx_actual):
        self.miembro = miembro
        self.idx_actual = idx_actual

        opciones = []
        for i in range(idx_actual + 1, len(JERARQUIA_URA)):
            nombre_rango, _, _ = JERARQUIA_URA[i]
            numero_opcion = i - idx_actual
            opciones.append(
                discord.SelectOption(
                    label=f"{numero_opcion} - {nombre_rango}",
                    value=str(i),
                    description=f"Subir {i - idx_actual} rango(s)"
                )
            )

        super().__init__(
            placeholder="Selecciona el rango destino...",
            min_values=1,
            max_values=1,
            options=opciones
        )

    async def callback(self, interaction: discord.Interaction):
        for option in self.options:
            option.default = (option.value == self.values[0])

        await interaction.response.edit_message(view=self.view)


class ViewSelectRangoURAMultiple(discord.ui.View):
    def __init__(self, miembro, idx_actual, motivo):
        super().__init__(timeout=60)
        self.miembro = miembro
        self.idx_actual = idx_actual
        self.motivo = motivo
        self.add_item(SelectRangoURAMultiple(miembro, idx_actual))

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, emoji="✅")
    async def btn_confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        select = next((x for x in self.children if isinstance(x, SelectRangoURAMultiple)), None)

        if not select or not select.values:
            return await interaction.response.send_message("❌ Por favor, selecciona un rango primero.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        idx_final = int(select.values[0])
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass
        await ejecutar_promote_multiple_ura(interaction, self.miembro, self.idx_actual, idx_final, self.motivo)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger, emoji="❌")
    async def btn_cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass


async def ejecutar_promote_multiple_ura(interaction, miembro, idx_actual, idx_final, motivo):
    tier_anterior = JERARQUIA_URA[idx_actual][2]
    cantidad_rangos = idx_final - idx_actual
    motivo_t = motivo.strip() if motivo else "Sin especificar"

    try:
        guild_id = interaction.guild.id
        viejo_nombre, _, viejo_tier = JERARQUIA_URA[idx_actual]
        viejo_id = _get_ura_rol_id(guild_id, JERARQUIA_URA[idx_actual])
        rol_v = interaction.guild.get_role(viejo_id)
        if rol_v and rol_v in miembro.roles:
            await miembro.remove_roles(rol_v, reason=f"Promote Multiple URA por {interaction.user}: {motivo_t}")

        rango_nuevo_nombre, _, tier_final = JERARQUIA_URA[idx_final]
        rango_nuevo_id = _get_ura_rol_id(guild_id, JERARQUIA_URA[idx_final])
        rol_n = interaction.guild.get_role(rango_nuevo_id)
        if rol_n:
            await miembro.add_roles(rol_n, reason=f"Promote Multiple URA por {interaction.user}: {motivo_t}")

        await swap_tier_roles(miembro, interaction.guild, tier_anterior, tier_final)

    except discord.Forbidden:
        return await interaction.followup.send(mensaje_sin_permisos_bot(), ephemeral=True)

    rango_viejo = JERARQUIA_URA[idx_actual][0]
    rango_nuevo = JERARQUIA_URA[idx_final][0]
    tier_msg = f" (Tier: {tier_anterior.upper()} → {tier_final.upper()})" if tier_anterior != tier_final else ""

    log_mensaje = (
        f"🚘⬆️ {miembro.mention} -> Ascenso Múltiple ({cantidad_rangos} rango(s))\n"
        f"📉 De: `{rango_viejo}`\n"
        f"📈 A: `{rango_nuevo}`{tier_msg}\n"
        f"📝 Motivo: {motivo_t}\n"
        f"[Por: {interaction.user.mention}]"
    )

    await enviar_log(interaction, log_mensaje)

    await interaction.followup.send(
        f"✅ **Miembro ascendido ({cantidad_rangos} rango(s)) en U.R.A.**\n\n"
        f"👤 {miembro.mention}\n"
        f"📉 `{rango_viejo}`\n"
        f"📈 `{rango_nuevo}`"
        f"{f'{chr(10)}🔄 Tier: `{tier_anterior.upper()}` → `{tier_final.upper()}`' if tier_anterior != tier_final else ''}"
        f"\n📝 {motivo_t}",
        ephemeral=True)


class ModalPromoteURAMultiple(discord.ui.Modal, title="Ascender Miembro — U.R.A (MÚLTIPLE)"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", placeholder="Ej: 123456789012345678",
                                       min_length=17, max_length=21, required=True)
    motivo = discord.ui.TextInput(label="Motivo del ascenso (opcional)", style=discord.TextStyle.paragraph,
                                  placeholder="Ej: Buen desempeño...", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if len(JERARQUIA_URA) < 2:
            return await interaction.followup.send("❌ Jerarquía no configurada.", ephemeral=True)

        miembro = await buscar_miembro(interaction, self.discord_id.value)
        if not miembro:
            return

        idx = get_rango_actual(miembro, interaction.guild)
        if idx == -1:
            return await interaction.followup.send(
                f"⚠️ {miembro.mention} no tiene rango de U.R.A.", ephemeral=True)

        if idx >= len(JERARQUIA_URA) - 1:
            return await interaction.followup.send(
                f"⚠️ {miembro.mention} ya tiene el rango más alto (`{JERARQUIA_URA[-1][0]}`).", ephemeral=True)

        await interaction.followup.send(
            f"👤 **Selecciona el rango destino para {miembro.mention}:**\n"
            f"🎖️ Rango actual: `{JERARQUIA_URA[idx][0]}`\n\n"
            f"📝 Motivo: {self.motivo.value.strip()}\n\n"
            f"Elige el rango deseado en el menú desplegable y presiona **Confirmar**.",
            view=ViewSelectRangoURAMultiple(miembro, idx, self.motivo.value),
            ephemeral=True
        )


#  VIEW: PANEL PRINCIPAL
# ═══════════════════════════════════════════════════════════════════

class ViewPanelGestionURA(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def _tiene_permiso(self, interaction):
        return tiene_permiso_panel_ura(interaction.user)

    @discord.ui.button(label="New", style=discord.ButtonStyle.success, emoji="✅", custom_id="panel_ura_new_v2", row=0)
    async def btn_new(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalNuevoURA())

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, emoji="❌", custom_id="panel_ura_remove_v2", row=0)
    async def btn_remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalRemoverURA())

    @discord.ui.button(label="Promote", style=discord.ButtonStyle.success, emoji="⬆️", custom_id="panel_ura_promote_v2", row=0)
    async def btn_promote(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalPromoteURAMultiple())

    @discord.ui.button(label="Promote x1", style=discord.ButtonStyle.secondary, emoji="⬆️", custom_id="panel_ura_promote_simple_v2", row=0)
    async def btn_promote_simple(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalPromoteURA())

    @discord.ui.button(label="Demote", style=discord.ButtonStyle.secondary, emoji="⬇️", custom_id="panel_ura_demote_v2", row=0)
    async def btn_demote(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalDemoteURA())

    # --- NUEVOS BOTONES DE TOP MISIONES ---
    @discord.ui.button(label="Top Misiones", style=discord.ButtonStyle.primary, emoji="🏆", custom_id="panel_ura_top_misiones_v1", row=1)
    async def btn_top_misiones(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor_ura.execute("SELECT user_id, misiones FROM ura_top_misiones WHERE guild_id = %s AND misiones > 0 ORDER BY misiones DESC LIMIT 15", (interaction.guild.id,))
        resultados = cursor_ura.fetchall()

        if not resultados:
            return await interaction.response.send_message("📭 Todavía no hay misiones registradas en el Top esta semana.", ephemeral=True)

        embed = discord.Embed(
            title="🏆 TOP MISIONES U.R.A - SEMANAL",
            description="Estos son los oficiales con más misiones completadas esta semana:\n\n",
            color=0xE91E63,
            timestamp=discord.utils.utcnow()
        )

        desc = ""
        medallas = {1: "🥇", 2: "🥈", 3: "🥉"}
        for i, (uid, mis) in enumerate(resultados, start=1):
            medalla = medallas.get(i, "🎖️")
            desc += f"{medalla} <@{uid}> — **{mis}** misiones\n"

        embed.description += desc
        embed.set_footer(text="Se reinicia automáticamente los domingos a las 12:00 Arg.")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Sumar Misión (Staff)", style=discord.ButtonStyle.secondary, emoji="➕", custom_id="panel_ura_add_mision_v1", row=1)
    async def btn_add_mision(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso para sumar puntos al Top.", ephemeral=True)
        await interaction.response.send_modal(ModalSumarMisionURA())


# ═══════════════════════════════════════════════════════════════════
#  COG
# ═══════════════════════════════════════════════════════════════════

class GestionURA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(ViewPanelGestionURA())
        if not self.reset_top_ura_semanal.is_running():
            self.reset_top_ura_semanal.start()
        print("✅ [Cog] Panel Gestión U.R.A cargado y Cronómetro del Top activado.")

    @app_commands.command(name="gestionura", description="Despliega el Panel de Gestión de miembros U.R.A.")
    async def gestionura(self, interaction: discord.Interaction):
        if not tiene_permiso_desplegar(interaction.user):
            return await interaction.response.send_message("⛔ Sin permiso.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(color=0xE91E63, timestamp=discord.utils.utcnow())
        embed.description = (
            "## 🚘  Gestión de Miembros — U.R.A\n\n"
            "**¡Hola, encargado U.R.A!**\n\n"
            "Este panel te permite gestionar los miembros de la Unidad Rápida de Acción.\n\n"
            "✅ **New:** Ingresa a un nuevo miembro a U.R.A.\n"
            "❌ **Remove:** Remueve a un miembro de U.R.A (se le notifica por MD).\n"
            "⬆️ **Promote:** Asciende a un miembro al rango que desees.\n"
            "⬆️ **Promote x1:** Asciende a un miembro al siguiente rango.\n"
            "⬇️ **Demote:** Desciende a un miembro al rango anterior.\n"
            "🏆 **Top Misiones:** Visualiza a los oficiales con más misiones completadas.\n"
            "➕ **Sumar Misión:** (Solo Staff) Añade misiones manualmente al contador del oficial.\n\n"
            "🔄 *Los roles de tier (Low/High/Head) se actualizan automáticamente.*\n\n"
            "Utiliza estos botones de forma responsable."
        )
        embed.set_footer(text="PFA – Ibiza Roleplay")

        await limpiar_paneles_ura(interaction.channel, self.bot.user)
        await interaction.channel.send(embed=embed, view=ViewPanelGestionURA())
        await asyncio.sleep(1)
        await dejar_un_solo_panel_ura(interaction.channel, self.bot.user)
        await interaction.followup.send("✅ Panel U.R.A desplegado.", ephemeral=True)

    # LOOP AUTOMÁTICO: Reset todos los Domingos a las 12:00 PM ARG (15:00 UTC)
    # Nota: Si referías a las 00:00 (Medianoche), cambia hour=15 a hour=3
    @tasks.loop(time=datetime.time(hour=15, minute=0, tzinfo=datetime.timezone.utc))
    async def reset_top_ura_semanal(self):
        ahora = discord.utils.utcnow()
        if ahora.weekday() == 6:  # 6 equivale a Domingo
            cursor_ura.execute("SELECT user_id, misiones FROM ura_top_misiones WHERE guild_id = %s AND misiones > 0 ORDER BY misiones DESC LIMIT 15", (interaction.guild.id,))
            resultados = cursor_ura.fetchall()

            for guild in self.bot.guilds:
                canal_id = _get_ura_rol_id(guild.id, "CANAL_TOP_MISIONES_URA_ID")
                canal = guild.get_channel(canal_id) if canal_id else None
                if canal:
                    if resultados:
                        embed = discord.Embed(
                            title="🏆 TOP MISIONES U.R.A - CIERRE SEMANAL",
                            description="¡Finalizó la semana! Estos son los oficiales más destacados de la unidad:\n\n",
                            color=0xE91E63
                        )
                        desc = ""
                        medallas = {1: "🥇", 2: "🥈", 3: "🥉"}
                        for i, (uid, mis) in enumerate(resultados, start=1):
                            medalla = medallas.get(i, "🎖️")
                            desc += f"{medalla} <@{uid}> — **{mis}** misiones\n"
                        embed.description += desc
                        embed.set_footer(text="Contador semanal reiniciado a 0.")
                        await canal.send(embed=embed)
                    else:
                        await canal.send("🏆 **TOP MISIONES U.R.A - CIERRE SEMANAL**\nEsta semana no se registraron misiones completadas. Contador reiniciado a 0.")

            # Limpiar la tabla para empezar la nueva semana
            cursor_ura.execute("DELETE FROM ura_top_misiones WHERE guild_id = %s", (guild.id,))
            conn_ura.commit()
            print("🧹 [SISTEMA] Top URA semanal reiniciado (Domingo 12:00 Arg).")

    @reset_top_ura_semanal.before_loop
    async def before_reset(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(GestionURA(bot))
