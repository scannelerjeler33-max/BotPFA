import discord
from discord.ext import commands
from discord import app_commands
import os
import re
import datetime
from dotenv import load_dotenv
from utils.config import obtener_config_int, safe_env_int

load_dotenv()

# --- CONFIGURACIÓN VIA .ENV ---
CANAL_BITACORAS_ID      = safe_env_int("CANAL_BITACORAS_ID", 0)
ROL_PFA_ID              = safe_env_int("ROL_PFA_ID", 0)
ROL_NUEVO_INGRESANTE_ID = safe_env_int("ROL_NUEVO_INGRESANTE_ID", 0)
ROL_PANEL_ADMIN_ID      = safe_env_int("ROL_PANEL_ADMIN_ID", 0)
ROL_PERMS               = safe_env_int("ROL_PERMS", 0)

# Tener este rol es condición necesaria y suficiente para excluir al miembro de la limpieza
ROL_AUSENTE_ID = 1464030189066653963

# --- PARÁMETROS DE LA LIMPIEZA ---
PERIODO_DIAS       = 14   # Ventana de análisis de bitácoras en días
HORAS_MINIMAS      = 5.0  # Horas mínimas requeridas en el período
DIAS_GRACIA_NUEVOS = 7    # Referencia para el footer

# Patrones de búsqueda en los embeds de bitácoras
PATRON_MENCION = re.compile(r'<@!?(\d+)>')
PATRON_HORAS = re.compile(
    r'(\d+)\s*horas?,\s*(\d+)\s*minutos?,\s*(\d+)\s*segundos?',
    re.IGNORECASE
)


def obtener_embeds_mensaje(mensaje: discord.Message) -> list[discord.Embed]:
    """
    Retorna todos los embeds de un mensaje, incluyendo los de mensajes reenviados.

    Discord guarda el embed original de un mensaje reenviado en message_snapshots,
    no en message.embeds (que queda vacío). Esta función unifica ambas fuentes.
    """
    embeds: list[discord.Embed] = list(mensaje.embeds)

    snapshots = getattr(mensaje, "message_snapshots", None)
    if snapshots:
        for snapshot in snapshots:
            embeds.extend(getattr(snapshot, "embeds", []))

    return embeds


def extraer_datos_embed(embed: discord.Embed) -> dict[int, float]:
    """
    Parsea un embed de bitácora y extrae el user ID y las horas de cada oficial.

    Estrategia 1 (campo a campo): busca mención + horas en el mismo field.
    Estrategia 2 (embed completo): si la estrategia 1 no encuentra nada, concatena
    todo el texto del embed y empareja cada mención con el valor de horas más cercano
    por posición. Cubre el caso donde mención y horas están en fields distintos.

    Returns:
        dict {user_id: horas_decimales} para todos los usuarios encontrados.
    """
    datos: dict[int, float] = {}

    # Bloques individuales: descripción + cada field (name + value)
    bloques: list[str] = []
    if embed.description:
        bloques.append(embed.description)
    for campo in embed.fields:
        bloques.append((campo.name or "") + "\n" + (campo.value or ""))

    # --- Estrategia 1: mención y horas en el mismo bloque ---
    for bloque in bloques:
        menciones = PATRON_MENCION.findall(bloque)
        match_horas = PATRON_HORAS.search(bloque)

        if not menciones or not match_horas:
            continue

        h = int(match_horas.group(1))
        m = int(match_horas.group(2))
        s = int(match_horas.group(3))
        horas_decimal = h + m / 60.0 + s / 3600.0

        for uid_str in menciones:
            uid = int(uid_str)
            if uid not in datos or horas_decimal > datos[uid]:
                datos[uid] = horas_decimal

    if datos:
        return datos

    # --- Estrategia 2: emparejar por proximidad en el texto completo ---
    # Se usa cuando mención y horas están en fields separados del mismo embed.
    texto_completo = "\n".join(bloques)

    menciones_pos = [
        (m.start(), int(m.group(1)))
        for m in PATRON_MENCION.finditer(texto_completo)
    ]
    horas_pos = [
        (m.start(), int(m.group(1)), int(m.group(2)), int(m.group(3)))
        for m in PATRON_HORAS.finditer(texto_completo)
    ]

    if not menciones_pos or not horas_pos:
        return datos

    for pos_m, uid in menciones_pos:
        mejor = min(horas_pos, key=lambda x: abs(x[0] - pos_m))
        h, m_val, s = mejor[1], mejor[2], mejor[3]
        horas_decimal = h + m_val / 60.0 + s / 3600.0
        if uid not in datos or horas_decimal > datos[uid]:
            datos[uid] = horas_decimal

    return datos


async def analizar_bitacoras(canal: discord.TextChannel, dias: int = PERIODO_DIAS) -> dict[int, float]:
    """
    Escanea el canal de bitácoras de los últimos `dias` días y calcula las horas
    totales por oficial para el período completo.

    Las bitácoras se reinician semanalmente. El mismo oficial puede aparecer en
    múltiples mensajes de la misma semana (las 5 páginas del reporte semanal).
    Para evitar doble conteo: se toma el máximo dentro de cada semana ISO y luego
    se suman los máximos de cada semana para obtener el total del período.

    Returns:
        dict {user_id: horas_totales_del_periodo}
    """
    desde = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=dias)

    # Clave: (user_id, numero_semana_iso) → valor: máximo de horas visto en esa semana
    horas_semanales: dict[tuple[int, int], float] = {}

    async for mensaje in canal.history(limit=None, after=desde, oldest_first=True):
        numero_semana = mensaje.created_at.isocalendar()[1]

        for embed in obtener_embeds_mensaje(mensaje):
            datos = extraer_datos_embed(embed)
            for user_id, horas in datos.items():
                clave = (user_id, numero_semana)
                if clave not in horas_semanales or horas > horas_semanales[clave]:
                    horas_semanales[clave] = horas

    # Sumar el máximo de cada semana para obtener el total del período por usuario
    horas_totales: dict[int, float] = {}
    for (user_id, _), horas in horas_semanales.items():
        horas_totales[user_id] = horas_totales.get(user_id, 0.0) + horas

    return horas_totales


async def enviar_resultados_limpieza(
    interaction: discord.Interaction,
    candidatos: list[tuple[discord.Member, str]],
    ahora: datetime.datetime,
) -> None:
    """
    Construye y envía el embed con los resultados del análisis de limpieza.

    Si hay más de 25 candidatos, divide en múltiples embeds para respetar
    el límite de fields de Discord.
    """
    fecha_str = ahora.strftime("%d/%m/%Y %H:%M UTC")
    pie = (
        f"Generado el {fecha_str}  •  "
        f"Exclusiones: ausente · nuevo ingresante (<{DIAS_GRACIA_NUEVOS}d) · bots"
    )

    if not candidatos:
        embed = discord.Embed(
            title="🧹 Limpieza de Oficiales — PFA",
            description=(
                f"✅ **No se encontraron candidatos a limpieza.**\n\n"
                f"Todos los oficiales @PFA superan el mínimo de **{HORAS_MINIMAS:.0f}h** "
                f"en los últimos **{PERIODO_DIAS} días**."
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text=pie)
        await interaction.followup.send(embed=embed)
        return

    # Paginar en bloques de 25 (límite de fields por embed en Discord)
    pagina_size = 25
    paginas = [candidatos[i:i + pagina_size] for i in range(0, len(candidatos), pagina_size)]

    for num_pagina, pagina in enumerate(paginas, start=1):
        descripcion = (
            f"📅 Período analizado: últimas **{PERIODO_DIAS} días**\n"
            f"⏱️ Mínimo requerido: **{HORAS_MINIMAS:.0f} horas**\n"
            f"🚫 Candidatos encontrados: **{len(candidatos)}**"
        )
        if len(paginas) > 1:
            descripcion += f"\n📄 Página **{num_pagina}/{len(paginas)}**"

        embed = discord.Embed(
            title="🧹 Limpieza de Oficiales — PFA",
            description=descripcion,
            color=discord.Color.red(),
        )

        for miembro, razon in pagina:
            embed.add_field(
                name=miembro.display_name,
                value=f"<@{miembro.id}>\n{razon}",
                inline=True,
            )

        embed.set_footer(text=pie)
        await interaction.followup.send(embed=embed)


class PanelLimpieza(commands.Cog):
    """Cog para detección de oficiales PFA inactivos mediante análisis de bitácoras."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="limpieza",
        description="Detecta oficiales @PFA inactivos en las últimas 2 semanas según las bitácoras."
    )
    async def limpieza(self, interaction: discord.Interaction) -> None:
        es_staff = interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator
        rol_admin = obtener_config_int(interaction.guild.id, "ROL_PANEL_ADMIN_ID", ROL_PANEL_ADMIN_ID)
        rol_perms = obtener_config_int(interaction.guild.id, "ROL_PERMS", ROL_PERMS)
        if not (es_staff or any(r.id in (rol_admin, rol_perms) for r in interaction.user.roles)):
            return await interaction.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)
        """
        Escanea el canal de bitácoras y retorna todos los oficiales con @PFA
        que no alcancen el mínimo de horas requeridas en el período.

        Exclusiones aplicadas automáticamente:
        - Bots de Discord
        - Miembros con el rol @Nuevo Ingresante activo (gestionado por panel_nuevo_ingresante)
        - Miembros con el rol @Ausente activo
        """
        await interaction.response.defer()

        guild = interaction.guild
        canal_bitacoras_id = obtener_config_int(guild.id, "CANAL_BITACORAS_ID", CANAL_BITACORAS_ID)
        canal_bitacoras = guild.get_channel(canal_bitacoras_id)

        if canal_bitacoras is None:
            await interaction.followup.send(
                "❌ No se encontró el canal de bitácoras. "
                "Verificá la configuración de `CANAL_BITACORAS_ID` con `/configuracion`."
            )
            return

        rol_pfa_id = obtener_config_int(guild.id, "ROL_PFA_ID", ROL_PFA_ID)
        rol_pfa = guild.get_role(rol_pfa_id)
        if rol_pfa is None:
            await interaction.followup.send("❌ No se encontró el rol @PFA.")
            return

        horas_por_usuario = await analizar_bitacoras(canal_bitacoras)

        rol_nuevo_ingresante_id = obtener_config_int(guild.id, "ROL_NUEVO_INGRESANTE_ID", ROL_NUEVO_INGRESANTE_ID)
        rol_ausente_id = obtener_config_int(guild.id, "ROL_AUSENTE_ID", ROL_AUSENTE_ID)

        ahora = datetime.datetime.now(datetime.timezone.utc)
        candidatos: list[tuple[discord.Member, str]] = []

        for miembro in rol_pfa.members:
            if miembro.bot:
                continue

            # Excluir nuevos ingresantes — la gestión del rol la hace panel_nuevo_ingresante
            if any(r.id == rol_nuevo_ingresante_id for r in miembro.roles):
                continue

            # Excluir miembros con ausencia activa
            if any(r.id == rol_ausente_id for r in miembro.roles):
                continue

            horas = horas_por_usuario.get(miembro.id, 0.0)
            if horas >= HORAS_MINIMAS:
                continue

            if miembro.id not in horas_por_usuario:
                razon = "Sin registros en bitácoras"
            else:
                razon = f"{horas:.1f}h registradas (mín. {HORAS_MINIMAS:.0f}h)"

            candidatos.append((miembro, razon))

        await enviar_resultados_limpieza(interaction, candidatos, ahora)

    @limpieza.error
    async def limpieza_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message(
                "⛔ No tenés los permisos necesarios para ejecutar este comando.",
                ephemeral=True,
            )

    @app_commands.command(
        name="bitacorasdebug",
        description="Muestra la estructura interna del último mensaje del canal de bitácoras."
    )
    async def bitacorasdebug(self, interaction: discord.Interaction) -> None:
        es_staff = interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator
        rol_admin = obtener_config_int(interaction.guild.id, "ROL_PANEL_ADMIN_ID", ROL_PANEL_ADMIN_ID)
        rol_perms = obtener_config_int(interaction.guild.id, "ROL_PERMS", ROL_PERMS)
        if not (es_staff or any(r.id in (rol_admin, rol_perms) for r in interaction.user.roles)):
            return await interaction.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)
        """
        Inspecciona el último mensaje del canal de bitácoras y muestra:
        - Si el embed viene de message.embeds o de message_snapshots (forwarded)
        - Los primeros 3 fields del embed con sus nombres y valores exactos

        Usar cuando /limpieza no detecta correctamente los datos del embed.
        """
        await interaction.response.defer(ephemeral=True)

        canal_bitacoras_id = obtener_config_int(interaction.guild.id, "CANAL_BITACORAS_ID", CANAL_BITACORAS_ID)
        canal = interaction.guild.get_channel(canal_bitacoras_id)
        if canal is None:
            await interaction.followup.send("❌ Canal de bitácoras no encontrado.", ephemeral=True)
            return

        mensaje = None
        async for msg in canal.history(limit=1):
            mensaje = msg

        if mensaje is None:
            await interaction.followup.send("❌ No hay mensajes en el canal de bitácoras.", ephemeral=True)
            return

        embeds_directos = len(mensaje.embeds)
        snapshots = getattr(mensaje, "message_snapshots", None)
        embeds_snapshots = sum(len(getattr(s, "embeds", [])) for s in snapshots) if snapshots else 0

        lineas = [
            f"**Embeds en message.embeds:** {embeds_directos}",
            f"**Embeds en message_snapshots:** {embeds_snapshots}",
            f"**Es mensaje reenviado (forwarded):** {embeds_directos == 0 and embeds_snapshots > 0}",
            "",
        ]

        todos = obtener_embeds_mensaje(mensaje)
        if not todos:
            lineas.append("⚠️ No se encontraron embeds en ninguna fuente.")
        else:
            embed = todos[0]
            lineas.append(f"**Título del embed:** `{embed.title}`")
            lineas.append(f"**Descripción:** `{str(embed.description)[:150] if embed.description else 'Ninguna'}`")
            lineas.append(f"**Total de fields:** {len(embed.fields)}")
            lineas.append("")
            for i, campo in enumerate(embed.fields[:3]):
                lineas.append(f"**Field {i}** (inline={campo.inline})")
                lineas.append(f"  name: `{str(campo.name)[:80]}`")
                lineas.append(f"  value: `{str(campo.value)[:150]}`")
                lineas.append("")

        await interaction.followup.send("\n".join(lineas)[:2000], ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PanelLimpieza(bot))
