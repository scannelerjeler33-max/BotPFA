import discord
from discord.ext import commands
from discord import app_commands
import os
import datetime
from dotenv import load_dotenv
from databases.connection import get_connection
from cogs.panel_nuevo_ingresante import registrar_nuevo_ingresante
from utils.config import obtener_config_int, safe_env_int

load_dotenv()

def _get_iv_config(guild_id: int, key: str) -> int:
    fallback = globals().get(key, 0)
    return obtener_config_int(guild_id, key, fallback)

# Offset horario local respecto a UTC (ej: -3 para Argentina, +2 para España en verano)
_TZ_OFFSET = safe_env_int("BOT_TIMEZONE_OFFSET", 0)
_TZ_LOCAL   = datetime.timezone(datetime.timedelta(hours=_TZ_OFFSET))


def _ahora_local() -> datetime.datetime:
    """Hora local del servidor, usada exclusivamente para calcular semana_iso."""
    return datetime.datetime.now(_TZ_LOCAL)


def obtener_rango_fechas_semana(semana_iso: int, anio: int) -> str:
    lunes = datetime.datetime.fromisocalendar(anio, semana_iso, 1)
    domingo = lunes + datetime.timedelta(days=6)
    return f"{lunes.strftime('%d/%m')} - {domingo.strftime('%d/%m')}"


ORIGINAL_GUILD_ID = int(os.getenv("GUILD_ID", "1132046806595944488") or 1132046806595944488)

# --- CONEXIÓN A BASE DE DATOS ---
conn_iv = get_connection()
conn_iv.autocommit = True
cursor_iv = conn_iv.cursor()

# --- CONFIGURACIÓN VIA .ENV ---
ROL_INTERVIEWER_ID           = safe_env_int("ROL_INTERVIEWER_ID", 0)
ROL_ENCARGADO_INTERVIEWER_ID = safe_env_int("ROL_ENCARGADO_INTERVIEWER_ID", 0)
ROL_PANEL_ADMIN_ID           = safe_env_int("ROL_PANEL_ADMIN_ID", 0)
ROL_PFA_ID                   = safe_env_int("ROL_PFA_ID", 0)
ROL_LOWPFA_ID                = safe_env_int("ROL_LOWPFA_ID", 0)
ROL_CADETE_ID                = safe_env_int("ROL_CADETE_ID", 0)
ROL_NUEVO_INGRESANTE_ID      = safe_env_int("ROL_NUEVO_INGRESANTE_ID", 0)

ROL_CIVIL_ID            = safe_env_int("ROL_CIVIL_ID", 0)

CANAL_POSTULACIONES_ID  = safe_env_int("CANAL_POSTULACIONES_ID", 0)
CANAL_RESULTADOS_ID     = safe_env_int("CANAL_RESULTADOS_ID", 0)
CANAL_BITACORA_OPOS_ID  = safe_env_int("CANAL_BITACORA_OPOS_ID", 0)
CANAL_CAMBIOS_PFA_ID    = safe_env_int("CANAL_CAMBIOS_PFA_ID", 0)
# Canal de "sala de espera" enlazado en el anuncio de apertura de oposiciones
CANAL_SALA_POSTULANTES_ID = safe_env_int("CANAL_SALA_POSTULANTES_ID", 1351236672351637565)

# Canales referenciados en el DM de bienvenida
CANAL_NOMBRE_PFA_ID     = safe_env_int("CANAL_NOMBRE_PFA_ID", 0)
CANAL_INDUMENTARIA_ID   = safe_env_int("CANAL_INDUMENTARIA_ID", 0)
CANAL_TS3_ID            = safe_env_int("CANAL_TS3_ID", 0)
CANAL_VIDEO_INTRO_ID    = safe_env_int("CANAL_VIDEO_INTRO_ID", 0)
CANAL_DF_INFO_ID        = safe_env_int("CANAL_DF_INFO_ID", 0)
CANAL_DF_POSTULACION_ID = safe_env_int("CANAL_DF_POSTULACION_ID", 0)
CANAL_JERARQUIA_ID      = safe_env_int("CANAL_JERARQUIA_ID", 0)
CANAL_ENCARGADOS_ID     = safe_env_int("CANAL_ENCARGADOS_ID", 0)

NOTA_MAXIMA   = 15
NOTA_MINIMA   = 10   # mínimo para aprobar
COOLDOWN_DIAS = 3    # días de espera tras desaprobar


# ---------------------------------------------------------------------------
# Permisos
# ---------------------------------------------------------------------------

def _es_interviewer(miembro: discord.Member) -> bool:
    guild_id = miembro.guild.id
    rol_interviewer = _get_iv_config(guild_id, "ROL_INTERVIEWER_ID")
    rol_encargado = _get_iv_config(guild_id, "ROL_ENCARGADO_INTERVIEWER_ID")
    rol_panel_admin = _get_iv_config(guild_id, "ROL_PANEL_ADMIN_ID")
    ids = {r.id for r in miembro.roles}
    return bool(ids & {rol_interviewer, rol_encargado, rol_panel_admin})


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def obtener_sesion_activa(interviewer_id: int, guild_id: int = None) -> dict | None:
    if guild_id is None: guild_id = ORIGINAL_GUILD_ID
    cursor_iv.execute(
        "SELECT id, numero_semanal, fecha_apertura FROM oposiciones_sesiones "
        "WHERE interviewer_id = %s AND guild_id = %s AND activa = TRUE",
        (interviewer_id, guild_id),
    )
    row = cursor_iv.fetchone()
    if not row:
        return None
    return {"id": row[0], "numero_semanal": row[1], "fecha_apertura": row[2]}


def abrir_sesion(interviewer_id: int, guild_id: int = None) -> tuple[int, int]:
    """Crea una nueva sesión de oposiciones. Retorna (sesion_id, numero_semanal)."""
    if guild_id is None: guild_id = ORIGINAL_GUILD_ID
    ahora = _ahora_local()
    semana_iso = ahora.isocalendar()[1]
    anio = ahora.year

    cursor_iv.execute(
        "SELECT COUNT(*) FROM oposiciones_sesiones WHERE semana_iso = %s AND anio = %s AND guild_id = %s",
        (semana_iso, anio, guild_id),
    )
    numero_semanal = cursor_iv.fetchone()[0] + 1

    cursor_iv.execute(
        """
        INSERT INTO oposiciones_sesiones
            (guild_id, interviewer_id, fecha_apertura, numero_semanal, semana_iso, anio, activa)
        VALUES (%s, %s, NOW(), %s, %s, %s, TRUE)
        RETURNING id
        """,
        (guild_id, interviewer_id, numero_semanal, semana_iso, anio),
    )
    return cursor_iv.fetchone()[0], numero_semanal


def cerrar_sesion(sesion_id: int) -> None:
    cursor_iv.execute(
        "UPDATE oposiciones_sesiones SET fecha_cierre = NOW(), activa = FALSE WHERE id = %s",
        (sesion_id,),
    )


def obtener_resultados_sesion(sesion_id: int) -> list[dict]:
    cursor_iv.execute(
        "SELECT postulante_id, nota, aprobado FROM oposiciones_resultados WHERE sesion_id = %s",
        (sesion_id,),
    )
    return [{"postulante_id": r[0], "nota": r[1], "aprobado": r[2]} for r in cursor_iv.fetchall()]


def registrar_resultado(
    sesion_id: int,
    interviewer_id: int,
    postulante_id: int,
    nota: int,
    aprobado: bool,
    invitado_por: int | None,
    guild_id: int = None,
) -> None:
    if guild_id is None: guild_id = ORIGINAL_GUILD_ID
    ahora = _ahora_local()
    cursor_iv.execute(
        """
        INSERT INTO oposiciones_resultados
            (guild_id, sesion_id, interviewer_id, postulante_id, nota, aprobado, invitado_por,
             semana_iso, anio, fecha)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """,
        (
            guild_id, sesion_id, interviewer_id, postulante_id, nota, aprobado, invitado_por,
            ahora.isocalendar()[1], ahora.year,
        ),
    )


def contar_invitaciones_aprobadas(invitador_id: int) -> int:
    cursor_iv.execute(
        "SELECT COUNT(*) FROM oposiciones_resultados WHERE invitado_por = %s AND aprobado = TRUE",
        (invitador_id,),
    )
    return cursor_iv.fetchone()[0]


def set_cooldown(user_id: int) -> None:
    cursor_iv.execute(
        """
        INSERT INTO oposiciones_cooldown (user_id, puede_postular_desde)
        VALUES (%s, NOW() + INTERVAL '3 days')
        ON CONFLICT (user_id) DO UPDATE SET puede_postular_desde = NOW() + INTERVAL '3 days'
        """,
        (user_id,),
    )


def limpiar_cooldown(user_id: int) -> None:
    cursor_iv.execute(
        "DELETE FROM oposiciones_cooldown WHERE user_id = %s", (user_id,)
    )


def obtener_stats_semana(interviewer_id: int) -> dict:
    ahora = _ahora_local()
    semana_iso = ahora.isocalendar()[1]
    anio = ahora.year

    cursor_iv.execute(
        """
        SELECT COUNT(*),
               COALESCE(SUM(
                   EXTRACT(EPOCH FROM (COALESCE(fecha_cierre, NOW()) - fecha_apertura)) / 3600
               ), 0)
        FROM oposiciones_sesiones
        WHERE interviewer_id = %s AND semana_iso = %s AND anio = %s
        """,
        (interviewer_id, semana_iso, anio),
    )
    row_s = cursor_iv.fetchone()

    cursor_iv.execute(
        """
        SELECT
            COUNT(*),
            COUNT(*) FILTER (WHERE aprobado = TRUE),
            COUNT(*) FILTER (WHERE aprobado = FALSE)
        FROM oposiciones_resultados
        WHERE interviewer_id = %s AND semana_iso = %s AND anio = %s
        """,
        (interviewer_id, semana_iso, anio),
    )
    row_r = cursor_iv.fetchone()

    cursor_iv.execute(
        """
        SELECT postulante_id, nota FROM oposiciones_resultados
        WHERE interviewer_id = %s AND semana_iso = %s AND anio = %s AND aprobado = TRUE
        ORDER BY fecha
        """,
        (interviewer_id, semana_iso, anio),
    )
    aprobados = [{"postulante_id": r[0], "nota": r[1]} for r in cursor_iv.fetchall()]

    cursor_iv.execute(
        "SELECT COALESCE(SUM(horas_ajuste), 0.0), COALESCE(SUM(aprobados_ajuste), 0) FROM oposiciones_ajustes WHERE interviewer_id = %s AND semana_iso = %s AND anio = %s",
        (interviewer_id, semana_iso, anio)
    )
    horas_aj, aprobados_aj = cursor_iv.fetchone()
    horas_aj = float(horas_aj or 0.0)
    aprobados_aj = int(aprobados_aj or 0)

    return {
        "n_sesiones": row_s[0],
        "horas": max(0.0, float(row_s[1]) + horas_aj),
        "n_total": row_r[0],
        "n_aprobados": max(0, row_r[1] + aprobados_aj),
        "n_desaprobados": row_r[2],
        "aprobados": aprobados,
    }


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _fmt_horas(horas_decimal: float) -> str:
    h = int(horas_decimal)
    m = int((horas_decimal - h) * 60)
    return f"{h}h {m}m" if h else f"{m}m"


def _build_dm_bienvenida(
    postulante: discord.Member,
    nota: int | None = None,
) -> discord.Embed:
    guild_id = postulante.guild.id
    canal_nombre = _get_iv_config(guild_id, "CANAL_NOMBRE_PFA_ID")
    canal_indumentaria = _get_iv_config(guild_id, "CANAL_INDUMENTARIA_ID")
    canal_ts3 = _get_iv_config(guild_id, "CANAL_TS3_ID")
    canal_video_intro = _get_iv_config(guild_id, "CANAL_VIDEO_INTRO_ID")
    canal_jerarquia = _get_iv_config(guild_id, "CANAL_JERARQUIA_ID")
    canal_encargados = _get_iv_config(guild_id, "CANAL_ENCARGADOS_ID")
    canal_df_info = _get_iv_config(guild_id, "CANAL_DF_INFO_ID")
    canal_df_postulacion = _get_iv_config(guild_id, "CANAL_DF_POSTULACION_ID")

    if nota is None:
        introduccion = (
            "Tu ingreso a la **Policía Federal Argentina** fue aprobado. ¡Felicitaciones!\n\n"
            "A continuación los canales que debés conocer desde el primer día:"
        )
    else:
        introduccion = (
            f"Aprobaste las oposiciones con **{nota}/{NOTA_MAXIMA}** respuestas correctas. "
            "¡Felicitaciones!\n\n"
            "A continuación los canales que debés conocer desde el primer día:"
        )

    embed = discord.Embed(
        title=f"🎉 ¡Bienvenido/a a la PFA, {postulante.display_name}!",
        description=introduccion,
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(
        name="📌 Canales esenciales",
        value=(
            f"🔤 Cambio de nombre → <#{canal_nombre}>\n"
            f"👔 Indumentaria → <#{canal_indumentaria}>\n"
            f"🎙️ Configuración TS3 → <#{canal_ts3}>\n"
            f"🎬 Video introductorio → <#{canal_video_intro}>\n"
            f"📊 Jerarquía y ascensos → <#{canal_jerarquia}>\n"
            f"👥 Encargados y subdivisiones → <#{canal_encargados}>"
        ),
        inline=False,
    )
    embed.add_field(
        name="⚠️ DOBLE FACCIÓN — LEER OBLIGATORIAMENTE",
        value=(
            "La PFA **NO** admite doble facción sin autorización previa.\n"
            "Si ya pertenecés a otra facción o querés hacerlo, **seguí el proceso oficial**:\n"
            f"📖 Información → <#{canal_df_info}>\n"
            f"📋 Postulación → <#{canal_df_postulacion}>"
        ),
        inline=False,
    )
    embed.set_footer(text="Ante cualquier duda, consultá a un encargado. ¡Bienvenido/a! 👮‍♂️")
    return embed


# ---------------------------------------------------------------------------
# Modales
# ---------------------------------------------------------------------------

class ModalAbrirOposiciones(discord.ui.Modal, title="📋 Abrir Opos"):
    horario_inicio = discord.ui.TextInput(
        label="Horario de inicio",
        placeholder="Ej: 20:00",
        max_length=10,
    )
    horario_cierre = discord.ui.TextInput(
        label="Horario de cierre estimado",
        placeholder="Ej: 21:30",
        max_length=10,
    )
    mensaje_extra = discord.ui.TextInput(
        label="Mensaje adicional (opcional)",
        placeholder="Ej: Traer cédula del personaje.",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=300,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if obtener_sesion_activa(interaction.user.id, interaction.guild.id):
            return await interaction.response.send_message(
                "⚠️ Ya tenés una sesión activa. Cerrala antes de abrir una nueva.",
                ephemeral=True,
            )

        sesion_id, numero_semanal = abrir_sesion(interaction.user.id, interaction.guild.id)

        guild_id = interaction.guild.id
        canal_post_id = _get_iv_config(guild_id, "CANAL_POSTULACIONES_ID")
        canal_post = interaction.guild.get_channel(canal_post_id)
        if canal_post:
            rol_civil_id = _get_iv_config(guild_id, "ROL_CIVIL_ID")
            mencion_civil = f"<@&{rol_civil_id}>" if rol_civil_id else ""
            contenido = (
                f"📋 **OPOSICIONES EN CURSO PARA INGRESAR A LA P.F.A!**\n\n"
                f"Las oposiciones de ingreso a la **Policía Federal Argentina** se encuentran "
                f"actualmente activas, a cargo de **{interaction.user.display_name}**.\n\n"
                f"⏰ Horario estimado: **{self.horario_inicio.value}** — **{self.horario_cierre.value}**\n"
                f"{mencion_civil}\n"
            )
            if self.mensaje_extra.value:
                contenido += f"📌 {self.mensaje_extra.value}\n"
            canal_sala_espera_id = _get_iv_config(guild_id, "CANAL_SALA_POSTULANTES_ID") or canal_post_id
            contenido += (
                f"\nIngresa a <#{canal_sala_espera_id}> para postularte "
                "y aguardá a ser llamado."
            )
            await canal_post.send(contenido)

        canal_bit_id = _get_iv_config(guild_id, "CANAL_BITACORA_OPOS_ID")
        canal_bit = interaction.guild.get_channel(canal_bit_id)
        if canal_bit:
            ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            semana_act = _ahora_local().isocalendar()[1]
            anio_act = _ahora_local().isocalendar()[0]
            embed = discord.Embed(
                title=f"🟢 Oposición #{numero_semanal} — {obtener_rango_fechas_semana(semana_act, anio_act)}",
                description=f"**A cargo de:** {interaction.user.mention}",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="🕐 Apertura", value=f"<t:{ts}:T>", inline=True)
            await canal_bit.send(embed=embed)

        await interaction.response.send_message(
            f"✅ Oposición **#{numero_semanal}** de la semana abierta. "
            f"Anuncio publicado en <#{canal_post_id}>.",
            ephemeral=True,
        )


class ModalEvaluarPostulante(discord.ui.Modal, title="📝 Evaluar"):
    postulante_id = discord.ui.TextInput(
        label="ID de Discord del postulante",
        placeholder="Ej: 123456789012345678",
        min_length=17,
        max_length=20,
    )
    nota = discord.ui.TextInput(
        label="Respuestas correctas (0–15)",
        placeholder="Ej: 11  |  Mínimo 10 para aprobar",
        max_length=2,
    )
    invitador_id = discord.ui.TextInput(
        label="ID del invitador (vacío si no fue invitado)",
        placeholder="Ej: 987654321098765432",
        required=False,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        sesion = obtener_sesion_activa(interaction.user.id, interaction.guild.id)
        if not sesion:
            return await interaction.followup.send(
                "⚠️ No tenés una sesión activa. Abrí oposiciones primero.",
                ephemeral=True,
            )

        try:
            nota_int = int(self.nota.value.strip())
            if not (0 <= nota_int <= NOTA_MAXIMA):
                raise ValueError
        except ValueError:
            return await interaction.followup.send(
                f"❌ La nota debe ser un número entre 0 y {NOTA_MAXIMA}.",
                ephemeral=True,
            )

        try:
            postulante_discord_id = int(self.postulante_id.value.strip())
        except ValueError:
            return await interaction.followup.send("❌ ID de postulante inválido.", ephemeral=True)

        postulante = interaction.guild.get_member(postulante_discord_id)
        if postulante is None:
            return await interaction.followup.send(
                f"❌ No se encontró al miembro con ID `{postulante_discord_id}` en el servidor.",
                ephemeral=True,
            )

        aprobado = nota_int >= NOTA_MINIMA

        if aprobado:
            await self._procesar_aprobacion(interaction, sesion, postulante, nota_int)
        else:
            await self._procesar_desaprobacion(interaction, sesion, postulante, nota_int)

    async def _procesar_aprobacion(
        self,
        interaction: discord.Interaction,
        sesion: dict,
        postulante: discord.Member,
        nota_int: int,
    ) -> None:
        guild_id = interaction.guild.id
        rol_pfa_id = _get_iv_config(guild_id, "ROL_PFA_ID")
        if any(r.id == rol_pfa_id for r in postulante.roles):
            return await interaction.followup.send(
                f"⚠️ {postulante.mention} ya tiene el rol @PFA.", ephemeral=True
            )

        invitador = None
        invitador_discord_id = None
        if self.invitador_id.value.strip():
            try:
                invitador_discord_id = int(self.invitador_id.value.strip())
                invitador = interaction.guild.get_member(invitador_discord_id)
            except ValueError:
                return await interaction.followup.send("❌ ID de invitador inválido.", ephemeral=True)

        roles_a_dar = [
            interaction.guild.get_role(rid)
            for rid in [
                rol_pfa_id,
                _get_iv_config(guild_id, "ROL_LOWPFA_ID"),
                _get_iv_config(guild_id, "ROL_CADETE_ID"),
                _get_iv_config(guild_id, "ROL_NUEVO_INGRESANTE_ID")
            ]
            if rid and interaction.guild.get_role(rid)
        ]
        try:
            await postulante.add_roles(
                *roles_a_dar,
                reason=f"Aprobado en oposiciones por {interaction.user.display_name}",
            )
        except discord.HTTPException as e:
            return await interaction.followup.send(f"❌ Error al asignar roles: {e}", ephemeral=True)

        registrar_nuevo_ingresante(postulante.id)
        limpiar_cooldown(postulante.id)
        registrar_resultado(sesion["id"], interaction.user.id, postulante.id, nota_int, True, invitador_discord_id)

        guild_id = interaction.guild.id
        canal_resultados_id = _get_iv_config(guild_id, "CANAL_RESULTADOS_ID")
        canal_resultados = interaction.guild.get_channel(canal_resultados_id)
        if canal_resultados:
            msg = (
                f"✅ {postulante.mention} aprobó las oposiciones con **{nota_int}/{NOTA_MAXIMA}** "
                f"respuestas correctas. ¡Bienvenido/a a la PFA! 🎉\n"
                f"👮 Interviewer: {interaction.user.mention}"
            )
            if invitador:
                msg += f"\n👥 Invitado/a por: {invitador.mention}"
            await canal_resultados.send(msg)

        canal_cambios_id = _get_iv_config(guild_id, "CANAL_CAMBIOS_PFA_ID")
        canal_cambios = interaction.guild.get_channel(canal_cambios_id)
        if canal_cambios:
            msg_cambios = (
                f"✅ {postulante.mention} > cadete > Nuevo "
                f"[Autorizado por: {interaction.user.mention}]\n"
                f"📝 Nota: **{nota_int}/{NOTA_MAXIMA}**"
            )
            if invitador:
                msg_cambios += f" | 👥 Invitado por: {invitador.mention}"
            await canal_cambios.send(msg_cambios)

        try:
            await postulante.send(embed=_build_dm_bienvenida(postulante, nota_int))
        except discord.HTTPException:
            pass

        if invitador_discord_id and canal_cambios:
            total_inv = contar_invitaciones_aprobadas(invitador_discord_id)
            if total_inv > 0 and total_inv % 3 == 0:
                inv_display = invitador.mention if invitador else f"<@{invitador_discord_id}>"
                await canal_cambios.send(
                    f"🌟 {inv_display} alcanzó **{total_inv} invitaciones aprobadas**. "
                    f"¡Un encargado debe evaluar su reconocimiento!"
                )

        await interaction.followup.send(
            f"✅ {postulante.mention} **aprobado** con **{nota_int}/{NOTA_MAXIMA}**. "
            f"Roles asignados, resultado publicado y DM enviado.",
            ephemeral=True,
        )

    async def _procesar_desaprobacion(
        self,
        interaction: discord.Interaction,
        sesion: dict,
        postulante: discord.Member,
        nota_int: int,
    ) -> None:
        registrar_resultado(sesion["id"], interaction.user.id, postulante.id, nota_int, False, None)
        set_cooldown(postulante.id)

        guild_id = interaction.guild.id
        canal_resultados_id = _get_iv_config(guild_id, "CANAL_RESULTADOS_ID")
        canal_resultados = interaction.guild.get_channel(canal_resultados_id)
        if canal_resultados:
            await canal_resultados.send(
                f"❌ {postulante.mention} no aprobó las oposiciones **({nota_int}/{NOTA_MAXIMA})**. "
                f"Podés volver a postularte en **{COOLDOWN_DIAS} días**. ¡Mucha suerte la próxima! 💪\n"
                f"👮 Interviewer: {interaction.user.mention}"
            )

        puede_desde = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=COOLDOWN_DIAS)
        try:
            await postulante.send(embed=discord.Embed(
                title="❌ No aprobaste las oposiciones",
                description=(
                    f"Obtuviste **{nota_int}/{NOTA_MAXIMA}** respuestas correctas.\n"
                    f"El mínimo para ingresar a la PFA es **{NOTA_MINIMA}/{NOTA_MAXIMA}**.\n\n"
                    f"Podrás volver a postularte el <t:{int(puede_desde.timestamp())}:F>.\n\n"
                    f"¡No te desanimes, seguí preparándote! 💪"
                ),
                color=discord.Color.red(),
            ))
        except discord.HTTPException:
            pass

        await interaction.followup.send(
            f"❌ {postulante.mention} **desaprobado** con **{nota_int}/{NOTA_MAXIMA}**. "
            f"Resultado publicado y cooldown de {COOLDOWN_DIAS} días establecido.",
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# View persistente
# ---------------------------------------------------------------------------

class ViewPanelInterviewer(discord.ui.View):
    """Panel operacional del interviewer. Persistente (sin timeout)."""

    def __init__(self):
        super().__init__(timeout=None)

    def _sin_permiso(self, interaction: discord.Interaction) -> bool:
        return not _es_interviewer(interaction.user)

    @discord.ui.button(
        label="Abrir Opos",
        style=discord.ButtonStyle.success,
        emoji="🟢",
        custom_id="iv_abrir_oposiciones",
        row=0,
    )
    async def btn_abrir(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._sin_permiso(interaction):
            return await interaction.response.send_message("⛔ Sin permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalAbrirOposiciones())

    @discord.ui.button(
        label="Cerrar Opos",
        style=discord.ButtonStyle.danger,
        emoji="🔴",
        custom_id="iv_cerrar_oposiciones",
        row=0,
    )
    async def btn_cerrar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._sin_permiso(interaction):
            return await interaction.response.send_message("⛔ Sin permiso.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        sesion = obtener_sesion_activa(interaction.user.id, interaction.guild.id)
        if not sesion:
            return await interaction.followup.send(
                "⚠️ No tenés una sesión activa.", ephemeral=True
            )

        ahora = datetime.datetime.now(datetime.timezone.utc)
        fa = sesion["fecha_apertura"]
        if fa.tzinfo is None:
            fa = fa.replace(tzinfo=datetime.timezone.utc)

        minutos = (ahora - fa).total_seconds() / 60
        if minutos < 30:
            return await interaction.followup.send(
                f"⏳ Las oposiciones deben estar abiertas al menos **30 minutos**. "
                f"Faltan **{int(30 - minutos)} minutos**.",
                ephemeral=True,
            )

        cerrar_sesion(sesion["id"])

        duracion_seg = int((ahora - fa).total_seconds())
        duracion_str = _fmt_horas(duracion_seg / 3600)

        resultados = obtener_resultados_sesion(sesion["id"])
        n_aprobados = sum(1 for r in resultados if r["aprobado"])
        n_desaprobados = len(resultados) - n_aprobados

        guild_id = interaction.guild.id
        canal_bit_id = _get_iv_config(guild_id, "CANAL_BITACORA_OPOS_ID")
        canal_bit = interaction.guild.get_channel(canal_bit_id)
        if canal_bit:
            semana_act = ahora.isocalendar()[1]
            anio_act = ahora.isocalendar()[0]
            embed = discord.Embed(
                title=f"🔴 Oposición #{sesion['numero_semanal']} — {obtener_rango_fechas_semana(semana_act, anio_act)}",
                description=f"**A cargo de:** {interaction.user.mention}",
                color=discord.Color.red(),
                timestamp=ahora,
            )
            embed.add_field(name="📅 Apertura", value=f"<t:{int(fa.timestamp())}:T>", inline=True)
            embed.add_field(name="📅 Cierre", value=f"<t:{int(ahora.timestamp())}:T>", inline=True)
            embed.add_field(name="⏰ Duración", value=duracion_str, inline=True)
            embed.add_field(
                name="👥 Cuestionarios tomados",
                value=(
                    f"**{len(resultados)}** personas evaluadas durante la sesión\n"
                    f"✅ {n_aprobados} aprobaron · ❌ {n_desaprobados} desaprobaron"
                ),
                inline=False,
            )
            await canal_bit.send(embed=embed)

        canal_post_id = _get_iv_config(guild_id, "CANAL_POSTULACIONES_ID")
        canal_post = interaction.guild.get_channel(canal_post_id)
        if canal_post:
            await canal_post.send(
                f"🔴 **Las oposiciones han finalizado.**\n"
                f"La sesión a cargo de **{interaction.user.display_name}** ha concluido. "
                f"¡Gracias a todos los que se presentaron!"
            )

        await interaction.followup.send(
            f"✅ Oposición **#{sesion['numero_semanal']}** cerrada. Duración: **{duracion_str}**.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Evaluar",
        style=discord.ButtonStyle.primary,
        emoji="📝",
        custom_id="iv_evaluar",
        row=0,
    )
    async def btn_evaluar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._sin_permiso(interaction):
            return await interaction.response.send_message("⛔ Sin permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalEvaluarPostulante())

    @discord.ui.button(
        label="Mis Estadísticas",
        style=discord.ButtonStyle.secondary,
        emoji="📊",
        custom_id="iv_mis_stats",
        row=0,
    )
    async def btn_mis_stats(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._sin_permiso(interaction):
            return await interaction.response.send_message("⛔ Sin permiso.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        stats = obtener_stats_semana(interaction.user.id)
        semana_iso = _ahora_local().isocalendar()[1]

        anio = _ahora_local().isocalendar()[0]
        embed = discord.Embed(
            title=f"📊 Tus estadísticas — {obtener_rango_fechas_semana(semana_iso, anio)}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="🕐 Sesiones", value=f"**{stats['n_sesiones']}**", inline=True)
        embed.add_field(name="⏱️ Horas", value=f"**{_fmt_horas(stats['horas'])}**", inline=True)
        embed.add_field(name="📋 Evaluados", value=f"**{stats['n_total']}**", inline=True)
        embed.add_field(name="✅ Aprobados", value=f"**{stats['n_aprobados']}**", inline=True)
        embed.add_field(name="❌ Desaprobados", value=f"**{stats['n_desaprobados']}**", inline=True)

        if stats["aprobados"]:
            lista = "\n".join(
                f"• <@{r['postulante_id']}> — {r['nota']}/{NOTA_MAXIMA}"
                for r in stats["aprobados"]
            )
            if len(lista) > 1024:
                lista = lista[:1000] + "\n..."
            embed.add_field(name="🎉 Ingresantes aprobados", value=lista, inline=False)

        sesion_activa = obtener_sesion_activa(interaction.user.id, interaction.guild.id)
        if sesion_activa:
            fa = sesion_activa["fecha_apertura"]
            if fa.tzinfo is None:
                fa = fa.replace(tzinfo=datetime.timezone.utc)
            embed.add_field(
                name="🟢 Sesión activa ahora",
                value=f"Abierta a las <t:{int(fa.timestamp())}:T>",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class PanelInterviewer(commands.Cog):
    """
    Cog del Panel Interviewer.
    Gestiona apertura/cierre de oposiciones, aprobación/desaprobación de
    postulantes y estadísticas semanales del interviewer.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_load(self) -> None:
        self.bot.add_view(ViewPanelInterviewer())

    @app_commands.command(
        name="panelinterviewer",
        description="Despliega el panel operacional de interviewer en este canal."
    )
    async def panel_interviewer(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild.id
        es_admin = interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator
        rol_encargado = _get_iv_config(guild_id, "ROL_ENCARGADO_INTERVIEWER_ID")
        rol_panel_admin = _get_iv_config(guild_id, "ROL_PANEL_ADMIN_ID")
        tiene_permiso = es_admin or any(r.id in (rol_encargado, rol_panel_admin) for r in interaction.user.roles)
        if not tiene_permiso:
            return await interaction.response.send_message(
                "⛔ No tenés permiso para desplegar este panel.", ephemeral=True
            )

        embed = discord.Embed(
            title="Bienvenido al Panel de Interviewer — PFA",
            description=(
                "**¡Hola, Interviewer!**\n\n"
                "Este panel te permite gestionar las oposiciones de ingreso a la "
                "**Policía Federal Argentina** de forma ordenada y eficiente. "
                "A continuación encontrás una descripción de cada función disponible:\n\n"
                "🟢 **Abrir Oposiciones:** Publica el anuncio en el canal de postulaciones "
                "con un ping a @civil e inicia el registro oficial de la sesión.\n\n"
                "🔴 **Cerrar Oposiciones:** Finaliza la sesión activa y publica el resumen "
                "con duración y cantidad de evaluados. Requiere un mínimo de 30 minutos desde la apertura.\n\n"
                "📝 **Evaluar Postulante:** Cargá el ID del postulante y su nota sobre 15. "
                "Si obtuvo 10 o más ingresa a la institución — se le asignan los roles automáticamente "
                "y recibe un DM de bienvenida. Si obtuvo 9 o menos, se le notifica el resultado "
                "y queda con un período de espera de 3 días antes de poder volver a postularse.\n\n"
                "📊 **Mis Estadísticas:** Consultá tu desempeño de la semana en curso: "
                "sesiones tomadas, horas totales, cantidad de evaluados y lista de ingresantes aprobados.\n\n"
                "Operá con responsabilidad. Cada acción queda registrada en el sistema."
            ),
            color=discord.Color.dark_blue(),
        )
        embed.set_footer(text="PFA — Ibiza Roleplay")
        await interaction.response.send_message(embed=embed, view=ViewPanelInterviewer())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PanelInterviewer(bot))
