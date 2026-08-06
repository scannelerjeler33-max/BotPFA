import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import datetime
from databases.connection import get_connection
from utils.config import obtener_config_int

# --- CONFIGURACIÓN (usada como fallback si el servidor no configuró nada) ---
ROL_PFA_ID = int(os.getenv("ROL_PFA_ID", "0"))
ROL_PANEL_ADMIN_ID = int(os.getenv("ROL_PANEL_ADMIN_ID", "0"))
_CANAL_TURNOS_ENV = os.getenv("CANAL_TURNOS_ID", "0").strip()
CANAL_TURNOS_ID = int(_CANAL_TURNOS_ENV) if _CANAL_TURNOS_ENV.isdigit() else 0

# --- BASE DE DATOS ---
conn = get_connection()
conn.autocommit = True
cursor = conn.cursor()

# 1. Crear tabla para el registro
cursor.execute("""
    CREATE TABLE IF NOT EXISTS turnos_oficiales (
        user_id BIGINT PRIMARY KEY,
        turno_activo BOOLEAN DEFAULT FALSE,
        inicio_turno TIMESTAMPTZ,
        turnos_semana INTEGER DEFAULT 0,
        horas_semana NUMERIC(6,2) DEFAULT 0.0
    )
""")

# --- VISTA: BOTÓN AFK ---
class ViewConfirmacionAFK(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120) # 2 minutos para responder
        self.user_id = user_id
        self.respondido = False

    @discord.ui.button(label="¡Sigo patrullando!", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.respondido = True
        self.stop()
        await interaction.response.send_message("✅ ¡Entendido! Sigue con tu servicio.", ephemeral=True)

# --- VISTA: BOTONES DEL PANEL ---
class ViewPanelTurnos(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir Turno", style=discord.ButtonStyle.success, emoji="🟢", custom_id="btn_abrir_turno_v1")
    async def btn_abrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verificar rol PFA
        rol_pfa_id = obtener_config_int(interaction.guild.id, "ROL_PFA_ID", ROL_PFA_ID)
        if not any(r.id == rol_pfa_id for r in interaction.user.roles):
            return await interaction.response.send_message("⛔ Solo los oficiales de la PFA pueden abrir turno.", ephemeral=True)
        
        # Verificar si ya tiene un turno abierto
        cursor.execute("SELECT turno_activo FROM turnos_oficiales WHERE user_id = %s", (interaction.user.id,))
        res = cursor.fetchone()
        if res and res[0]:
            return await interaction.response.send_message("⚠️ Ya tienes un turno abierto en este momento.", ephemeral=True)
        
        # Guardar en base de datos
        cursor.execute("""
            INSERT INTO turnos_oficiales (user_id, turno_activo, inicio_turno)
            VALUES (%s, TRUE, NOW())
            ON CONFLICT (user_id) DO UPDATE SET turno_activo = TRUE, inicio_turno = NOW()
        """, (interaction.user.id,))
        
        # Anuncio en el canal de turnos
        canal_turnos_id = obtener_config_int(interaction.guild.id, "CANAL_TURNOS_ID", CANAL_TURNOS_ID)
        canal = interaction.guild.get_channel(canal_turnos_id)
        if canal:
            embed = discord.Embed(
                title="🟢 INICIO DE SERVICIO",
                description=f"{interaction.user.mention} ha entrado de servicio en la ciudad.", 
                color=discord.Color.green(), 
                timestamp=discord.utils.utcnow()
            )
            await canal.send(embed=embed)
        
        await interaction.response.send_message("✅ **Turno iniciado.** Recuerda que cada 30 mins recibirás una verificación de seguridad por MD y se cerrará automáticamente en 3 horas.", ephemeral=True)

    @discord.ui.button(label="Cerrar Turno", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="btn_cerrar_turno_v1")
    async def btn_cerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verificar si tiene turno activo
        cursor.execute("SELECT turno_activo, inicio_turno FROM turnos_oficiales WHERE user_id = %s", (interaction.user.id,))
        res = cursor.fetchone()
        if not res or not res[0]:
            return await interaction.response.send_message("⚠️ No tienes ningún turno abierto.", ephemeral=True)
        
        inicio = res[1]
        ahora = datetime.datetime.now(datetime.timezone.utc)
        duracion_seg = (ahora - inicio.replace(tzinfo=datetime.timezone.utc)).total_seconds()
        
        # Limitar la duración manual a 3 horas máximo (10800 segundos) por si se buguea
        if duracion_seg > 10800:
            duracion_seg = 10800
        
        horas_decimal = duracion_seg / 3600.0
        
        # Actualizar base de datos
        cursor.execute("""
            UPDATE turnos_oficiales 
            SET turno_activo = FALSE, 
                inicio_turno = NULL, 
                turnos_semana = turnos_semana + 1,
                horas_semana = horas_semana + %s
            WHERE user_id = %s
        """, (horas_decimal, interaction.user.id))
        
        h = int(duracion_seg // 3600)
        m = int((duracion_seg % 3600) // 60)
        
        # Anuncio de salida
        canal_turnos_id = obtener_config_int(interaction.guild.id, "CANAL_TURNOS_ID", CANAL_TURNOS_ID)
        canal = interaction.guild.get_channel(canal_turnos_id)
        if canal:
            embed = discord.Embed(
                title="🔴 FIN DE SERVICIO", 
                description=f"{interaction.user.mention} ha salido de servicio.\n⏱️ **Duración de la patrulla:** {h}h {m}m", 
                color=discord.Color.red(), 
                timestamp=discord.utils.utcnow()
            )
            await canal.send(embed=embed)
        
        await interaction.response.send_message(f"✅ **Turno cerrado.** Se han sumado **{h}h {m}m** a tu reporte semanal.", ephemeral=True)

    @discord.ui.button(label="Mis Turnos Semanales", style=discord.ButtonStyle.secondary, emoji="📊", custom_id="btn_mis_turnos_v1")
    async def btn_mis_turnos(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor.execute("SELECT turnos_semana, horas_semana, turno_activo, inicio_turno FROM turnos_oficiales WHERE user_id = %s", (interaction.user.id,))
        res = cursor.fetchone()
        
        if not res:
            return await interaction.response.send_message("📭 Aún no tienes registros de servicio en el sistema.", ephemeral=True)
        
        turnos_semana, horas_semana, activo, inicio = res
        h = int(horas_semana)
        m = int((horas_semana - h) * 60)
        
        embed = discord.Embed(title="📊 Tus Estadísticas Semanales", color=discord.Color.blue())
        embed.add_field(name="📋 Turnos Completados", value=f"**{turnos_semana}** patrullas", inline=True)
        embed.add_field(name="⏱️ Horas Acumuladas", value=f"**{h}h {m}m**", inline=True)
        
        if activo and inicio:
            minutos_activos = int((datetime.datetime.now(datetime.timezone.utc) - inicio.replace(tzinfo=datetime.timezone.utc)).total_seconds() / 60)
            embed.add_field(name="🟢 Estado Actual", value=f"En servicio desde hace **{minutos_activos} min**.", inline=False)
        
        embed.set_footer(text="Las estadísticas se reinician el domingo a las 21:00 Arg.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- NUEVO BOTÓN: TOP SEMANAL ---
    @discord.ui.button(label="Top Semanal", style=discord.ButtonStyle.primary, emoji="🏆", custom_id="btn_top_turnos_v1")
    async def btn_top_turnos(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Obtenemos a los que tengan más de 0 horas ordenados de mayor a menor
        cursor.execute("SELECT user_id, turnos_semana, horas_semana FROM turnos_oficiales WHERE horas_semana > 0 OR turnos_semana > 0 ORDER BY horas_semana DESC LIMIT 15")
        resultados = cursor.fetchall()
        
        if not resultados:
            return await interaction.response.send_message("📭 Todavía no hay registros de servicio esta semana.", ephemeral=True)
            
        embed = discord.Embed(
            title="🏆 TOP SEMANAL DE SERVICIO", 
            description="Los oficiales con más horas de patrulla esta semana:\n\n",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        
        desc = ""
        medallas = {1: "🥇", 2: "🥈", 3: "🥉"}
        for i, (uid, turnos, horas) in enumerate(resultados, start=1):
            medalla = medallas.get(i, "🎖️")
            h = int(horas)
            m = int((horas - h) * 60)
            desc += f"{medalla} <@{uid}> — **{h}h {m}m** en `{turnos}` turnos\n"
            
        embed.description += desc
        embed.set_footer(text="Se reinicia automáticamente los domingos a las 21:00 Arg.")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


# --- COG PRINCIPAL Y TAREAS ---
class PanelTurnos(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_load(self):
        self.bot.add_view(ViewPanelTurnos())
        self.loop_turnos.start()
        self.reset_semanal_turnos.start()

    def cog_unload(self):
        self.loop_turnos.cancel()
        self.reset_semanal_turnos.cancel()

    @app_commands.command(name="panelturnos", description="Despliega el panel de Fichaje de Turnos PFA.")
    async def panelturnos(self, interaction: discord.Interaction):
        rol_admin_id = obtener_config_int(interaction.guild.id, "ROL_PANEL_ADMIN_ID", ROL_PANEL_ADMIN_ID)
        if not any(r.id == rol_admin_id for r in interaction.user.roles):
            return await interaction.response.send_message("⛔ No tienes permiso para desplegar este panel.", ephemeral=True)
        
        embed = discord.Embed(
            title="👮 SISTEMA DE SERVICIO - TURNOS PFA",
            description=(
                "Ficha tu entrada y salida de servicio utilizando este panel.\n\n"
                "🟢 **Abrir Turno:** Inicia tu horario de servicio. (Se cierra automáticamente a las 3 horas).\n"
                "🔴 **Cerrar Turno:** Finaliza tu patrulla y guarda las horas trabajadas.\n"
                "📊 **Mis Turnos:** Consulta la cantidad de patrullas y horas de tu semana.\n"
                "🏆 **Top Semanal:** Descubre qué oficiales tienen más horas acumuladas.\n\n"
                "⚠️ *Recordatorio: Las estadísticas y horas se reinician a 0 todos los domingos a las 21:00 Arg.*"
            ),
            color=discord.Color.dark_blue()
        )
        embed.set_footer(text="Registro Operativo - PFA")
        await interaction.channel.send(embed=embed, view=ViewPanelTurnos())
        await interaction.response.send_message("✅ Panel desplegado.", ephemeral=True)

    # LOOP 1: Autocierre de Turnos y Verificación AFK
    @tasks.loop(minutes=2)
    async def loop_turnos(self):
        ahora = datetime.datetime.now(datetime.timezone.utc)
        cursor.execute("SELECT user_id, inicio_turno FROM turnos_oficiales WHERE turno_activo = TRUE")
        activos = cursor.fetchall()
        
        for (uid, inicio) in activos:
            inicio = inicio.replace(tzinfo=datetime.timezone.utc)
            minutos = (ahora - inicio).total_seconds() / 60

            # Buscar en qué servidor está el oficial, para resolver SU canal de turnos configurado
            guild = None
            miembro = None
            for g in self.bot.guilds:
                m = g.get_member(uid)
                if m:
                    guild, miembro = g, m
                    break

            canal_turnos_id = obtener_config_int(guild.id, "CANAL_TURNOS_ID", CANAL_TURNOS_ID) if guild else CANAL_TURNOS_ID
            canal = guild.get_channel(canal_turnos_id) if guild else self.bot.get_channel(canal_turnos_id)

            # 1. Autocierre 3 horas
            if minutos >= 180:
                cursor.execute("""
                    UPDATE turnos_oficiales
                    SET turno_activo = FALSE, inicio_turno = NULL,
                        turnos_semana = turnos_semana + 1, horas_semana = horas_semana + 3.0
                    WHERE user_id = %s
                """, (uid,))
                if canal: await canal.send(f"🔴 <@{uid}> ha cumplido su límite máximo de 3 horas. Turno cerrado automáticamente.")
                continue

            # 2. Verificación AFK (Cada 30 mins)
            if 30 <= minutos <= 32 or 60 <= minutos <= 62 or 90 <= minutos <= 92 or 120 <= minutos <= 122 or 150 <= minutos <= 152:
                if miembro:
                    view = ViewConfirmacionAFK(uid)
                    try:
                        await miembro.send("🛡️ **Verificación de Seguridad:** ¿Sigues en servicio? Tienes 2 minutos para confirmar.", view=view)
                        await view.wait()
                        if not view.respondido:
                            cursor.execute("UPDATE turnos_oficiales SET turno_activo = FALSE, inicio_turno = NULL WHERE user_id = %s", (uid,))
                            if canal: await canal.send(f"🔴 <@{uid}> ha sido expulsado de servicio por AFK.")
                    except: pass
        conn.commit()

    @loop_turnos.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

    # LOOP 2: Reseteo semanal
    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=datetime.timezone.utc))
    async def reset_semanal_turnos(self):
        if datetime.datetime.now(datetime.timezone.utc).weekday() == 0:
            cursor.execute("UPDATE turnos_oficiales SET turnos_semana = 0, horas_semana = 0.0")
            conn.commit()

async def setup(bot):
    await bot.add_cog(PanelTurnos(bot))