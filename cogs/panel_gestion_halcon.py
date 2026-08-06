import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════════════════════════════
#  PANEL DE GESTIÓN — HALCÓN
# ═══════════════════════════════════════════════════════════════════

# --- CONFIG ---
from utils.config import obtener_config_int

ROL_HALCON_ID = 1441595283808063610
CANAL_LOGS_HALCON_ID = 1409352142745243688
ROL_PANEL_HALCON_ADMIN_ID = 1500021425891708959
ROL_PERMS = 1351228669359558809

# Roles de TIER (UN solo rol por tier — se swappean automáticamente)
ROL_LOW_HALCON_ID = 1448782122293657703
ROL_HIGH_HALCON_ID = 1448782388317524032
ROL_HEAD_HALCON_ID = 1448784252538720389

def _get_halcon_rol_id(guild_id: int, key_or_tuple) -> int:
    if isinstance(key_or_tuple, tuple):
        raw_name = key_or_tuple[0].replace(" ", "_").replace("º", "_").replace("1", "1_").upper()
        import re
        clean_name = re.sub(r"[^A-Z0-9_]", "", raw_name)
        key = f"ROL_HALCON_RANGO_{clean_name}"
        fallback = key_or_tuple[1]
        return obtener_config_int(guild_id, key, fallback)
    fallback = globals().get(key_or_tuple, 0)
    return obtener_config_int(guild_id, key_or_tuple, fallback) 

TIER_ROLES = {
    "low": ROL_LOW_HALCON_ID,
    "high": ROL_HIGH_HALCON_ID,
    "head": ROL_HEAD_HALCON_ID,
}

# --- JERARQUÍA DE RANGOS (de menor a mayor) ---
# Formato: (nombre, rol_id, tier)
JERARQUIA_HALCON = [
    # --- LOW ---
    ("Aspirante Halcon",            1374188897990348810, "low"),
    ("Agente Halcon",               1506437348525740132, "low"),
    ("Agente Tactico Halcon",       1506437354452418621, "low"),
    ("Agente Especial Halcon",      1506437359401439253, "low"),
    ("Operador Halcon",  1506437373221802044, "low"),
    ("Operador Experimentado Halcon", 1506437376409600111, "low"),
    ("Operador De Elite Halcon", 1506437381895749752, "low"),
    ("Oficial Halcon",              1506437363059003463, "low"),
    ("Oficial Mayor Halcon",        1506437370076074145, "low"),

    # --- HIGH ---
    ("Instructor Halcon", 1506437680659959838, "high"),
    ("Inspector Halcon", 1494045887314530434, "high"),
    ("Sub comandante Halcon", 1506437715384860763, "high"),
    ("Comandante Halcon", 1476328217513169159, "high"),
    ("Sub capitán Halcon", 1506437683751162036, "high"),
    ("Capitán Halcon", 1506437693977137182, "high"),
    ("Supervisor Halcon", 1506437389944623144, "high"),
    ("Supervisor Mayor Halcon", 1506437387327377418, "high"),

    # --- HEAD ---
    ("Sub jefe Halcon", 1442958942224515405, "head"),
    ("Jefe Halcon", 1355764357140844707, "head"),
    ("General Halcon", 1506437703913308280, "head"),
    ("Director Halcon", 1351969989799972915, "head"),
] 


# --- HELPERS ---
def get_rango_actual(miembro, guild):
    """Devuelve el índice del rango actual del miembro, o -1."""
    for idx, item in enumerate(JERARQUIA_HALCON):
        rol_id = _get_halcon_rol_id(guild.id, item)
        rol = guild.get_role(rol_id)
        if rol and rol in miembro.roles:
            return idx
    return -1


async def swap_tier_roles(miembro, guild, tier_viejo, tier_nuevo):
    """Quita el rol de tier viejo y da el nuevo si cambiaron."""
    if tier_viejo == tier_nuevo:
        return
        
    rol_low = _get_halcon_rol_id(guild.id, "ROL_LOW_HALCON_ID")
    rol_high = _get_halcon_rol_id(guild.id, "ROL_HIGH_HALCON_ID")
    rol_head = _get_halcon_rol_id(guild.id, "ROL_HEAD_HALCON_ID")
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

    roles_dar = []
    if rol_dar_id:
        r = guild.get_role(rol_dar_id)
        if r and r not in miembro.roles:
            roles_dar.append(r)
    if roles_quitar:
        await miembro.remove_roles(*roles_quitar, reason=f"Cambio de tier Halcón: {tier_viejo.upper()} -> {tier_nuevo.upper()}")
    if roles_dar:
        await miembro.add_roles(*roles_dar, reason=f"Cambio de tier Halcón: {tier_viejo.upper()} -> {tier_nuevo.upper()}")


async def buscar_miembro(interaction, raw_id):
    """Valida ID y devuelve el miembro o None (ya responde con error)."""
    try:
        target_id = int(raw_id.strip())
    except ValueError:
        await interaction.followup.send("❌ El ID ingresado no es válido.", ephemeral=True)
        return None
    miembro = interaction.guild.get_member(target_id)
    if not miembro:
        try:
            miembro = await interaction.guild.fetch_member(target_id)
        except (discord.NotFound, discord.HTTPException):
            await interaction.followup.send(
                f"❌ No se encontró ningún usuario con el ID `{target_id}`.", ephemeral=True)
            return None
    return miembro


async def enviar_log(interaction, mensaje):
    canal_logs_halcon_id = _get_halcon_rol_id(interaction.guild.id, "CANAL_LOGS_HALCON_ID")
    canal = interaction.guild.get_channel(canal_logs_halcon_id)
    if canal:
        await canal.send(mensaje)


def es_panel_halcon(mensaje):
    for embed in mensaje.embeds:
        texto = " ".join(
            parte or ""
            for parte in (embed.title, embed.description, embed.footer.text if embed.footer else "")
        )
        if "Gestión de Miembros" in texto and "Halcón" in texto:
            return True

    for fila in mensaje.components:
        for componente in fila.children:
            custom_id = getattr(componente, "custom_id", "") or ""
            if custom_id.startswith("panel_halcon_"):
                return True

    return False


async def limpiar_paneles_halcon(canal, bot_user):
    async for mensaje in canal.history(limit=100):
        if mensaje.author.id != bot_user.id:
            continue
        if not es_panel_halcon(mensaje):
            continue
        try:
            await mensaje.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass


async def dejar_un_solo_panel_halcon(canal, bot_user):
    paneles = []
    async for mensaje in canal.history(limit=100):
        if mensaje.author.id == bot_user.id and es_panel_halcon(mensaje):
            paneles.append(mensaje)

    if len(paneles) <= 1:
        return

    paneles.sort(key=lambda mensaje: mensaje.created_at, reverse=True)
    for mensaje in paneles[1:]:
        try:
            await mensaje.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass


def tiene_permiso_panel_halcon(miembro):
    if miembro.id == miembro.guild.owner_id or miembro.guild_permissions.administrator:
        return True
    rol_panel_halcon_admin_id = _get_halcon_rol_id(miembro.guild.id, "ROL_PANEL_HALCON_ADMIN_ID")
    rol_perms = _get_halcon_rol_id(miembro.guild.id, "ROL_PERMS")
    nombres_permitidos = {"panel halcón", "perms"}
    return any(
        rol.id in (rol_panel_halcon_admin_id, rol_perms)
        or normalizar_nombre_rol(rol.name) in nombres_permitidos
        or ("panel" in normalizar_nombre_rol(rol.name) and any(alias in normalizar_nombre_rol(rol.name) for alias in ("halcon", "halcón")))
        for rol in miembro.roles
    )


def tiene_permiso_desplegar(miembro):
    if miembro.id == miembro.guild.owner_id or miembro.guild_permissions.administrator:
        return True
    rol_perms = _get_halcon_rol_id(miembro.guild.id, "ROL_PERMS")
    return any(rol.id == rol_perms or normalizar_nombre_rol(rol.name) == "perms" for rol in miembro.roles)


def normalizar_nombre_rol(nombre):
    return "".join(c for c in nombre.casefold() if c.isalnum())


# ═══════════════════════════════════════════════════════════════════
#  MODALES
# ═══════════════════════════════════════════════════════════════════

class ModalNuevoHalcon(discord.ui.Modal, title="Nuevo Miembro — Halcón"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", placeholder="Ej: 123456789012345678",
                                       min_length=17, max_length=21, required=True)
    motivo = discord.ui.TextInput(label="Motivo de ingreso (opcional)", style=discord.TextStyle.paragraph,
                                   placeholder="Ej: Aprobó las pruebas...", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        miembro = await buscar_miembro(interaction, self.discord_id.value)
        if not miembro:
            return

        guild_id = interaction.guild.id
        rol_halcon_id = _get_halcon_rol_id(guild_id, "ROL_HALCON_ID")
        rol_halcon = interaction.guild.get_role(rol_halcon_id)
        if rol_halcon and rol_halcon in miembro.roles:
            return await interaction.followup.send(
                f"⚠️ {miembro.mention} ya tiene el rol de Halcón.", ephemeral=True)

        # Roles a dar: Halcón base + primer rango + tier del primer rango
        roles_a_dar = []
        if rol_halcon:
            roles_a_dar.append(rol_halcon)
        if JERARQUIA_HALCON:
            primer_nombre, _, primer_tier = JERARQUIA_HALCON[0]
            primer_id = _get_halcon_rol_id(guild_id, JERARQUIA_HALCON[0])
            r = interaction.guild.get_role(primer_id)
            if r:
                roles_a_dar.append(r)
                
            tier_name = {
                "low": "ROL_LOW_HALCON_ID",
                "high": "ROL_HIGH_HALCON_ID",
                "head": "ROL_HEAD_HALCON_ID",
            }.get(primer_tier)
            tier_rol_id = _get_halcon_rol_id(guild_id, tier_name) if tier_name else 0
            if tier_rol_id:
                tr = interaction.guild.get_role(tier_rol_id)
                if tr:
                    roles_a_dar.append(tr)

        if not roles_a_dar:
            return await interaction.followup.send(
                "❌ Error de configuración: roles no encontrados.", ephemeral=True)

        try:
            await miembro.add_roles(*roles_a_dar, reason=f"Nuevo Halcón — por {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(
                "❌ No tengo permisos suficientes.", ephemeral=True)

        motivo_t = self.motivo.value.strip() if self.motivo.value else "Sin especificar"
        rango_n = JERARQUIA_HALCON[0][0] if JERARQUIA_HALCON else "Miembro"

        await enviar_log(interaction,
            f"🦅✅ {miembro.mention} -> {rango_n} -> **Nuevo ingreso** "
            f"[Por: {interaction.user.mention}]. Motivo: {motivo_t}")

        await interaction.followup.send(
            f"✅ **Miembro ingresado a Halcón.**\n\n"
            f"👤 {miembro.mention}\n🎖️ `{rango_n}`\n📝 {motivo_t}", ephemeral=True)


class ModalRemoverHalcon(discord.ui.Modal, title="Remover Miembro — Halcón"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", placeholder="Ej: 123456789012345678",
                                       min_length=17, max_length=21, required=True)
    motivo = discord.ui.TextInput(label="Motivo de remoción", style=discord.TextStyle.paragraph,
                                   placeholder="Ej: Inactividad...", min_length=5, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        miembro = await buscar_miembro(interaction, self.discord_id.value)
        if not miembro:
            return

        # Recopilar TODOS los roles Halcón (base + rangos + tiers)
        guild_id = interaction.guild.id
        roles_a_quitar = []
        for rol_name in ["ROL_HALCON_ID", "ROL_LOW_HALCON_ID", "ROL_HIGH_HALCON_ID"]:
            rol_id = _get_halcon_rol_id(guild_id, rol_name)
            r = interaction.guild.get_role(rol_id)
            if r and r in miembro.roles:
                roles_a_quitar.append(r)
        for item in JERARQUIA_HALCON:
            rol_id = _get_halcon_rol_id(guild_id, item)
            r = interaction.guild.get_role(rol_id)
            if r and r in miembro.roles:
                roles_a_quitar.append(r)

        if not roles_a_quitar:
            return await interaction.followup.send(
                f"⚠️ {miembro.mention} no tiene roles de Halcón.", ephemeral=True)

        try:
            await miembro.remove_roles(*roles_a_quitar, reason=f"Removido de Halcón por {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send("❌ Sin permisos.", ephemeral=True)

        motivo_t = self.motivo.value.strip()

        # MD al usuario
        try:
            embed_dm = discord.Embed(title="🦅  Notificación — Halcón",
                description=f"Has sido **removido** de la subdivisión **Halcón**.\n\n"
                            f"📝 **Motivo:** {motivo_t}\n"
                            f"👨‍⚖️ **Por:** {interaction.user.display_name}\n\n"
                            f"Si hubo un error, contacta a un superior.",
                color=0xE53E3E)
            embed_dm.set_footer(text="Equipo Administrativo — P.F.A")
            await miembro.send(embed=embed_dm)
        except discord.Forbidden:
            pass

        await enviar_log(interaction,
            f"🦅❌ {miembro.mention} -> **Removido de Halcón** "
            f"[Por: {interaction.user.mention}]. Motivo: {motivo_t}")

        await interaction.followup.send(
            f"✅ **Miembro removido de Halcón.**\n\n"
            f"👤 {miembro.mention}\n📝 {motivo_t}\n📩 Notificado por MD.", ephemeral=True)


class ModalPromoteHalcon(discord.ui.Modal, title="Ascender Miembro — Halcón"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", placeholder="Ej: 123456789012345678",
                                       min_length=17, max_length=21, required=True)
    motivo = discord.ui.TextInput(label="Motivo del ascenso (opcional)", style=discord.TextStyle.paragraph,
                                   placeholder="Ej: Buen desempeño...", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if len(JERARQUIA_HALCON) < 2:
            return await interaction.followup.send("❌ Jerarquía no configurada.", ephemeral=True)

        miembro = await buscar_miembro(interaction, self.discord_id.value)
        if not miembro:
            return

        idx = get_rango_actual(miembro, interaction.guild)
        if idx == -1:
            return await interaction.followup.send(
                f"⚠️ {miembro.mention} no tiene rango de Halcón.", ephemeral=True)
        if idx >= len(JERARQUIA_HALCON) - 1:
            return await interaction.followup.send(
                f"⚠️ {miembro.mention} ya tiene el rango más alto (`{JERARQUIA_HALCON[-1][0]}`).", ephemeral=True)

        guild_id = interaction.guild.id
        viejo_nombre, _, viejo_tier = JERARQUIA_HALCON[idx]
        nuevo_nombre, _, nuevo_tier = JERARQUIA_HALCON[idx + 1]
        
        viejo_id = _get_halcon_rol_id(guild_id, JERARQUIA_HALCON[idx])
        nuevo_id = _get_halcon_rol_id(guild_id, JERARQUIA_HALCON[idx + 1])

        try:
            rol_v = interaction.guild.get_role(viejo_id)
            rol_n = interaction.guild.get_role(nuevo_id)
            if rol_v:
                await miembro.remove_roles(rol_v, reason=f"Promote Halcón por {interaction.user}")
            if rol_n:
                await miembro.add_roles(rol_n, reason=f"Promote Halcón por {interaction.user}")
            # Swap tier automático
            await swap_tier_roles(miembro, interaction.guild, viejo_tier, nuevo_tier)
        except discord.Forbidden:
            return await interaction.followup.send("❌ Sin permisos.", ephemeral=True)

        motivo_t = self.motivo.value.strip() if self.motivo.value else "Sin especificar"
        tier_msg = f" (Tier: {viejo_tier.upper()} → {nuevo_tier.upper()})" if viejo_tier != nuevo_tier else ""

        await enviar_log(interaction,
            f"🦅⬆️ {miembro.mention} -> {viejo_nombre} → **{nuevo_nombre}**{tier_msg} "
            f"[Por: {interaction.user.mention}]. Motivo: {motivo_t}")

        await interaction.followup.send(
            f"✅ **Miembro ascendido en Halcón.**\n\n"
            f"👤 {miembro.mention}\n📉 `{viejo_nombre}` → 📈 `{nuevo_nombre}`"
            f"{f'{chr(10)}🔄 Tier: `{viejo_tier.upper()}` → `{nuevo_tier.upper()}`' if viejo_tier != nuevo_tier else ''}"
            f"\n📝 {motivo_t}", ephemeral=True)


class ModalDemoteHalcon(discord.ui.Modal, title="Descender Miembro — Halcón"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", placeholder="Ej: 123456789012345678",
                                       min_length=17, max_length=21, required=True)
    motivo = discord.ui.TextInput(label="Motivo del descenso", style=discord.TextStyle.paragraph,
                                   placeholder="Ej: Incumplimiento...", min_length=5, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if len(JERARQUIA_HALCON) < 2:
            return await interaction.followup.send("❌ Jerarquía no configurada.", ephemeral=True)

        miembro = await buscar_miembro(interaction, self.discord_id.value)
        if not miembro:
            return

        idx = get_rango_actual(miembro, interaction.guild)
        if idx == -1:
            return await interaction.followup.send(
                f"⚠️ {miembro.mention} no tiene rango de Halcón.", ephemeral=True)
        if idx <= 0:
            return await interaction.followup.send(
                f"⚠️ {miembro.mention} ya tiene el rango más bajo (`{JERARQUIA_HALCON[0][0]}`).", ephemeral=True)

        guild_id = interaction.guild.id
        viejo_nombre, _, viejo_tier = JERARQUIA_HALCON[idx]
        nuevo_nombre, _, nuevo_tier = JERARQUIA_HALCON[idx - 1]
        
        viejo_id = _get_halcon_rol_id(guild_id, JERARQUIA_HALCON[idx])
        nuevo_id = _get_halcon_rol_id(guild_id, JERARQUIA_HALCON[idx - 1])

        try:
            rol_v = interaction.guild.get_role(viejo_id)
            rol_n = interaction.guild.get_role(nuevo_id)
            if rol_v:
                await miembro.remove_roles(rol_v, reason=f"Demote Halcón por {interaction.user}")
            if rol_n:
                await miembro.add_roles(rol_n, reason=f"Demote Halcón por {interaction.user}")
            # Swap tier automático
            await swap_tier_roles(miembro, interaction.guild, viejo_tier, nuevo_tier)
        except discord.Forbidden:
            return await interaction.followup.send("❌ Sin permisos.", ephemeral=True)

        motivo_t = self.motivo.value.strip()
        tier_msg = f" (Tier: {viejo_tier.upper()} → {nuevo_tier.upper()})" if viejo_tier != nuevo_tier else ""

        # MD al usuario
        try:
            embed_dm = discord.Embed(title="🦅  Notificación — Halcón",
                description=f"Has sido **descendido** en la subdivisión **Halcón**.\n\n"
                            f"📉 `{viejo_nombre}` → `{nuevo_nombre}`\n"
                            f"📝 **Motivo:** {motivo_t}\n\n"
                            f"Si hubo un error, contacta a un superior.",
                color=0xE5A100)
            embed_dm.set_footer(text="Equipo Administrativo — P.F.A")
            await miembro.send(embed=embed_dm)
        except discord.Forbidden:
            pass

        await enviar_log(interaction,
            f"🦅⬇️ {miembro.mention} -> {viejo_nombre} → **{nuevo_nombre}**{tier_msg} "
            f"[Por: {interaction.user.mention}]. Motivo: {motivo_t}")

        await interaction.followup.send(
            f"✅ **Miembro descendido en Halcón.**\n\n"
            f"👤 {miembro.mention}\n📉 `{viejo_nombre}` → `{nuevo_nombre}`"
            f"{f'{chr(10)}🔄 Tier: `{viejo_tier.upper()}` → `{nuevo_tier.upper()}`' if viejo_tier != nuevo_tier else ''}"
            f"\n📝 {motivo_t}\n📩 Notificado por MD.", ephemeral=True)


class SelectRangoHalconMultiple(discord.ui.Select):
    def __init__(self, miembro, idx_actual):
        self.miembro = miembro
        self.idx_actual = idx_actual
        
        # Crear opciones para rangos superiores al actual
        opciones = []
        for i in range(idx_actual + 1, len(JERARQUIA_HALCON)):
            nombre_rango, _, _ = JERARQUIA_HALCON[i]
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
        # Al seleccionar, solo actualizamos el estado (no ejecutamos nada)
        for option in self.options:
            option.default = (option.value == self.values[0])
        
        await interaction.response.edit_message(view=self.view)


class ViewSelectRangoHalconMultiple(discord.ui.View):
    def __init__(self, miembro, idx_actual, motivo):
        super().__init__(timeout=60)
        self.miembro = miembro
        self.idx_actual = idx_actual
        self.motivo = motivo
        self.add_item(SelectRangoHalconMultiple(miembro, idx_actual))

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, emoji="✅")
    async def btn_confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Buscar qué rango fue seleccionado
        select = next((x for x in self.children if isinstance(x, SelectRangoHalconMultiple)), None)
        
        if not select or not select.values:
            return await interaction.response.send_message("❌ Por favor, selecciona un rango primero.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        idx_final = int(select.values[0])
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass
        await ejecutar_promote_multiple(interaction, self.miembro, self.idx_actual, idx_final, self.motivo)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger, emoji="❌")
    async def btn_cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass


async def ejecutar_promote_multiple(interaction, miembro, idx_actual, idx_final, motivo):
    """Ejecuta el promote múltiple - SOLO DA EL RANGO DESTINO"""
    tier_anterior = JERARQUIA_HALCON[idx_actual][2]
    cantidad_rangos = idx_final - idx_actual
    motivo_t = motivo.strip() if motivo else "Sin especificar"

    try:
        # 1. QUITAR el rango actual (solo el actual, no todos)
        guild_id = interaction.guild.id
        viejo_nombre, _, viejo_tier = JERARQUIA_HALCON[idx_actual]
        viejo_id = _get_halcon_rol_id(guild_id, JERARQUIA_HALCON[idx_actual])
        rol_v = interaction.guild.get_role(viejo_id)
        if rol_v and rol_v in miembro.roles:
            await miembro.remove_roles(rol_v, reason=f"Promote Múltiple Halcón por {interaction.user}: {motivo_t}")
        
        # 2. DAR SOLO el rango destino (no los intermedios)
        rango_nuevo_nombre, _, tier_final = JERARQUIA_HALCON[idx_final]
        rango_nuevo_id = _get_halcon_rol_id(guild_id, JERARQUIA_HALCON[idx_final])
        rol_n = interaction.guild.get_role(rango_nuevo_id)
        if rol_n:
            await miembro.add_roles(rol_n, reason=f"Promote Múltiple Halcón por {interaction.user}: {motivo_t}")
        
        # 3. Swap tier automático (solo del inicial al final)
        await swap_tier_roles(miembro, interaction.guild, tier_anterior, tier_final)
        
    except discord.Forbidden:
        return await interaction.followup.send("❌ Sin permisos.", ephemeral=True)

    rango_viejo = JERARQUIA_HALCON[idx_actual][0]
    rango_nuevo = JERARQUIA_HALCON[idx_final][0]
    tier_msg = f" (Tier: {tier_anterior.upper()} → {tier_final.upper()})" if tier_anterior != tier_final else ""

    # Log detallado
    log_mensaje = (
        f"🦅⬆️ {miembro.mention} -> Ascenso Múltiple ({cantidad_rangos} rango(s))\n"
        f"📉 De: `{rango_viejo}`\n"
        f"📈 A: `{rango_nuevo}`{tier_msg}\n"
        f"📝 Motivo: {motivo_t}\n"
        f"[Autorizado Por: {interaction.user.mention}]"
    )
    
    await enviar_log(interaction, log_mensaje)

    await interaction.followup.send(
        f"✅ **Miembro ascendido ({cantidad_rangos} rango(s)) en Halcón.**\n\n"
        f"👤 {miembro.mention}\n"
        f"📉 `{rango_viejo}`\n"
        f"📈 `{rango_nuevo}`"
        f"{f'{chr(10)}🔄 Tier: `{tier_anterior.upper()}` → `{tier_final.upper()}`' if tier_anterior != tier_final else ''}"
        f"\n📝 {motivo_t}",
        ephemeral=True)


class ModalPromoteHalconMultiple(discord.ui.Modal, title="Ascender Miembro — Halcón (MÚLTIPLE)"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", placeholder="Ej: 123456789012345678",
                                       min_length=17, max_length=21, required=True)
    motivo = discord.ui.TextInput(label="Motivo del ascenso (opcional)", style=discord.TextStyle.paragraph,
                                  placeholder="Ej: Buen desempeño...", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if len(JERARQUIA_HALCON) < 2:
            return await interaction.followup.send("❌ Jerarquía no configurada.", ephemeral=True)

        miembro = await buscar_miembro(interaction, self.discord_id.value)
        if not miembro:
            return

        idx = get_rango_actual(miembro, interaction.guild)
        if idx == -1:
            return await interaction.followup.send(
                f"⚠️ {miembro.mention} no tiene rango de Halcón.", ephemeral=True)

        if idx >= len(JERARQUIA_HALCON) - 1:
            return await interaction.followup.send(
                f"⚠️ {miembro.mention} ya tiene el rango más alto (`{JERARQUIA_HALCON[-1][0]}`).", ephemeral=True)

        # Mostrar el selector de rango con botones de confirmación
        await interaction.followup.send(
            f"👤 **Selecciona el rango destino para {miembro.mention}:**\n"
            f"🎖️ Rango actual: `{JERARQUIA_HALCON[idx][0]}`\n\n"
            f"📝 Motivo: {self.motivo.value.strip()}\n\n"
            f"Elige el rango deseado en el menú desplegable y presiona **Confirmar**.",
            view=ViewSelectRangoHalconMultiple(miembro, idx, self.motivo.value),
            ephemeral=True
        )


# ═══════════════════════════════════════════════════════════════════
#  COG
# ═══════════════════════════════════════════════════════════════════

class GestionHalcon(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(ViewPanelGestionHalcon())
        print("✅ [Cog] Panel Gestión Halcón cargado.")

    @app_commands.command(name="gestionhalcon", description="Despliega el Panel de Gestión de miembros Halcón.")
    async def gestionhalcon(self, interaction: discord.Interaction):
        if not tiene_permiso_desplegar(interaction.user):
            return await interaction.response.send_message("⛔ Sin permiso.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(color=discord.Color.dark_embed(), timestamp=discord.utils.utcnow())
        embed.description = (
            "## 🦅 Gestión de Miembros — Halcón\n\n"
            "**¡Hola, encargado!**\n\n"
            "Este panel te permite gestionar los miembros de la subdivisión Halcón.\n\n"
            "✅ **New:** Ingresa a un nuevo miembro a Halcón.\n"
            "❌ **Remove:** Remueve a un miembro de Halcón (se le notifica por MD).\n"
            "⬆️ **Promote:** Asciende a un miembro al rango que desees.\n"
            "⬆️ **Promote x1:** Asciende a un miembro al siguiente rango.\n"
            "⬇️ **Demote:** Desciende a un miembro al rango anterior.\n\n"
            "🔄 *Los roles de tier (Low/High/Head) se actualizan automáticamente.*\n\n"
            "Utiliza estos botones de forma responsable."
        )
        embed.set_footer(text="PFA – Ibiza Roleplay")

        await limpiar_paneles_halcon(interaction.channel, self.bot.user)
        await interaction.channel.send(embed=embed, view=ViewPanelGestionHalcon())
        await asyncio.sleep(1)
        await dejar_un_solo_panel_halcon(interaction.channel, self.bot.user)
        await interaction.followup.send("✅ Panel Halcón desplegado.", ephemeral=True)


class ViewPanelGestionHalcon(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def _tiene_permiso(self, interaction):
        return tiene_permiso_panel_halcon(interaction.user)

    @discord.ui.button(label="New", style=discord.ButtonStyle.success, emoji="✅", custom_id="panel_halcon_new_v2", row=0)
    async def btn_new(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalNuevoHalcon())

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, emoji="❌", custom_id="panel_halcon_remove_v2", row=0)
    async def btn_remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalRemoverHalcon())

    @discord.ui.button(label="Promote", style=discord.ButtonStyle.success, emoji="⬆️", custom_id="panel_halcon_promote_v2", row=0)
    async def btn_promote(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalPromoteHalconMultiple())

    @discord.ui.button(label="Promote x1", style=discord.ButtonStyle.secondary, emoji="⬆️", custom_id="panel_halcon_promote_simple_v2", row=0)
    async def btn_promote_simple(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalPromoteHalcon())

    @discord.ui.button(label="Demote", style=discord.ButtonStyle.secondary, emoji="⬇️", custom_id="panel_halcon_demote_v2", row=0)
    async def btn_demote(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._tiene_permiso(interaction):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalDemoteHalcon())


async def setup(bot):
    await bot.add_cog(GestionHalcon(bot))
