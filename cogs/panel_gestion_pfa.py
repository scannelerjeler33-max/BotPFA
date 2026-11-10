import datetime
import os
import re
import unicodedata
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from databases.connection import get_connection


load_dotenv()


def _env_id(name: str) -> int:
    try:
        return int(os.getenv(name, "0") or 0)
    except ValueError:
        return 0


ROL_PFA_ID = _env_id("ROL_PFA_ID")
ROL_LOWPFA_ID = _env_id("ROL_LOWPFA_ID")
ROL_HIGHPFA_ID = _env_id("ROL_HIGHPFA_ID")
ROL_HEAD_PFA_ID = _env_id("ROL_HEAD_PFA_ID")
ROL_CADETE_ID = _env_id("ROL_CADETE_ID")
ROL_NUEVO_INGRESANTE_ID = _env_id("ROL_NUEVO_INGRESANTE_ID")
ROL_BLACKLIST_PFA_ID = _env_id("ROL_BLACKLIST_PFA_ID")
CANAL_CAMBIOS_PFA_ID = _env_id("CANAL_CAMBIOS_PFA_ID")
ROL_PANEL_ADMIN_ID = _env_id("ROL_PANEL_ADMIN_ID")
ROL_PERMS = _env_id("ROL_PERMS")


conn_pfa = get_connection()
conn_pfa.autocommit = True
cursor_pfa = conn_pfa.cursor()
cursor_pfa.execute(
    """
    CREATE TABLE IF NOT EXISTS pfa_blacklist (
        user_id BIGINT PRIMARY KEY,
        motivo TEXT NOT NULL,
        admin_id BIGINT NOT NULL,
        fecha TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """
)


@dataclass(frozen=True)
class RangoPFA:
    nivel: int
    nombre: str
    env_var: str
    rol_id: int
    tier: str
    beneficio: str = ""


# Estructura estable: 0-12 Low, 13-25 High y 26-33 Head.
JERARQUIA_PFA = [
    RangoPFA(0, "Cadete", "ROL_CADETE_ID", ROL_CADETE_ID, "low", "Ingreso a la PFA, semana de prueba y postulacion U.R.A"),
    RangoPFA(1, "Agente", "ROL_PFA_AGENTE_ID", _env_id("ROL_PFA_AGENTE_ID"), "low", "Pasar la semana de prueba"),
    RangoPFA(2, "Cabo", "ROL_PFA_CABO_ID", _env_id("ROL_PFA_CABO_ID"), "low", "Posibilidad de postulacion Interviewer"),
    RangoPFA(3, "Cabo 1º", "ROL_PFA_CABO_PRIMERO_ID", _env_id("ROL_PFA_CABO_PRIMERO_ID"), "low"),
    RangoPFA(4, "Sargento", "ROL_PFA_SARGENTO_ID", _env_id("ROL_PFA_SARGENTO_ID"), "low"),
    RangoPFA(5, "Sargento 1º", "ROL_PFA_SARGENTO_PRIMERO_ID", _env_id("ROL_PFA_SARGENTO_PRIMERO_ID"), "low", "Ingreso a Aspirante Halcon"),
    RangoPFA(6, "Sargento Mayor", "ROL_PFA_SARGENTO_MAYOR_ID", _env_id("ROL_PFA_SARGENTO_MAYOR_ID"), "low"),
    RangoPFA(7, "Sub Oficial", "ROL_PFA_SUB_OFICIAL_ID", _env_id("ROL_PFA_SUB_OFICIAL_ID"), "low", "Ingreso a Miembro Halcon"),
    RangoPFA(8, "Oficial", "ROL_PFA_OFICIAL_ID", _env_id("ROL_PFA_OFICIAL_ID"), "low", "Corrupcion fuera de servicio"),
    RangoPFA(9, "Oficial 1º", "ROL_PFA_OFICIAL_PRIMERO_ID", _env_id("ROL_PFA_OFICIAL_PRIMERO_ID"), "low"),
    RangoPFA(10, "Oficial 2º", "ROL_PFA_OFICIAL_SEGUNDO_ID", _env_id("ROL_PFA_OFICIAL_SEGUNDO_ID"), "low"),
    RangoPFA(11, "Oficial Mayor", "ROL_PFA_OFICIAL_MAYOR_ID", _env_id("ROL_PFA_OFICIAL_MAYOR_ID"), "low"),
    RangoPFA(12, "Sub Teniente", "ROL_PFA_SUB_TENIENTE_ID", _env_id("ROL_PFA_SUB_TENIENTE_ID"), "low"),
    RangoPFA(13, "Teniente", "ROL_PFA_TENIENTE_ID", _env_id("ROL_PFA_TENIENTE_ID"), "high"),
    RangoPFA(14, "Teniente Coronel", "ROL_PFA_TENIENTE_CORONEL_ID", _env_id("ROL_PFA_TENIENTE_CORONEL_ID"), "high"),
    RangoPFA(15, "Coronel", "ROL_PFA_CORONEL_ID", _env_id("ROL_PFA_CORONEL_ID"), "high"),
    RangoPFA(16, "Sub Inspector", "ROL_PFA_SUB_INSPECTOR_ID", _env_id("ROL_PFA_SUB_INSPECTOR_ID"), "high", "Permiso para hacer doble faccion"),
    RangoPFA(17, "Inspector", "ROL_PFA_INSPECTOR_ID", _env_id("ROL_PFA_INSPECTOR_ID"), "high"),
    RangoPFA(18, "Detective", "ROL_PFA_DETECTIVE_ID", _env_id("ROL_PFA_DETECTIVE_ID"), "high"),
    RangoPFA(19, "Detective 1º", "ROL_PFA_DETECTIVE_PRIMERO_ID", _env_id("ROL_PFA_DETECTIVE_PRIMERO_ID"), "high"),
    RangoPFA(20, "Detective 2º", "ROL_PFA_DETECTIVE_SEGUNDO_ID", _env_id("ROL_PFA_DETECTIVE_SEGUNDO_ID"), "high"),
    RangoPFA(21, "Sub Capitán", "ROL_PFA_SUB_CAPITAN_ID", _env_id("ROL_PFA_SUB_CAPITAN_ID"), "high"),
    RangoPFA(22, "Capitán", "ROL_PFA_CAPITAN_ID", _env_id("ROL_PFA_CAPITAN_ID"), "high"),
    RangoPFA(23, "Comandante", "ROL_PFA_COMANDANTE_ID", _env_id("ROL_PFA_COMANDANTE_ID"), "high"),
    RangoPFA(24, "General", "ROL_PFA_GENERAL_ID", _env_id("ROL_PFA_GENERAL_ID"), "high"),
    RangoPFA(25, "Sub Comisario", "ROL_PFA_SUB_COMISARIO_ID", _env_id("ROL_PFA_SUB_COMISARIO_ID"), "high"),
    RangoPFA(26, "Comisario", "ROL_PFA_COMISARIO_ID", _env_id("ROL_PFA_COMISARIO_ID"), "head"),
    RangoPFA(27, "Instructor", "ROL_PFA_INSTRUCTOR_ID", _env_id("ROL_PFA_INSTRUCTOR_ID"), "head"),
    RangoPFA(28, "Sub Jefe", "ROL_PFA_SUB_JEFE_ID", _env_id("ROL_PFA_SUB_JEFE_ID"), "head"),
    RangoPFA(29, "Jefe", "ROL_PFA_JEFE_ID", _env_id("ROL_PFA_JEFE_ID"), "head"),
    RangoPFA(30, "Director", "ROL_PFA_DIRECTOR_ID", _env_id("ROL_PFA_DIRECTOR_ID"), "head"),
    RangoPFA(31, "Interventor", "ROL_PFA_INTERVENTOR_ID", _env_id("ROL_PFA_INTERVENTOR_ID"), "head"),
    RangoPFA(32, "Co Dueño", "ROL_PFA_CO_DUENO_ID", _env_id("ROL_PFA_CO_DUENO_ID"), "head"),
    RangoPFA(33, "Dueño", "ROL_PFA_DUENO_ID", _env_id("ROL_PFA_DUENO_ID"), "head"),
]

TIER_ROLES = {
    "low": ROL_LOWPFA_ID,
    "high": ROL_HIGHPFA_ID,
    "head": ROL_HEAD_PFA_ID,
}

TIER_INFO = {
    "low": ("LOW PFA", "🔹", discord.Color.blue()),
    "high": ("HIGH PFA", "🔸", discord.Color.gold()),
    "head": ("HEAD PFA", "⭐", discord.Color.purple()),
}


def _nombre_tier(tier: str) -> str:
    return TIER_INFO[tier][0]


def _detalle_cambio_tier(actual: RangoPFA, destino: RangoPFA) -> str:
    if actual.tier == destino.tier:
        return ""
    return f"\n🔄 **Tier:** {_nombre_tier(actual.tier)} → {_nombre_tier(destino.tier)}"


def _mapa_rangos(tier: str) -> str:
    return "\n".join(
        f"`[{rango.nivel:02}]` {rango.nombre}"
        for rango in JERARQUIA_PFA
        if rango.tier == tier
    )


def _embed_selector_ascenso(
    guild: discord.Guild,
    miembro: discord.Member | None = None,
    destino: RangoPFA | None = None,
) -> discord.Embed:
    actual = _rango_actual(miembro) if miembro else None
    if miembro is None:
        estado = (
            "**1.** Seleccioná al miembro que querés ascender o usá "
            "**Buscar por ID** si su nombre es difícil de encontrar."
        )
    elif actual is None:
        estado = f"⚠️ {miembro.mention} no tiene un rango PFA reconocido."
    elif actual.nivel == JERARQUIA_PFA[-1].nivel:
        estado = f"⚠️ {miembro.mention} ya posee el rango máximo."
    else:
        estado = (
            f"**Miembro:** {miembro.mention}\n"
            f"**Rango actual:** `[{actual.nivel:02}] {actual.nombre}`\n"
            "**2.** Elegí el tier y luego el rango de destino."
        )
        if destino:
            estado += (
                f"\n**Destino:** `[{destino.nivel:02}] {destino.nombre}` · "
                f"**+{destino.nivel - actual.nivel}** niveles"
            )
            if actual.tier != destino.tier:
                estado += (
                    f"\n**Cambio de tier:** {_nombre_tier(actual.tier)} → "
                    f"{_nombre_tier(destino.tier)}"
                )

    embed = discord.Embed(
        title="Ascenso PFA · Selección asistida",
        description=(
            f"{estado}\n\n"
            "El sistema solo habilita destinos superiores y actualiza el rol de tier automáticamente."
        ),
        color=discord.Color.gold(),
    )
    if guild.icon:
        embed.set_author(name="Policía Federal Argentina", icon_url=guild.icon.url)
    for tier in ("low", "high", "head"):
        nombre, emoji, _ = TIER_INFO[tier]
        embed.add_field(name=f"{emoji} {nombre}", value=_mapa_rangos(tier), inline=True)
    if miembro is None:
        pie = "Paso 1 de 4 · Selección de miembro"
    elif destino is None:
        pie = "Pasos 2 y 3 de 4 · Selección de tier y rango"
    else:
        pie = "Paso 4 de 4 · Revisá el destino y confirmá"
    embed.set_footer(text=pie)
    return embed


def _ahora() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3)))


def _get_rol_id(guild_id: int, key_or_rango) -> int:
    from utils.config import obtener_config_int
    if isinstance(key_or_rango, RangoPFA):
        return obtener_config_int(guild_id, key_or_rango.env_var, key_or_rango.rol_id)
    fallback = globals().get(key_or_rango, 0)
    return obtener_config_int(guild_id, key_or_rango, fallback)

def _tiene_permiso(miembro: discord.Member) -> bool:
    if miembro.id == miembro.guild.owner_id or miembro.guild_permissions.administrator:
        return True
    rol_admin = _get_rol_id(miembro.guild.id, "ROL_PANEL_ADMIN_ID")
    rol_perms = _get_rol_id(miembro.guild.id, "ROL_PERMS")
    permitidos = {rol_admin, rol_perms}
    return any(rol.id in permitidos for rol in miembro.roles)


def _esta_en_blacklist(user_id: int) -> bool:
    cursor_pfa.execute("SELECT 1 FROM pfa_blacklist WHERE user_id = %s", (user_id,))
    return cursor_pfa.fetchone() is not None


def _agregar_blacklist(user_id: int, motivo: str, admin_id: int) -> None:
    cursor_pfa.execute(
        """
        INSERT INTO pfa_blacklist (user_id, motivo, admin_id, fecha)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            motivo = EXCLUDED.motivo,
            admin_id = EXCLUDED.admin_id,
            fecha = NOW()
        """,
        (user_id, motivo, admin_id),
    )


def _quitar_blacklist(user_id: int) -> bool:
    cursor_pfa.execute(
        "DELETE FROM pfa_blacklist WHERE user_id = %s RETURNING user_id",
        (user_id,),
    )
    return cursor_pfa.fetchone() is not None


def _normalizar_texto_rol(nombre: str) -> str:
    nombre = unicodedata.normalize("NFKD", nombre.casefold())
    nombre = "".join(caracter for caracter in nombre if not unicodedata.combining(caracter))
    return "".join(re.findall(r"[a-z0-9]+", nombre))


def _normalizar_nombre_rango(nombre: str) -> str:
    nombre = unicodedata.normalize("NFKD", nombre.casefold())
    nombre = "".join(caracter for caracter in nombre if not unicodedata.combining(caracter))
    nombre = re.sub(r"^\s*[^a-z0-9]*\d{1,2}[^a-z0-9]*", "", nombre)
    palabras = re.findall(r"[a-z0-9]+", nombre)
    palabras = [palabra for palabra in palabras if palabra not in {"pfa", "low", "high", "head"}]
    return "".join(palabras)


def _tiene_marca_pfa(miembro: discord.Member) -> bool:
    guild_id = miembro.guild.id
    ids_marca = {
        _get_rol_id(guild_id, "ROL_PFA_ID"),
        _get_rol_id(guild_id, "ROL_LOWPFA_ID"),
        _get_rol_id(guild_id, "ROL_HIGHPFA_ID"),
        _get_rol_id(guild_id, "ROL_HEAD_PFA_ID")
    }
    ids_marca.discard(0)
    if any(rol.id in ids_marca for rol in miembro.roles):
        return True

    nombres_marca = {
        "pfa",
        "lowpfa",
        "highpfa",
        "headpfa",
        "policiafederalargentina",
    }
    return any(_normalizar_texto_rol(rol.name) in nombres_marca for rol in miembro.roles)


def _rango_actual(miembro: discord.Member) -> RangoPFA | None:
    guild_id = miembro.guild.id
    ids_miembro = {rol.id for rol in miembro.roles}
    for rango in reversed(JERARQUIA_PFA):
        r_id = _get_rol_id(guild_id, rango)
        if r_id and r_id in ids_miembro:
            return rango

    if _tiene_marca_pfa(miembro):
        rangos_por_nombre = {
            _normalizar_nombre_rango(rango.nombre): rango
            for rango in JERARQUIA_PFA
        }
        detectados = [
            rangos_por_nombre[_normalizar_nombre_rango(rol.name)]
            for rol in miembro.roles
            if _normalizar_nombre_rango(rol.name) in rangos_por_nombre
        ]
        if detectados:
            return max(detectados, key=lambda rango: rango.nivel)
    return None


def _rango_por_nivel(nivel: int) -> RangoPFA | None:
    if 0 <= nivel < len(JERARQUIA_PFA):
        return JERARQUIA_PFA[nivel]
    return None


def _roles_pfa_del_miembro(miembro: discord.Member) -> list[discord.Role]:
    guild_id = miembro.guild.id
    ids_pfa = {
        _get_rol_id(guild_id, "ROL_PFA_ID"),
        _get_rol_id(guild_id, "ROL_LOWPFA_ID"),
        _get_rol_id(guild_id, "ROL_HIGHPFA_ID"),
        _get_rol_id(guild_id, "ROL_HEAD_PFA_ID"),
        _get_rol_id(guild_id, "ROL_NUEVO_INGRESANTE_ID"),
        *(_get_rol_id(guild_id, rango) for rango in JERARQUIA_PFA),
    }
    ids_pfa.discard(0)
    roles = [rol for rol in miembro.roles if rol.id in ids_pfa]
    if _tiene_marca_pfa(miembro):
        nombres_rangos = {_normalizar_nombre_rango(rango.nombre) for rango in JERARQUIA_PFA}
        roles.extend(
            rol
            for rol in miembro.roles
            if rol not in roles and _normalizar_nombre_rango(rol.name) in nombres_rangos
        )
    return roles


async def _responder(interaction: discord.Interaction, mensaje: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(mensaje, ephemeral=True)
    else:
        await interaction.response.send_message(mensaje, ephemeral=True)


async def _buscar_miembro(interaction: discord.Interaction, raw_id: str) -> discord.Member | None:
    try:
        user_id = int(raw_id.strip())
    except ValueError:
        await _responder(interaction, "❌ El ID ingresado no es valido.")
        return None

    miembro_cache = interaction.guild.get_member(user_id)

    try:
        return await interaction.guild.fetch_member(user_id)
    except discord.NotFound:
        await _responder(interaction, f"❌ No se encontro al usuario {user_id} en el servidor.")
        return None
    except discord.HTTPException:
        if miembro_cache is not None:
            return miembro_cache
        await _responder(interaction, f"❌ No se pudo consultar al usuario {user_id} en Discord.")
        return None


def _validar_rol(guild: discord.Guild, rol_id: int) -> discord.Role | None:
    if not rol_id:
        return None
    return guild.get_role(rol_id)


async def _enviar_log(
    interaction: discord.Interaction,
    titulo: str,
    miembro: discord.Member,
    detalle: str,
    emoji: str,
) -> None:
    canal_cambios_id = _get_rol_id(interaction.guild.id, "CANAL_CAMBIOS_PFA_ID")
    canal = interaction.guild.get_channel(canal_cambios_id)
    if canal is None:
        return

    detalle_formateado = "\n".join(f"> {linea}" for linea in detalle.splitlines())
    fecha_unix = int(discord.utils.utcnow().timestamp())
    mensaje = (
        f"{emoji} **{titulo.upper()}**\n"
        f"> 👤 **Miembro:** {miembro.mention} · `{miembro.id}`\n"
        f"{detalle_formateado}\n"
        f"> 🛡️ **Autorizado por:** {interaction.user.mention} · `{interaction.user.id}`\n"
        f"> 🕒 **Fecha:** <t:{fecha_unix}:F>"
    )
    await canal.send(
        mensaje,
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def _cambiar_rango(
    miembro: discord.Member,
    destino: RangoPFA,
    *,
    reason: str,
) -> tuple[bool, str]:
    guild_id = miembro.guild.id
    rol_destino = _validar_rol(miembro.guild, _get_rol_id(guild_id, destino))
    
    tier_name = {
        "low": "ROL_LOWPFA_ID",
        "high": "ROL_HIGHPFA_ID",
        "head": "ROL_HEAD_PFA_ID",
    }[destino.tier]
    rol_tier = _validar_rol(miembro.guild, _get_rol_id(guild_id, tier_name))

    if rol_destino is None:
        return False, f"Falta configurar {destino.env_var} o el rol no existe."
    if rol_tier is None:
        return False, f"Falta configurar {tier_name} o el rol no existe."

    ids_rangos = {_get_rol_id(guild_id, rango) for rango in JERARQUIA_PFA if _get_rol_id(guild_id, rango)}
    ids_tiers = {
        _get_rol_id(guild_id, "ROL_LOWPFA_ID"),
        _get_rol_id(guild_id, "ROL_HIGHPFA_ID"),
        _get_rol_id(guild_id, "ROL_HEAD_PFA_ID")
    }
    ids_tiers.discard(0)
    roles_quitar = [
        rol
        for rol in miembro.roles
        if (rol.id in ids_rangos and rol.id != rol_destino.id)
        or (rol.id in ids_tiers and rol.id != rol_tier.id)
    ]
    roles_dar = [rol for rol in (rol_destino, rol_tier) if rol not in miembro.roles]

    try:
        if roles_quitar:
            await miembro.remove_roles(*roles_quitar, reason=reason)
        if roles_dar:
            await miembro.add_roles(*roles_dar, reason=reason)
    except discord.Forbidden:
        return False, "No tengo jerarquia suficiente para administrar esos roles."
    except discord.HTTPException as exc:
        return False, f"Discord rechazo el cambio de roles: {exc}"

    return True, ""


async def _limpiar_registro_nuevo_ingresante(user_id: int) -> None:
    try:
        from cogs.panel_nuevo_ingresante import eliminar_ingresante

        eliminar_ingresante(user_id)
    except Exception:
        pass


class ModalNuevoMiembro(discord.ui.Modal, title="Nuevo Miembro PFA"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", min_length=17, max_length=21)
    motivo = discord.ui.TextInput(
        label="Motivo de ingreso (opcional)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        miembro = await _buscar_miembro(interaction, self.discord_id.value)
        if miembro is None:
            return

        if _esta_en_blacklist(miembro.id, interaction.guild.id):
            return await interaction.followup.send(
                "⛔ El usuario esta en la blacklist PFA. Retiralo primero de la blacklist.",
                ephemeral=True,
            )

        guild_id = interaction.guild.id
        rol_pfa = _validar_rol(interaction.guild, _get_rol_id(guild_id, "ROL_PFA_ID"))
        rol_cadete = _validar_rol(interaction.guild, _get_rol_id(guild_id, JERARQUIA_PFA[0]))
        rol_low = _validar_rol(interaction.guild, _get_rol_id(guild_id, "ROL_LOWPFA_ID"))
        faltantes = []
        if rol_pfa is None:
            faltantes.append("ROL_PFA_ID")
        if rol_cadete is None:
            faltantes.append("ROL_CADETE_ID")
        if rol_low is None:
            faltantes.append("ROL_LOWPFA_ID")
        if faltantes:
            return await interaction.followup.send(
                f"❌ Configuracion incompleta: {', '.join(faltantes)}.",
                ephemeral=True,
            )

        if rol_pfa in miembro.roles:
            return await interaction.followup.send(f"⚠️ {miembro.mention} ya pertenece a la PFA.", ephemeral=True)

        try:
            await miembro.add_roles(rol_pfa, rol_low, rol_cadete, reason=f"Nuevo ingreso PFA por {interaction.user}")
        except discord.Forbidden:
            return await interaction.followup.send(
                "❌ No tengo jerarquia suficiente para asignar los roles PFA.",
                ephemeral=True,
            )
        except discord.HTTPException as exc:
            return await interaction.followup.send(f"❌ Error de Discord: {exc}", ephemeral=True)

        motivo = self.motivo.value.strip() or "Sin especificar"
        await _enviar_log(
            interaction,
            "Nuevo ingreso PFA",
            miembro,
            f"🎖️ **Rango inicial:** `[00] Cadete`\n📝 **Motivo:** {motivo}",
            "✅",
        )
        dm_enviado = False
        try:
            from cogs.panel_interviewer import _build_dm_bienvenida

            await miembro.send(embed=_build_dm_bienvenida(miembro))
            dm_enviado = True
        except (discord.Forbidden, discord.HTTPException):
            pass

        estado_md = (
            "📨 MD de bienvenida enviado."
            if dm_enviado
            else "⚠️ No se pudo enviar el MD de bienvenida; el usuario tiene los mensajes cerrados."
        )
        await interaction.followup.send(
            f"✅ {miembro.mention} ingreso a PFA como **[0] Cadete**.\n{estado_md}",
            ephemeral=True,
        )


class ModalRemoverMiembro(discord.ui.Modal, title="Remover Miembro PFA"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", min_length=17, max_length=21)
    motivo = discord.ui.TextInput(
        label="Motivo de la remocion (opcional)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        miembro = await _buscar_miembro(interaction, self.discord_id.value)
        if miembro is None:
            return

        motivo = self.motivo.value.strip() or "Sin especificar"
        roles_quitar = _roles_pfa_del_miembro(miembro)
        if not roles_quitar:
            return await interaction.followup.send(f"⚠️ {miembro.mention} no tiene roles de PFA.", ephemeral=True)

        rango = _rango_actual(miembro)
        try:
            await miembro.remove_roles(
                *roles_quitar,
                reason=f"Remocion PFA por {interaction.user}: {motivo}",
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                "❌ No tengo jerarquia suficiente para quitar todos los roles PFA.",
                ephemeral=True,
            )
        except discord.HTTPException as exc:
            return await interaction.followup.send(f"❌ Error de Discord: {exc}", ephemeral=True)

        await _limpiar_registro_nuevo_ingresante(miembro.id)
        rango_texto = f"[{rango.nivel}] {rango.nombre}" if rango else "No detectado"

        embed_dm = discord.Embed(
            title="🚨 Notificación de expulsión — PFA",
            description=(
                "Te informamos que fuiste **removido oficialmente de la Policía Federal Argentina**.\n\n"
                "La medida ya fue aplicada y tus roles institucionales fueron retirados."
            ),
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow(),
        )
        embed_dm.add_field(name="🎖️ Último rango", value=rango_texto, inline=False)
        embed_dm.add_field(name="📝 Motivo", value=motivo, inline=False)
        embed_dm.add_field(
            name="📌 Estado",
            value="Expulsión de facción confirmada.",
            inline=False,
        )
        if interaction.guild.icon:
            embed_dm.set_thumbnail(url=interaction.guild.icon.url)
        embed_dm.set_footer(text="Policía Federal Argentina — Ibiza Roleplay")

        dm_enviado = False
        try:
            await miembro.send(embed=embed_dm)
            dm_enviado = True
        except (discord.Forbidden, discord.HTTPException):
            pass

        await _enviar_log(
            interaction,
            "Miembro removido de PFA",
            miembro,
            (
                f"🎖️ **Último rango:** `{rango_texto}`\n"
                f"📝 **Motivo:** {motivo}"
            ),
            "❌",
        )

        estado_md = (
            "📨 El oficial fue notificado correctamente por MD."
            if dm_enviado
            else "⚠️ Los roles fueron retirados, pero no se pudo entregar el MD porque el usuario lo tiene cerrado."
        )
        await interaction.followup.send(
            f"✅ {miembro.mention} fue removido completamente de PFA.\n{estado_md}",
            ephemeral=True,
        )


class ModalConfirmarPromotePFA(discord.ui.Modal, title="Confirmar ascenso PFA"):
    motivo = discord.ui.TextInput(
        label="Motivo del ascenso (opcional)",
        style=discord.TextStyle.paragraph,
        placeholder="Ej: desempeño, antigüedad o aprobación interna...",
        max_length=500,
        required=False,
    )

    def __init__(self, miembro_id: int, destino: RangoPFA) -> None:
        super().__init__()
        self.miembro_id = miembro_id
        self.destino = destino

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not _tiene_permiso(interaction.user):
            return await interaction.followup.send(
                "⛔ Ya no tenés permiso para completar esta operación.",
                ephemeral=True,
            )

        miembro = await _buscar_miembro(interaction, str(self.miembro_id))
        if miembro is None:
            return

        actual = _rango_actual(miembro)
        if actual is None:
            return await interaction.followup.send(
                "❌ El miembro ya no tiene un rango PFA reconocido.", ephemeral=True
            )
        if self.destino.nivel <= actual.nivel:
            return await interaction.followup.send(
                f"⚠️ El rango cambió mientras confirmabas. Ahora posee "
                f"**[{actual.nivel}] {actual.nombre}**; abrí nuevamente **Ascenso**.",
                ephemeral=True,
            )

        motivo = self.motivo.value.strip() or "Sin especificar"
        ok, error = await _cambiar_rango(
            miembro,
            self.destino,
            reason=f"Ascenso PFA por {interaction.user}: {motivo}",
        )
        if not ok:
            return await interaction.followup.send(f"❌ {error}", ephemeral=True)

        beneficio = f"\n🎁 **Habilita:** {self.destino.beneficio}" if self.destino.beneficio else ""
        cambio_tier = _detalle_cambio_tier(actual, self.destino)
        await _enviar_log(
            interaction,
            "Ascenso de rango PFA",
            miembro,
            (
                f"🎖️ **Rango:** `[{actual.nivel:02}] {actual.nombre}` → "
                f"`[{self.destino.nivel:02}] {self.destino.nombre}`\n"
                f"📈 **Niveles ascendidos:** {self.destino.nivel - actual.nivel}"
                f"{cambio_tier}\n"
                f"📝 **Motivo:** {motivo}{beneficio}"
            ),
            "⭐",
        )
        await interaction.followup.send(
            (
                f"✅ Ascenso aplicado a {miembro.mention}.\n"
                f"`[{actual.nivel:02}] {actual.nombre}` → "
                f"`[{self.destino.nivel:02}] {self.destino.nombre}`"
                f"{cambio_tier}"
            ),
            ephemeral=True,
        )


class ModalBuscarMiembroPromotePFA(discord.ui.Modal, title="Buscar miembro por ID"):
    discord_id = discord.ui.TextInput(
        label="Discord ID del usuario",
        placeholder="Ej: 123456789012345678",
        min_length=17,
        max_length=21,
    )

    def __init__(self, view: "ViewPromotePFA") -> None:
        super().__init__()
        self.promote_view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.promote_view.autor_id or not _tiene_permiso(interaction.user):
            return await interaction.response.send_message(
                "⛔ Ya no tenés permiso para completar esta operación.", ephemeral=True
            )

        miembro = await _buscar_miembro(interaction, self.discord_id.value)
        if miembro is None:
            return

        self.promote_view.seleccionar_miembro(miembro)
        await interaction.response.edit_message(
            embed=self.promote_view.crear_embed(),
            view=self.promote_view,
        )


class SelectMiembroPromotePFA(discord.ui.UserSelect):
    def __init__(self) -> None:
        super().__init__(
            placeholder="1 · Seleccioná un miembro o usá Buscar por ID",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: ViewPromotePFA = self.view
        seleccionado = self.values[0]
        if isinstance(seleccionado, discord.Member):
            miembro = seleccionado
        else:
            miembro = interaction.guild.get_member(seleccionado.id)
            if miembro is None:
                try:
                    miembro = await interaction.guild.fetch_member(seleccionado.id)
                except (discord.NotFound, discord.HTTPException):
                    return await interaction.response.send_message(
                        "❌ Ese usuario ya no se encuentra en el servidor.", ephemeral=True
                    )

        view.seleccionar_miembro(miembro)
        await interaction.response.edit_message(embed=view.crear_embed(), view=view)


class SelectTierPromotePFA(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="2 · Primero seleccioná un miembro",
            options=[discord.SelectOption(label="Esperando miembro", value="none")],
            min_values=1,
            max_values=1,
            disabled=True,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: ViewPromotePFA = self.view
        view.seleccionar_tier(self.values[0])
        await interaction.response.edit_message(embed=view.crear_embed(), view=view)


class SelectRangoPromotePFA(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="3 · Elegí primero un tier",
            options=[discord.SelectOption(label="Esperando tier", value="none")],
            min_values=1,
            max_values=1,
            disabled=True,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: ViewPromotePFA = self.view
        view.seleccionar_rango(int(self.values[0]))
        await interaction.response.edit_message(embed=view.crear_embed(), view=view)


class ViewPromotePFA(discord.ui.View):
    def __init__(self, autor_id: int, guild: discord.Guild) -> None:
        super().__init__(timeout=300)
        self.autor_id = autor_id
        self.guild = guild
        self.miembro: discord.Member | None = None
        self.destino: RangoPFA | None = None
        self.miembro_select = SelectMiembroPromotePFA()
        self.tier_select = SelectTierPromotePFA()
        self.rango_select = SelectRangoPromotePFA()
        self.add_item(self.miembro_select)
        self.add_item(self.tier_select)
        self.add_item(self.rango_select)
        self.confirmar.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message(
                "⛔ Este selector pertenece a otra operación.", ephemeral=True
            )
            return False
        if not _tiene_permiso(interaction.user):
            await interaction.response.send_message(
                "⛔ No tenés permiso para gestionar rangos PFA.", ephemeral=True
            )
            return False
        return True

    def crear_embed(self) -> discord.Embed:
        return _embed_selector_ascenso(self.guild, self.miembro, self.destino)

    def seleccionar_miembro(self, miembro: discord.Member) -> None:
        self.miembro = miembro
        self.destino = None
        actual = _rango_actual(miembro)
        tiers_disponibles = []
        if actual and actual.nivel < JERARQUIA_PFA[-1].nivel:
            for tier in ("low", "high", "head"):
                if any(r.tier == tier and r.nivel > actual.nivel for r in JERARQUIA_PFA):
                    nombre, emoji, _ = TIER_INFO[tier]
                    tiers_disponibles.append(
                        discord.SelectOption(
                            label=nombre,
                            value=tier,
                            emoji=emoji,
                            description=f"Rangos superiores disponibles en {nombre}",
                        )
                    )

        self.tier_select.options = tiers_disponibles or [
            discord.SelectOption(label="Sin destinos disponibles", value="none")
        ]
        self.tier_select.placeholder = "2 · Seleccioná el tier de destino"
        self.tier_select.disabled = not tiers_disponibles
        self.rango_select.options = [discord.SelectOption(label="Esperando tier", value="none")]
        self.rango_select.placeholder = "3 · Elegí primero un tier"
        self.rango_select.disabled = True
        self.confirmar.disabled = True

    def seleccionar_tier(self, tier: str) -> None:
        self.destino = None
        actual = _rango_actual(self.miembro) if self.miembro else None
        for option in self.tier_select.options:
            option.default = option.value == tier
        destinos = [
            rango
            for rango in JERARQUIA_PFA
            if actual and rango.tier == tier and rango.nivel > actual.nivel
        ]
        self.rango_select.options = [
            discord.SelectOption(
                label=f"[{rango.nivel:02}] {rango.nombre}",
                value=str(rango.nivel),
                description=(
                    f"+{rango.nivel - actual.nivel} niveles"
                    if rango.tier == actual.tier
                    else (
                        f"{_nombre_tier(actual.tier)} → {_nombre_tier(rango.tier)} · "
                        f"+{rango.nivel - actual.nivel} niveles"
                    )
                ),
            )
            for rango in destinos
        ]
        self.rango_select.placeholder = "3 · Seleccioná el rango de destino"
        self.rango_select.disabled = not destinos
        self.confirmar.disabled = True

    def seleccionar_rango(self, nivel: int) -> None:
        self.destino = _rango_por_nivel(nivel)
        for option in self.rango_select.options:
            option.default = option.value == str(nivel)
        self.confirmar.disabled = self.destino is None

    @discord.ui.button(
        label="Buscar por ID",
        emoji="🔎",
        style=discord.ButtonStyle.primary,
        row=3,
    )
    async def buscar_por_id(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ModalBuscarMiembroPromotePFA(self))

    @discord.ui.button(
        label="Confirmar ascenso",
        emoji="✅",
        style=discord.ButtonStyle.success,
        row=3,
    )
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.miembro is None or self.destino is None:
            return await interaction.response.send_message(
                "⚠️ Seleccioná el miembro y el rango de destino.", ephemeral=True
            )
        await interaction.response.send_modal(
            ModalConfirmarPromotePFA(self.miembro.id, self.destino)
        )

    @discord.ui.button(
        label="Cancelar",
        emoji="✖️",
        style=discord.ButtonStyle.secondary,
        row=3,
    )
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        for item in self.children:
            item.disabled = True
        self.stop()
        embed = discord.Embed(
            title="Operación cancelada",
            description="No se realizó ningún cambio de rango.",
            color=discord.Color.light_grey(),
        )
        await interaction.response.edit_message(embed=embed, view=self)


class ModalPromoteUnoPFA(discord.ui.Modal, title="Ascender un rango PFA"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", min_length=17, max_length=21)
    motivo = discord.ui.TextInput(
        label="Motivo del ascenso (opcional)",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        miembro = await _buscar_miembro(interaction, self.discord_id.value)
        if miembro is None:
            return

        actual = _rango_actual(miembro)
        if actual is None:
            return await interaction.followup.send("❌ El usuario no tiene un rango PFA reconocido.", ephemeral=True)
        if actual.nivel >= 33:
            return await interaction.followup.send("⚠️ El usuario ya tiene el rango maximo.", ephemeral=True)

        destino = JERARQUIA_PFA[actual.nivel + 1]
        motivo = self.motivo.value.strip() or "Sin especificar"
        ok, error = await _cambiar_rango(miembro, destino, reason=f"Ascenso PFA +1 por {interaction.user}: {motivo}")
        if not ok:
            return await interaction.followup.send(f"❌ {error}", ephemeral=True)

        cambio_tier = _detalle_cambio_tier(actual, destino)
        await _enviar_log(
            interaction,
            "Ascenso PFA +1",
            miembro,
            (
                f"🎖️ **Rango:** `[{actual.nivel:02}] {actual.nombre}` → "
                f"`[{destino.nivel:02}] {destino.nombre}`"
                f"{cambio_tier}\n"
                f"📝 **Motivo:** {motivo}"
            ),
            "⭐",
        )
        await interaction.followup.send(
            f"✅ {miembro.mention} ascendio a **[{destino.nivel}] {destino.nombre}**.",
            ephemeral=True,
        )


class ModalDemotePFA(discord.ui.Modal, title="Descender Miembro PFA"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", min_length=17, max_length=21)
    motivo = discord.ui.TextInput(
        label="Motivo del descenso",
        style=discord.TextStyle.paragraph,
        min_length=3,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        miembro = await _buscar_miembro(interaction, self.discord_id.value)
        if miembro is None:
            return

        actual = _rango_actual(miembro)
        if actual is None:
            return await interaction.followup.send("❌ El usuario no tiene un rango PFA reconocido.", ephemeral=True)
        if actual.nivel <= 0:
            return await interaction.followup.send("⚠️ Cadete es el rango minimo.", ephemeral=True)

        destino = JERARQUIA_PFA[actual.nivel - 1]
        motivo = self.motivo.value.strip()
        ok, error = await _cambiar_rango(miembro, destino, reason=f"Descenso PFA por {interaction.user}: {motivo}")
        if not ok:
            return await interaction.followup.send(f"❌ {error}", ephemeral=True)

        cambio_tier = _detalle_cambio_tier(actual, destino)
        await _enviar_log(
            interaction,
            "Descenso de rango PFA",
            miembro,
            (
                f"🎖️ **Rango:** `[{actual.nivel:02}] {actual.nombre}` → "
                f"`[{destino.nivel:02}] {destino.nombre}`"
                f"{cambio_tier}\n"
                f"📝 **Motivo:** {motivo}"
            ),
            "🔻",
        )
        try:
            await miembro.send(
                f"Fuiste descendido en PFA: **[{actual.nivel}] {actual.nombre}** → "
                f"**[{destino.nivel}] {destino.nombre}**.\nMotivo: **{motivo}**"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

        await interaction.followup.send(
            f"✅ {miembro.mention} descendio a **[{destino.nivel}] {destino.nombre}**.",
            ephemeral=True,
        )


class ModalBlacklistPFA(discord.ui.Modal, title="Blacklist PFA"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", min_length=17, max_length=21)
    motivo = discord.ui.TextInput(
        label="Motivo de blacklist",
        style=discord.TextStyle.paragraph,
        min_length=3,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        miembro = await _buscar_miembro(interaction, self.discord_id.value)
        if miembro is None:
            return

        rol_blacklist = _validar_rol(interaction.guild, _get_rol_id(interaction.guild.id, "ROL_BLACKLIST_PFA_ID"))
        if rol_blacklist is None:
            return await interaction.followup.send(
                "❌ Falta configurar ROL_BLACKLIST_PFA_ID o el rol no existe.",
                ephemeral=True,
            )

        motivo = self.motivo.value.strip()
        roles_quitar = _roles_pfa_del_miembro(miembro)
        rol_agregado = rol_blacklist not in miembro.roles

        try:
            if rol_agregado:
                await miembro.add_roles(
                    rol_blacklist,
                    reason=f"Blacklist PFA por {interaction.user}: {motivo}",
                )
            if roles_quitar:
                await miembro.remove_roles(
                    *roles_quitar,
                    reason=f"Blacklist PFA por {interaction.user}: {motivo}",
                )
        except (discord.Forbidden, discord.HTTPException) as exc:
            if rol_agregado and rol_blacklist in miembro.roles:
                try:
                    await miembro.remove_roles(rol_blacklist, reason="Rollback de blacklist PFA fallida")
                except discord.HTTPException:
                    pass
            return await interaction.followup.send(
                f"❌ No se pudo completar la blacklist en Discord: {exc}",
                ephemeral=True,
            )

        _agregar_blacklist(miembro.id, motivo, interaction.user.id)
        await _limpiar_registro_nuevo_ingresante(miembro.id)
        await _enviar_log(
            interaction,
            "Ingreso a blacklist PFA",
            miembro,
            f"🚫 **Rol asignado:** {rol_blacklist.mention}\n📝 **Motivo:** {motivo}",
            "⛔",
        )

        embed_dm = discord.Embed(
            title="⛔ Inclusión en Blacklist — PFA",
            description=(
                "Fuiste retirado de la Policía Federal Argentina e incluido en la "
                "**blacklist institucional**."
            ),
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow(),
        )
        embed_dm.add_field(name="📝 Motivo", value=motivo, inline=False)
        embed_dm.add_field(
            name="📌 Consecuencia",
            value="No podrás reingresar a PFA mientras la blacklist permanezca activa.",
            inline=False,
        )
        embed_dm.set_footer(text="Policía Federal Argentina — Ibiza Roleplay")
        try:
            await miembro.send(embed=embed_dm)
        except (discord.Forbidden, discord.HTTPException):
            pass

        await interaction.followup.send(
            f"✅ {miembro.mention} recibió {rol_blacklist.mention}, fue retirado de PFA "
            "y quedó registrado en la blacklist.",
            ephemeral=True,
        )


class ModalUnblacklistPFA(discord.ui.Modal, title="Quitar Blacklist PFA"):
    discord_id = discord.ui.TextInput(label="Discord ID del usuario", min_length=17, max_length=21)
    motivo = discord.ui.TextInput(
        label="Motivo del retiro de blacklist",
        style=discord.TextStyle.paragraph,
        placeholder="Ej: apelación aprobada, sanción cumplida...",
        min_length=3,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        miembro = await _buscar_miembro(interaction, self.discord_id.value)
        if miembro is None:
            return
        motivo = self.motivo.value.strip()

        rol_blacklist = _validar_rol(interaction.guild, _get_rol_id(interaction.guild.id, "ROL_BLACKLIST_PFA_ID"))
        if rol_blacklist is None:
            return await interaction.followup.send(
                "❌ Falta configurar ROL_BLACKLIST_PFA_ID o el rol no existe.",
                ephemeral=True,
            )

        estaba_registrado = _esta_en_blacklist(miembro.id, interaction.guild.id)
        tenia_rol = rol_blacklist in miembro.roles
        if not estaba_registrado and not tenia_rol:
            return await interaction.followup.send(
                "⚠️ El usuario no estaba en la blacklist PFA.",
                ephemeral=True,
            )

        if tenia_rol:
            try:
                await miembro.remove_roles(
                    rol_blacklist,
                    reason=f"Blacklist PFA levantada por {interaction.user}: {motivo}",
                )
            except (discord.Forbidden, discord.HTTPException) as exc:
                return await interaction.followup.send(
                    f"❌ No se pudo retirar el rol blacklist: {exc}",
                    ephemeral=True,
                )

        _quitar_blacklist(miembro.id)
        await _enviar_log(
            interaction,
            "Retiro de blacklist PFA",
            miembro,
            (
                f"🔓 **Rol retirado:** {rol_blacklist.mention}\n"
                f"📝 **Motivo:** {motivo}\n"
                "ℹ️ **Estado:** Los roles PFA no se restauraron automáticamente."
            ),
            "🔓",
        )
        await interaction.followup.send(
            f"✅ {miembro.mention} fue retirado de la blacklist. Usa **New** si debe reingresar.",
            ephemeral=True,
        )

class ViewPanelGestionPFA(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _verificar(self, interaction: discord.Interaction) -> bool:
        if _tiene_permiso(interaction.user):
            return True
        await interaction.response.send_message("⛔ No tenes permiso para usar este panel.", ephemeral=True)
        return False

    @discord.ui.button(label="Nuevo ingreso", emoji="➕", style=discord.ButtonStyle.success, custom_id="panel_pfa_new_v2", row=0)
    async def btn_new(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await self._verificar(interaction):
            await interaction.response.send_modal(ModalNuevoMiembro())

    @discord.ui.button(label="Remover", emoji="👤", style=discord.ButtonStyle.danger, custom_id="panel_pfa_remove_v2", row=0)
    async def btn_remove(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await self._verificar(interaction):
            await interaction.response.send_modal(ModalRemoverMiembro())

    @discord.ui.button(label="Ascenso", emoji="⬆️", style=discord.ButtonStyle.success, custom_id="panel_pfa_promote_v2", row=0)
    async def btn_promote(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await self._verificar(interaction):
            view = ViewPromotePFA(interaction.user.id, interaction.guild)
            await interaction.response.send_message(
                embed=view.crear_embed(),
                view=view,
                ephemeral=True,
            )

    @discord.ui.button(label="Ascenso +1", emoji="⏫", style=discord.ButtonStyle.secondary, custom_id="panel_pfa_promote_one_v2", row=0)
    async def btn_promote_uno(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await self._verificar(interaction):
            await interaction.response.send_modal(ModalPromoteUnoPFA())

    @discord.ui.button(label="Descenso", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="panel_pfa_demote_v2", row=0)
    async def btn_demote(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await self._verificar(interaction):
            await interaction.response.send_modal(ModalDemotePFA())

    @discord.ui.button(label="Blacklist", emoji="🚫", style=discord.ButtonStyle.danger, custom_id="panel_pfa_blacklist_v2", row=1)
    async def btn_blacklist(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await self._verificar(interaction):
            await interaction.response.send_modal(ModalBlacklistPFA())

    @discord.ui.button(label="Quitar blacklist", emoji="🔓", style=discord.ButtonStyle.primary, custom_id="panel_pfa_unblacklist_v2", row=1)
    async def btn_unblacklist(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await self._verificar(interaction):
            await interaction.response.send_modal(ModalUnblacklistPFA())


class GestionPFA(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        self.bot.add_view(ViewPanelGestionPFA())
        print("[Cog] Panel de Gestion PFA cargado.")

    @app_commands.command(name="panelpfa", description="Despliega el Panel de Gestion de miembros PFA.")
    async def panelpfa(self, interaction: discord.Interaction) -> None:
        if not _tiene_permiso(interaction.user):
            return await interaction.response.send_message(
                "⛔ No tenes permiso para desplegar este panel.",
                ephemeral=True,
            )

        guild_id = interaction.guild.id
        faltantes = [
            rango.env_var
            for rango in JERARQUIA_PFA
            if _validar_rol(interaction.guild, _get_rol_id(guild_id, rango)) is None
        ]
        for env_var in (
            "ROL_PFA_ID",
            "ROL_LOWPFA_ID",
            "ROL_HIGHPFA_ID",
            "ROL_HEAD_PFA_ID",
            "ROL_BLACKLIST_PFA_ID",
        ):
            if _validar_rol(interaction.guild, _get_rol_id(guild_id, env_var)) is None:
                faltantes.append(env_var)

        embed = discord.Embed(
            title="Centro de Gestión PFA",
            description=(
                "Administración centralizada del personal de la **Policía Federal Argentina**.\n"
                "Seleccioná una acción; las operaciones sensibles se revisan antes de aplicarse."
            ),
            color=discord.Color.from_rgb(20, 74, 125),
            timestamp=_ahora(),
        )
        if interaction.guild.icon:
            embed.set_author(
                name=f"{interaction.guild.name} · Policía Federal Argentina",
                icon_url=interaction.guild.icon.url,
            )
            embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.add_field(
            name="👥 Personal",
            value=(
                "`Nuevo ingreso` incorpora como **[00] Cadete**.\n"
                "`Remover` retira todos los roles institucionales."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎖️ Carrera y rangos",
            value=(
                "`Ascenso` abre el selector guiado de miembro, tier y rango.\n"
                "`Ascenso +1` y `Descenso` resuelven movimientos de un solo nivel."
            ),
            inline=False,
        )
        embed.add_field(
            name="🛡️ Control de acceso",
            value=(
                "`Blacklist` bloquea el reingreso y retira los roles PFA.\n"
                "`Quitar blacklist` levanta el bloqueo sin restaurar cargos automáticamente."
            ),
            inline=False,
        )
        embed.add_field(
            name="🔹 LOW PFA",
            value="`[00–12]` Cadete → Sub Teniente",
            inline=True,
        )
        embed.add_field(
            name="🔸 HIGH PFA",
            value="`[13–25]` Teniente → Sub Comisario",
            inline=True,
        )
        embed.add_field(
            name="⭐ HEAD PFA",
            value="`[26–33]` Comisario → Dueño",
            inline=True,
        )
        embed.add_field(
            name="⚙️ Automatización segura",
            value=(
                "Los tiers se sincronizan con cada cambio de rango. Todas las acciones validan "
                "permisos, configuración y jerarquía del bot, y quedan registradas en el canal de cambios."
            ),
            inline=False,
        )
        embed.set_footer(text="PFA · Panel administrativo • Las respuestas operativas son privadas")

        await interaction.channel.send(embed=embed, view=ViewPanelGestionPFA())

        aviso = "✅ Panel PFA desplegado."
        if faltantes:
            aviso += (
                f" ⚠️ Hay {len(set(faltantes))} roles PFA sin configurar "
                "o que ya no existen en el servidor."
            )
        await interaction.response.send_message(aviso, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GestionPFA(bot))
