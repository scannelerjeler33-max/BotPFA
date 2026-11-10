import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import datetime
from dotenv import load_dotenv
from databases.connection import get_connection
from utils.config import obtener_config_int, safe_env_int

load_dotenv()

# Offset horario local respecto a UTC (ej: -3 para Argentina, +2 para España en verano)
_TZ_OFFSET = safe_env_int("BOT_TIMEZONE_OFFSET", 0)
_TZ_LOCAL   = datetime.timezone(datetime.timedelta(hours=_TZ_OFFSET))

# --- CONEXIÓN A BASE DE DATOS ---
conn_enc = get_connection()
conn_enc.autocommit = True
cursor_enc = conn_enc.cursor()

# --- CONFIGURACIÓN VIA .ENV ---
ROL_ENCARGADO_INTERVIEWER_ID = safe_env_int("ROL_ENCARGADO_INTERVIEWER_ID", 0)
ROL_PANEL_ADMIN_ID           = safe_env_int("ROL_PANEL_ADMIN_ID", 0)
CANAL_BITACORA_OPOS_ID       = safe_env_int("CANAL_BITACORA_OPOS_ID", 0)

def _get_iv_config(guild_id: int, key: str) -> int:
    fallback = globals().get(key, 0)
    return obtener_config_int(guild_id, key, fallback)

NOTA_MAXIMA = 15


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _semana_actual() -> tuple[int, int]:
    ahora = datetime.datetime.now(_TZ_LOCAL)
    return ahora.isocalendar()[1], ahora.year


def _fmt_horas(horas_decimal: float) -> str:
    h = int(horas_decimal)
    m = int((horas_decimal - h) * 60)
    return f"{h}h {m}m" if h else f"{m}m"


def obtener_rango_fechas_semana(semana_iso: int, anio: int) -> str:
    lunes = datetime.datetime.fromisocalendar(anio, semana_iso, 1)
    domingo = lunes + datetime.timedelta(days=6)
    return f"{lunes.strftime('%d/%m')} - {domingo.strftime('%d/%m')}"


def _sin_permiso(interaction: discord.Interaction) -> bool:
    if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator:
        return False
    guild_id = interaction.guild.id
    rol_encargado = _get_iv_config(guild_id, "ROL_ENCARGADO_INTERVIEWER_ID")
    rol_panel_admin = _get_iv_config(guild_id, "ROL_PANEL_ADMIN_ID")
    ids = {r.id for r in interaction.user.roles}
    return not bool(ids & {rol_encargado, rol_panel_admin})


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def obtener_stats_semana_todos(semana_iso: int = None, anio: int = None) -> list[dict]:
    """Stats de todos los interviewers en la semana actual o específica, ordenado por aprobados."""
    if semana_iso is None or anio is None:
        semana_iso, anio = _semana_actual()
    cursor_enc.execute(
        """
        SELECT
            r.interviewer_id,
            COUNT(DISTINCT s.id)                                                 AS sesiones,
            COALESCE(SUM(
                EXTRACT(EPOCH FROM (COALESCE(s.fecha_cierre, NOW()) - s.fecha_apertura)) / 3600
            ), 0)                                                                AS horas,
            COUNT(r.id)                                                          AS total_eval,
            COUNT(r.id) FILTER (WHERE r.aprobado = TRUE)                        AS aprobados,
            COUNT(r.id) FILTER (WHERE r.aprobado = FALSE)                       AS desaprobados
        FROM oposiciones_resultados r
        LEFT JOIN oposiciones_sesiones s ON r.sesion_id = s.id
        WHERE r.semana_iso = %s AND r.anio = %s AND (r.guild_id = %s OR r.guild_id IS NULL)
        GROUP BY r.interviewer_id
        """,
        (semana_iso, anio),
    )
    raw_results = cursor_enc.fetchall()

    cursor_enc.execute(
        "SELECT interviewer_id, COALESCE(SUM(aprobados_ajuste), 0), COALESCE(SUM(horas_ajuste), 0.0) FROM oposiciones_ajustes WHERE semana_iso = %s AND anio = %s GROUP BY interviewer_id",
        (semana_iso, anio)
    )
    ajustes = {row[0]: (int(row[1]), float(row[2])) for row in cursor_enc.fetchall()}

    merged = {}
    for r in raw_results:
        uid = r[0]
        merged[uid] = {
            "sesiones": r[1],
            "horas": float(r[2]),
            "total_eval": r[3],
            "aprobados": r[4],
            "desaprobados": r[5],
        }

    for uid, (aj_aprobados, aj_horas) in ajustes.items():
        if uid not in merged:
            merged[uid] = {
                "sesiones": 0,
                "horas": 0.0,
                "total_eval": 0,
                "aprobados": 0,
                "desaprobados": 0,
            }
        merged[uid]["aprobados"] = max(0, merged[uid]["aprobados"] + aj_aprobados)
        merged[uid]["horas"] = max(0.0, merged[uid]["horas"] + aj_horas)

    stats_list = [
        {
            "interviewer_id": uid,
            "sesiones": data["sesiones"],
            "horas": data["horas"],
            "total_eval": data["total_eval"],
            "aprobados": data["aprobados"],
            "desaprobados": data["desaprobados"],
        }
        for uid, data in merged.items()
    ]
    stats_list.sort(key=lambda x: x["aprobados"], reverse=True)
    return stats_list


def obtener_sesiones_activas() -> list[dict]:
    cursor_enc.execute(
        "SELECT id, interviewer_id, fecha_apertura, numero_semanal "
        "FROM oposiciones_sesiones WHERE activa = TRUE"
    )
    return [
        {"id": r[0], "interviewer_id": r[1], "fecha_apertura": r[2], "numero_semanal": r[3]}
        for r in cursor_enc.fetchall()
    ]


def obtener_historial_semana() -> list[dict]:
    semana_iso, anio = _semana_actual()
    cursor_enc.execute(
        """
        SELECT id, interviewer_id, fecha_apertura, fecha_cierre, numero_semanal
        FROM oposiciones_sesiones
        WHERE semana_iso = %s AND anio = %s AND activa = FALSE
        ORDER BY fecha_apertura
        """,
        (semana_iso, anio),
    )
    return [
        {"id": r[0], "interviewer_id": r[1], "fecha_apertura": r[2],
         "fecha_cierre": r[3], "numero_semanal": r[4]}
        for r in cursor_enc.fetchall()
    ]


def obtener_stats_interviewer(interviewer_id: int) -> dict:
    semana_iso, anio = _semana_actual()

    cursor_enc.execute(
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
    s = cursor_enc.fetchone()

    cursor_enc.execute(
        """
        SELECT postulante_id, nota, aprobado, invitado_por, fecha
        FROM oposiciones_resultados
        WHERE interviewer_id = %s AND semana_iso = %s AND anio = %s
        ORDER BY fecha
        """,
        (interviewer_id, semana_iso, anio),
    )
    resultados = [
        {"postulante_id": r[0], "nota": r[1], "aprobado": r[2],
         "invitado_por": r[3], "fecha": r[4]}
        for r in cursor_enc.fetchall()
    ]

    cursor_enc.execute(
        "SELECT COALESCE(SUM(horas_ajuste), 0.0) FROM oposiciones_ajustes WHERE interviewer_id = %s AND semana_iso = %s AND anio = %s",
        (interviewer_id, semana_iso, anio)
    )
    horas_aj = float(cursor_enc.fetchone()[0] or 0.0)

    return {
        "n_sesiones": s[0],
        "horas": max(0.0, float(s[1]) + horas_aj),
        "resultados": resultados,
    }


def compilar_resumen_semanal() -> dict:
    semana_iso, anio = _semana_actual()
    stats_todos = obtener_stats_semana_todos()

    cursor_enc.execute(
        "SELECT COUNT(*) FROM oposiciones_sesiones WHERE semana_iso = %s AND anio = %s",
        (semana_iso, anio),
    )
    total_sesiones = cursor_enc.fetchone()[0]

    cursor_enc.execute(
        "SELECT COUNT(*), COUNT(*) FILTER (WHERE aprobado = TRUE) "
        "FROM oposiciones_resultados WHERE semana_iso = %s AND anio = %s",
        (semana_iso, anio),
    )
    row_t = cursor_enc.fetchone()

    cursor_enc.execute(
        """
        SELECT COALESCE(SUM(
            EXTRACT(EPOCH FROM (COALESCE(fecha_cierre, NOW()) - fecha_apertura)) / 3600
        ), 0)
        FROM oposiciones_sesiones WHERE semana_iso = %s AND anio = %s
        """,
        (semana_iso, anio),
    )
    total_horas = float(cursor_enc.fetchone()[0])

    cursor_enc.execute(
        "SELECT COALESCE(SUM(aprobados_ajuste), 0), COALESCE(SUM(horas_ajuste), 0.0) FROM oposiciones_ajustes WHERE semana_iso = %s AND anio = %s",
        (semana_iso, anio)
    )
    total_aprobados_aj, total_horas_aj = cursor_enc.fetchone()
    total_aprobados_aj = int(total_aprobados_aj or 0)
    total_horas_aj = float(total_horas_aj or 0.0)

    return {
        "semana_iso": semana_iso,
        "anio": anio,
        "total_sesiones": total_sesiones,
        "total_evaluados": row_t[0],
        "total_aprobados": max(0, row_t[1] + total_aprobados_aj),
        "total_horas": round(max(0.0, total_horas + total_horas_aj), 2),
        "por_interviewer": stats_todos,
    }


def cerrar_sesiones_activas_forzado() -> int:
    """Cierra todas las sesiones abiertas. Retorna la cantidad cerrada."""
    cursor_enc.execute(
        "UPDATE oposiciones_sesiones SET fecha_cierre = NOW(), activa = FALSE WHERE activa = TRUE"
    )
    return cursor_enc.rowcount


def guardar_cierre_semanal(cerrado_por: int, resumen: dict) -> None:
    cursor_enc.execute(
        """
        INSERT INTO oposiciones_cierre_semanal
            (semana_iso, anio, cerrado_por, total_sesiones, total_evaluados,
             total_aprobados, total_horas_decimal, resumen_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            resumen["semana_iso"], resumen["anio"], cerrado_por,
            resumen["total_sesiones"], resumen["total_evaluados"],
            resumen["total_aprobados"], resumen["total_horas"],
            json.dumps(resumen["por_interviewer"]),
        ),
    )


def ya_cerrada_semana() -> bool:
    semana_iso, anio = _semana_actual()
    cursor_enc.execute(
        "SELECT 1 FROM oposiciones_cierre_semanal WHERE semana_iso = %s AND anio = %s",
        (semana_iso, anio),
    )
    return cursor_enc.fetchone() is not None


# ---------------------------------------------------------------------------
# Modal
# ---------------------------------------------------------------------------

class ModalConsultarInterviewer(discord.ui.Modal, title="🔍 Consultar Interviewer"):
    interviewer_id = discord.ui.TextInput(
        label="ID de Discord del interviewer",
        placeholder="Ej: 123456789012345678",
        min_length=17,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        try:
            iv_id = int(self.interviewer_id.value.strip())
        except ValueError:
            return await interaction.followup.send("❌ ID inválido.", ephemeral=True)

        miembro = interaction.guild.get_member(iv_id)
        nombre = miembro.display_name if miembro else f"ID: {iv_id}"

        stats = obtener_stats_interviewer(iv_id)
        semana_iso, _ = _semana_actual()

        cursor_enc.execute(
            "SELECT COALESCE(SUM(aprobados_ajuste), 0) FROM oposiciones_ajustes WHERE interviewer_id = %s AND semana_iso = %s AND anio = %s",
            (iv_id, semana_iso, _semana_actual()[1])
        )
        aj_ap = int(cursor_enc.fetchone()[0] or 0)
        n_aprobados = max(0, sum(1 for r in stats["resultados"] if r["aprobado"]) + aj_ap)
        n_desaprobados = max(0, len(stats["resultados"]) - sum(1 for r in stats["resultados"] if r["aprobado"]))

        embed = discord.Embed(
            title=f"🔍 Informe de {nombre} — {obtener_rango_fechas_semana(semana_iso, _semana_actual()[1])}",
            color=discord.Color.dark_teal(),
            timestamp=discord.utils.utcnow(),
        )
        if miembro:
            embed.set_thumbnail(url=miembro.display_avatar.url)

        embed.add_field(name="📋 Sesiones", value=f"**{stats['n_sesiones']}**", inline=True)
        embed.add_field(name="⏱️ Horas", value=f"**{_fmt_horas(stats['horas'])}**", inline=True)
        embed.add_field(name="📊 Evaluados", value=f"**{len(stats['resultados'])}**", inline=True)
        embed.add_field(name="✅ Aprobados", value=f"**{n_aprobados}**", inline=True)
        embed.add_field(name="❌ Desaprobados", value=f"**{n_desaprobados}**", inline=True)

        if stats["resultados"]:
            detalle = []
            for r in stats["resultados"][:15]:
                icono = "✅" if r["aprobado"] else "❌"
                linea = f"{icono} <@{r['postulante_id']}> — {r['nota']}/{NOTA_MAXIMA}"
                if r["invitado_por"]:
                    linea += f" *(inv. <@{r['invitado_por']}>)*"
                detalle.append(linea)
            valor = "\n".join(detalle)
            if len(stats["resultados"]) > 15:
                valor += f"\n*...y {len(stats['resultados']) - 15} más*"
            embed.add_field(name="📋 Detalle de evaluaciones", value=valor, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# View persistente
# ---------------------------------------------------------------------------

class ViewPanelEncargado(discord.ui.View):
    """Panel de supervisión del encargado de interviewers. Persistente (sin timeout)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Resumen Semanal",
        style=discord.ButtonStyle.primary,
        emoji="📊",
        custom_id="enc_resumen_semanal",
        row=0,
    )
    async def btn_resumen(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if _sin_permiso(interaction):
            return await interaction.response.send_message("⛔ Sin permiso.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        stats = obtener_stats_semana_todos()
        semana_iso, anio = _semana_actual()

        embed = discord.Embed(
            title=f"📊 Resumen Semanal — {obtener_rango_fechas_semana(semana_iso, anio)}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )

        if not stats:
            embed.description = "No hay actividad registrada esta semana."
        else:
            for s in stats:
                embed.add_field(
                    name=f"<@{s['interviewer_id']}>",
                    value=(
                        f"📋 {s['sesiones']} sesiones · ⏱️ {_fmt_horas(s['horas'])}\n"
                        f"✅ {s['aprobados']} aprobados · ❌ {s['desaprobados']} desaprobados\n"
                        f"📊 {s['total_eval']} evaluados en total"
                    ),
                    inline=False,
                )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="TOP Interviewers",
        style=discord.ButtonStyle.primary,
        emoji="🏆",
        custom_id="enc_top",
        row=0,
    )
    async def btn_top(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if _sin_permiso(interaction):
            return await interaction.response.send_message("⛔ Sin permiso.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        stats = obtener_stats_semana_todos()
        semana_iso, anio = _semana_actual()

        embed = discord.Embed(
            title=f"🏆 TOP Interviewers — {obtener_rango_fechas_semana(semana_iso, anio)}",
            description="Ranking por candidatos aprobados esta semana.",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow(),
        )

        if not stats:
            embed.description = "No hay actividad registrada esta semana."
        else:
            medallas = {1: "🥇", 2: "🥈", 3: "🥉"}
            for i, s in enumerate(stats, start=1):
                miembro = interaction.guild.get_member(s["interviewer_id"])
                nombre = miembro.display_name if miembro else f"ID {s['interviewer_id']}"
                mencion = miembro.mention if miembro else f"<@{s['interviewer_id']}>"
                embed.add_field(
                    name=f"{medallas.get(i, f'#{i}')} {nombre}",
                    value=(
                        f"{mencion}\n"
                        f"**{s['aprobados']}** aprobados · "
                        f"{s['sesiones']} sesiones · {_fmt_horas(s['horas'])}"
                    ),
                    inline=False,
                )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Consultar Interviewer",
        style=discord.ButtonStyle.secondary,
        emoji="🔍",
        custom_id="enc_consultar",
        row=1,
    )
    async def btn_consultar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if _sin_permiso(interaction):
            return await interaction.response.send_message("⛔ Sin permiso.", ephemeral=True)
        await interaction.response.send_modal(ModalConsultarInterviewer())

    @discord.ui.button(
        label="Oposiciones Activas",
        style=discord.ButtonStyle.secondary,
        emoji="📋",
        custom_id="enc_activas",
        row=1,
    )
    async def btn_activas(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if _sin_permiso(interaction):
            return await interaction.response.send_message("⛔ Sin permiso.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        activas = obtener_sesiones_activas()
        ahora = datetime.datetime.now(datetime.timezone.utc)

        embed = discord.Embed(
            title="📋 Oposiciones Activas Ahora",
            color=discord.Color.green() if activas else discord.Color.light_grey(),
            timestamp=ahora,
        )

        if not activas:
            embed.description = "No hay oposiciones abiertas en este momento."
        else:
            for s in activas:
                fa = s["fecha_apertura"]
                if fa.tzinfo is None:
                    fa = fa.replace(tzinfo=datetime.timezone.utc)
                min_trans = int((ahora - fa).total_seconds() / 60)
                embed.add_field(
                    name=f"<@{s['interviewer_id']}> — Opo #{s['numero_semanal']}",
                    value=f"🟢 Abierta hace **{min_trans} min** (<t:{int(fa.timestamp())}:T>)",
                    inline=False,
                )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Historial de la Semana",
        style=discord.ButtonStyle.secondary,
        emoji="📅",
        custom_id="enc_historial",
        row=2,
    )
    async def btn_historial(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if _sin_permiso(interaction):
            return await interaction.response.send_message("⛔ Sin permiso.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        historial = obtener_historial_semana()
        semana_iso, anio = _semana_actual()

        embed = discord.Embed(
            title=f"📅 Sesiones Cerradas — {obtener_rango_fechas_semana(semana_iso, anio)}",
            color=discord.Color.dark_blue(),
            timestamp=discord.utils.utcnow(),
        )

        if not historial:
            embed.description = "No hay sesiones cerradas esta semana."
        else:
            for s in historial[:10]:
                fa = s["fecha_apertura"]
                fc = s["fecha_cierre"]
                if fa and fa.tzinfo is None:
                    fa = fa.replace(tzinfo=datetime.timezone.utc)
                if fc and fc.tzinfo is None:
                    fc = fc.replace(tzinfo=datetime.timezone.utc)
                duracion = ""
                if fa and fc:
                    seg = int((fc - fa).total_seconds())
                    duracion = _fmt_horas(seg / 3600)
                embed.add_field(
                    name=f"Opo #{s['numero_semanal']} — <@{s['interviewer_id']}>",
                    value=f"<t:{int(fa.timestamp())}:t> → <t:{int(fc.timestamp())}:t> · **{duracion}**",
                    inline=False,
                )
            if len(historial) > 10:
                embed.set_footer(text=f"Mostrando 10 de {len(historial)} sesiones.")

        await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class PanelEncargadoInterviewer(commands.Cog):
    """
    Cog del Panel Encargado de Interviewer.
    Provee supervisión, métricas y el comando /cierresemanal.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_load(self) -> None:
        self.bot.add_view(ViewPanelEncargado())
        self.publicar_top_semanal_automatico.start()

    def cog_unload(self) -> None:
        self.publicar_top_semanal_automatico.cancel()

    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=_TZ_LOCAL))
    async def publicar_top_semanal_automatico(self) -> None:
        ahora = datetime.datetime.now(_TZ_LOCAL)
        if ahora.weekday() != 0:  # 0 es lunes
            return

        # Obtenemos la semana anterior (domingo)
        ayer = ahora - datetime.timedelta(days=1)
        semana_iso_anterior = ayer.isocalendar()[1]
        anio_anterior = ayer.year

        stats = obtener_stats_semana_todos(semana_iso=semana_iso_anterior, anio=anio_anterior)

        for guild in self.bot.guilds:
            canal_id = obtener_config_int(guild.id, "CANAL_TOP_INTERVIEWERS_ID", 1437600758894694411)
            canal = guild.get_channel(canal_id)
            if not canal:
                continue

            embed = discord.Embed(
                title=f"🏆 TOP Interviewers — Cierre {obtener_rango_fechas_semana(semana_iso_anterior, anio_anterior)}",
                description="Ranking final por candidatos aprobados de la semana pasada.",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow(),
            )

            if not stats:
                embed.description = "No se registró actividad de oposiciones la semana pasada."
            else:
                medallas = {1: "🥇", 2: "🥈", 3: "🥉"}
                for i, s in enumerate(stats, start=1):
                    miembro = guild.get_member(s["interviewer_id"])
                    nombre = miembro.display_name if miembro else f"ID {s['interviewer_id']}"
                    mencion = miembro.mention if miembro else f"<@{s['interviewer_id']}>"
                    embed.add_field(
                        name=f"{medallas.get(i, f'#{i}')} {nombre}",
                        value=(
                            f"{mencion}\n"
                            f"**{s['aprobados']}** aprobados · "
                            f"{s['sesiones']} sesiones · {_fmt_horas(s['horas'])}"
                        ),
                        inline=False,
                    )

            try:
                await canal.send(embed=embed)
            except Exception as e:
                print(f"Error al enviar el top semanal automático de interviewers: {e}")

    @app_commands.command(
        name="panelencargado",
        description="Despliega el panel de supervisión de interviewers en este canal."
    )
    async def panel_encargado(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild.id
        rol_encargado = _get_iv_config(guild_id, "ROL_ENCARGADO_INTERVIEWER_ID")
        rol_panel_admin = _get_iv_config(guild_id, "ROL_PANEL_ADMIN_ID")
        tiene_permiso = any(r.id in (rol_encargado, rol_panel_admin) for r in interaction.user.roles)
        if not tiene_permiso:
            return await interaction.response.send_message(
                "⛔ No tenés permiso para ejecutar este comando.", ephemeral=True
            )

        embed = discord.Embed(
            title="Bienvenido al Panel de Encargado de Interviewers — PFA",
            description=(
                "**¡Hola, Encargado!**\n\n"
                "Este panel te permite supervisar el desempeño del equipo de interviewers "
                "y gestionar el ciclo semanal de oposiciones de ingreso a la "
                "**Policía Federal Argentina**. "
                "A continuación encontrás una descripción de cada función disponible:\n\n"
                "📊 **Resumen Semanal:** Vista general del rendimiento de todos los interviewers "
                "en la semana en curso: sesiones tomadas, horas acumuladas, aprobados y desaprobados.\n\n"
                "🏆 **TOP Interviewers:** Ranking semanal ordenado por cantidad de postulantes "
                "aprobados. Ideal para reconocer el trabajo del equipo.\n\n"
                "🔍 **Consultar Interviewer:** Accedé al informe detallado de un interviewer "
                "específico ingresando su ID de Discord. Incluye cada evaluación realizada "
                "con nota e invitador si corresponde.\n\n"
                "📋 **Oposiciones Activas:** Visualizá en tiempo real qué interviewers tienen "
                "una sesión abierta en este momento y desde hace cuánto tiempo.\n\n"
                "📅 **Historial de la Semana:** Revisá todas las sesiones cerradas de la semana "
                "actual con sus horarios y duración.\n\n"
                "Utilizá el comando **/cierresemanal** para archivar el historial de la semana, "
                "cerrar sesiones olvidadas automáticamente y preparar el sistema para el nuevo período."
            ),
            color=discord.Color.dark_gold(),
        )
        embed.set_footer(text="PFA — Ibiza Roleplay")
        await interaction.response.send_message(embed=embed, view=ViewPanelEncargado())

    @app_commands.command(
        name="cierresemanal",
        description="Archiva el historial de la semana y prepara el reset para la semana entrante."
    )
    async def cierre_semanal(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild.id
        rol_encargado = _get_iv_config(guild_id, "ROL_ENCARGADO_INTERVIEWER_ID")
        rol_panel_admin = _get_iv_config(guild_id, "ROL_PANEL_ADMIN_ID")
        tiene_permiso = any(r.id in (rol_encargado, rol_panel_admin) for r in interaction.user.roles)
        if not tiene_permiso:
            return await interaction.response.send_message(
                "⛔ No tenés permiso para ejecutar este comando.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        if ya_cerrada_semana():
            return await interaction.followup.send(
                "⚠️ La semana actual ya fue cerrada. El reset es automático al cambiar la semana ISO.",
                ephemeral=True,
            )

        n_forzadas = cerrar_sesiones_activas_forzado()
        resumen = compilar_resumen_semanal()
        guardar_cierre_semanal(interaction.user.id, resumen)

        semana_iso = resumen["semana_iso"]

        embed = discord.Embed(
            title=f"📁 Cierre Semanal — {obtener_rango_fechas_semana(semana_iso, resumen['anio'])}",
            description=f"Archivado por {interaction.user.mention}.",
            color=discord.Color.dark_purple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="📋 Sesiones", value=f"**{resumen['total_sesiones']}**", inline=True)
        embed.add_field(
            name="⏱️ Horas totales",
            value=f"**{_fmt_horas(resumen['total_horas'])}**",
            inline=True,
        )
        embed.add_field(name="👥 Evaluados", value=f"**{resumen['total_evaluados']}**", inline=True)
        embed.add_field(name="✅ Aprobados", value=f"**{resumen['total_aprobados']}**", inline=True)

        if n_forzadas:
            embed.add_field(
                name="⚠️ Sesiones auto-cerradas",
                value=f"{n_forzadas} sesión(es) se cerraron automáticamente al hacer el cierre.",
                inline=False,
            )

        if resumen["por_interviewer"]:
            tabla = []
            for s in resumen["por_interviewer"]:
                tabla.append(
                    f"<@{s['interviewer_id']}> — ✅ {s['aprobados']} · "
                    f"📋 {s['sesiones']} sesiones · ⏱️ {_fmt_horas(s['horas'])}"
                )
            embed.add_field(
                name="📊 Resumen por interviewer",
                value="\n".join(tabla)[:1024],
                inline=False,
            )

        embed.set_footer(text="El reset es automático: la semana entrante tiene nuevo período ISO.")

        canal_bit_id = _get_iv_config(guild_id, "CANAL_BITACORA_OPOS_ID")
        canal_bit = interaction.guild.get_channel(canal_bit_id)
        if canal_bit:
            await canal_bit.send(embed=embed)

        await interaction.followup.send(
            f"✅ Cierre semanal completado. Informe enviado a <#{canal_bit_id}>.",
            ephemeral=True,
        )

    @app_commands.command(
        name="inter_restar_aprobados",
        description="Resta una cantidad de aprobados a las estadísticas semanales de un interviewer."
    )
    @app_commands.describe(
        interviewer="El interviewer al que se le restarán los aprobados.",
        cantidad="La cantidad de aprobados a restar (número entero positivo)."
    )
    async def inter_restar_aprobados(self, interaction: discord.Interaction, interviewer: discord.Member, cantidad: int) -> None:
        guild_id = interaction.guild.id
        rol_encargado = _get_iv_config(guild_id, "ROL_ENCARGADO_INTERVIEWER_ID")
        rol_panel_admin = _get_iv_config(guild_id, "ROL_PANEL_ADMIN_ID")
        tiene_permiso = any(r.id in (rol_encargado, rol_panel_admin) for r in interaction.user.roles)
        if not tiene_permiso:
            return await interaction.response.send_message(
                "⛔ No tenés permiso para ejecutar este comando.", ephemeral=True
            )

        if cantidad <= 0:
            return await interaction.response.send_message("❌ La cantidad debe ser un número entero positivo.", ephemeral=True)

        semana_iso, anio = _semana_actual()
        cursor_enc.execute(
            """
            INSERT INTO oposiciones_ajustes (interviewer_id, aprobados_ajuste, horas_ajuste, semana_iso, anio)
            VALUES (%s, %s, 0.0, %s, %s)
            """,
            (interviewer.id, -cantidad, semana_iso, anio)
        )
        await interaction.response.send_message(
            f"✅ Se han restado **{cantidad}** aprobados de las estadísticas semanales de {interviewer.mention} ({obtener_rango_fechas_semana(semana_iso, anio)}).",
            ephemeral=True
        )

    @app_commands.command(
        name="inter_restar_tiempo",
        description="Resta una cantidad de horas a las estadísticas semanales de un interviewer."
    )
    @app_commands.describe(
        interviewer="El interviewer al que se le restará el tiempo.",
        horas="La cantidad de horas a restar (ejemplo: 1.5)."
    )
    async def inter_restar_tiempo(self, interaction: discord.Interaction, interviewer: discord.Member, horas: float) -> None:
        guild_id = interaction.guild.id
        rol_encargado = _get_iv_config(guild_id, "ROL_ENCARGADO_INTERVIEWER_ID")
        rol_panel_admin = _get_iv_config(guild_id, "ROL_PANEL_ADMIN_ID")
        tiene_permiso = any(r.id in (rol_encargado, rol_panel_admin) for r in interaction.user.roles)
        if not tiene_permiso:
            return await interaction.response.send_message(
                "⛔ No tenés permiso para ejecutar este comando.", ephemeral=True
            )

        if horas <= 0:
            return await interaction.response.send_message("❌ La cantidad de horas debe ser un número positivo.", ephemeral=True)

        semana_iso, anio = _semana_actual()
        cursor_enc.execute(
            """
            INSERT INTO oposiciones_ajustes (interviewer_id, aprobados_ajuste, horas_ajuste, semana_iso, anio)
            VALUES (%s, 0, %s, %s, %s)
            """,
            (interviewer.id, -horas, semana_iso, anio)
        )
        await interaction.response.send_message(
            f"✅ Se han restado **{horas}h** de las estadísticas semanales de {interviewer.mention} ({obtener_rango_fechas_semana(semana_iso, anio)}).",
            ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PanelEncargadoInterviewer(bot))
