import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import datetime
import hashlib
from utils.core import cursor, conn, actualizar_coins, enviar_log

from utils.config import obtener_config_int, obtener_config_list

def obtener_roles_division(guild_id: int, division: str) -> list[int]:
    if division == "URA":
        return obtener_config_list(guild_id, "ROLE_SUB_URA", [1390022409381216388, 1351228669359558809])
    elif division == "Halcon":
        return obtener_config_list(guild_id, "ROLE_SUB_HALCON", [1441595283808063610, 1351228669359558809])
    elif division == "PDI":
        return obtener_config_list(guild_id, "ROLE_SUB_PDI", [1519516475688357958, 1351228669359558809])
    return []

def _es_staff_operativo(i: discord.Interaction) -> bool:
    if i.user.id == i.guild.owner_id or i.user.guild_permissions.administrator:
        return True
    roles_staff = obtener_config_list(i.guild.id, "ROLES_PARA_ADMIN_STAFF", [1351228669359558809, 1390055851657789481, 1411483502142029866])
    return any(r.id in roles_staff for r in i.user.roles)

METAS_MISIONES = {
    "Hacer 120 actividades en una semana": 120, "Acudir a 80 Robos en Moto": 80, "Acudir a 20 Robos en Helicoptero": 20,
    "Acudir a 7 Fleecas en un día": 7, "Hacer 20 actividades en un día": 20, "Acudir a 15 Banco Central/Humane": 15,
    "Procesar 10 personas en una semana": 10, "Procesar 3 personas en un día": 3,
}

MISIONES_POR_DIVISION = {
    "URA": ["Hacer 120 actividades en una semana", "Acudir a 80 Robos en Moto", "Acudir a 20 Robos en Helicoptero"],
    "URA_DIARIA": ["Hacer 20 actividades en un día"],
    "Halcon": ["Acudir a 15 Banco Central/Humane"],
    "Halcon_DIARIA": ["Acudir a 7 Fleecas en un día"],
    "PDI": ["Procesar 10 personas en una semana"],
    "PDI_DIARIA": ["Procesar 3 personas en un día"],
}

class SelectMision(discord.ui.Select):
    def __init__(self, division_key, es_diaria=False):
        self.es_diaria = es_diaria
        clave = f"{division_key}_DIARIA" if es_diaria else division_key
        misiones = MISIONES_POR_DIVISION.get(clave, [])
        options = [discord.SelectOption(label=m, value=m) for m in misiones]
        super().__init__(placeholder="📅 Misiones DIARIAS..." if es_diaria else "⚠️ Misiones SEMANALES...", options=options, custom_id=f"select_{'diaria' if es_diaria else 'semanal'}_{division_key}_v10")

    async def callback(self, interaction: discord.Interaction):
        for item in self.view.children:
            if isinstance(item, SelectMision):
                for opt in item.options: opt.default = False
        for option in self.options:
            if option.value == self.values[0]: option.default = True
        await interaction.response.edit_message(view=self.view)

class ViewMisiones(discord.ui.View):
    def __init__(self, division_key="DESCONOCIDO"):
        super().__init__(timeout=None)
        self.division_key = division_key
        self.add_item(SelectMision(division_key, es_diaria=False))
        self.add_item(SelectMision(division_key, es_diaria=True))

    @discord.ui.button(label="Empezar Misión", style=discord.ButtonStyle.success, custom_id="btn_mision_start_v13")
    async def empezar(self, interaction: discord.Interaction, button: discord.ui.Button):
        roles_div = obtener_roles_division(interaction.guild.id, self.division_key)
        if self.division_key != "DESCONOCIDO" and not any(rol.id in roles_div for rol in interaction.user.roles):
            return await interaction.response.send_message(f"⛔ No perteneces a **{self.division_key}**.", ephemeral=True)

        select_diaria = next((x for x in self.children if isinstance(x, SelectMision) and x.es_diaria), None)
        select_semanal = next((x for x in self.children if isinstance(x, SelectMision) and not x.es_diaria), None)
        
        m_nombre, es_diaria = None, False
        if select_diaria:
            for opt in select_diaria.options:
                if opt.default: m_nombre, es_diaria = opt.value, True
        if not m_nombre and select_semanal:
            for opt in select_semanal.options:
                if opt.default: m_nombre, es_diaria = opt.value, False

        if not m_nombre: return await interaction.response.send_message("⚠️ Selecciona una misión.", ephemeral=True)

        if es_diaria:
            fecha_hoy = discord.utils.utcnow().strftime("%Y-%m-%d")
            cursor.execute("SELECT 1 FROM misiones_diarias_completadas WHERE user_id = %s AND fecha = %s", (interaction.user.id, fecha_hoy))
            if cursor.fetchone(): return await interaction.response.send_message("🚫 Ya hiciste la diaria de hoy.", ephemeral=True)
            cursor.execute("SELECT 1 FROM misiones_diarias_activas WHERE user_id = %s", (interaction.user.id,))
            if cursor.fetchone(): return await interaction.response.send_message("❌ Ya tienes una diaria en curso.", ephemeral=True)
            cursor.execute("INSERT INTO misiones_diarias_activas (user_id, mision_nombre, division, progreso) VALUES (%s, %s, %s, 0)", (interaction.user.id, m_nombre, self.division_key))
        else:
            cursor.execute("SELECT 1 FROM misiones_activas WHERE user_id = %s", (interaction.user.id,))
            if cursor.fetchone(): return await interaction.response.send_message("❌ Ya tienes una semanal en curso.", ephemeral=True)
            cursor.execute("SELECT 1 FROM misiones_completadas WHERE user_id = %s", (interaction.user.id,))
            if cursor.fetchone(): return await interaction.response.send_message("🚫 Ya completaste la semanal.", ephemeral=True)
            cursor.execute("INSERT INTO misiones_activas (user_id, mision_nombre, division, progreso) VALUES (%s, %s, %s, 0)", (interaction.user.id, m_nombre, self.division_key))

        conn.commit()
        await interaction.response.send_message(f"🚀 **OPERATIVO INICIADO**: {m_nombre}", ephemeral=True)
    
    @discord.ui.button(label="Tarea Finalizada", style=discord.ButtonStyle.danger, custom_id="btn_mision_finish_v15")
    async def finalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor.execute("SELECT mision_nombre, progreso FROM misiones_activas WHERE user_id = %s", (interaction.user.id,))
        semanal = cursor.fetchone()
        cursor.execute("SELECT mision_nombre, progreso FROM misiones_diarias_activas WHERE user_id = %s", (interaction.user.id,))
        diaria = cursor.fetchone()

        if not semanal and not diaria: return await interaction.response.send_message("❌ Sin misiones.", ephemeral=True)

        mensajes, total_recompensa = [], 0.0
        hoy_str = discord.utils.utcnow().date().strftime("%Y-%m-%d")
        embed = discord.Embed(title="📊 ESTADO DE TUS OPERATIVOS", color=discord.Color.blue())

        if semanal:
            n_s, p_s = semanal
            m_s = METAS_MISIONES.get(n_s, 20)
            if p_s >= m_s:
                total_recompensa += 5.00
                cursor.execute("INSERT INTO misiones_completadas (user_id, mision_nombre, fecha) VALUES (%s, %s, %s)", (interaction.user.id, n_s, discord.utils.utcnow().strftime("%Y-%m-%d %H:%M")))
                cursor.execute("DELETE FROM misiones_activas WHERE user_id = %s", (interaction.user.id,))
                cursor.execute("UPDATE competencia_subdivisiones SET puntos = puntos + 1 WHERE division = %s", (self.division_key,))
                if self.division_key == "URA":
                    cursor.execute("INSERT INTO ura_top_misiones (user_id, misiones) VALUES (%s, 1) ON CONFLICT (user_id) DO UPDATE SET misiones = ura_top_misiones.misiones + 1", (interaction.user.id,))
                embed.add_field(name="📅 Semanal: COMPLETADA", value=f"✅ **{n_s}** (+5.00)", inline=False)
                mensajes.append(f"semanal {n_s}")
            else: embed.add_field(name="📅 Semanal: EN CURSO", value=f"⏳ `{n_s}`\nProgreso: **{p_s}/{m_s}**", inline=False)

        if diaria:
            n_d, p_d = diaria
            m_d = METAS_MISIONES.get(n_d, 1)
            if p_d >= m_d:
                recompensa_d, msg_racha = 1.50, ""
                ayer = (discord.utils.utcnow().date() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                cursor.execute("SELECT contador, ultima_fecha FROM rachas_diarias WHERE user_id = %s", (interaction.user.id,))
                r_data = cursor.fetchone()
                n_r = 1
                if r_data:
                    c, u_f = r_data
                    if u_f == ayer: n_r = c + 1
                    elif u_f == hoy_str: n_r = c
                
                if n_r >= 7: recompensa_d += 0.50; n_r = 0; msg_racha = " 🔥 **¡BONO RACHA!**"
                total_recompensa += recompensa_d
                cursor.execute("INSERT INTO rachas_diarias (user_id, contador, ultima_fecha) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET contador = EXCLUDED.contador, ultima_fecha = EXCLUDED.ultima_fecha", (interaction.user.id, n_r, hoy_str))
                cursor.execute("INSERT INTO misiones_diarias_completadas (user_id, fecha) VALUES (%s, %s)", (interaction.user.id, hoy_str))
                cursor.execute("DELETE FROM misiones_diarias_activas WHERE user_id = %s", (interaction.user.id,))
                cursor.execute("UPDATE competencia_subdivisiones SET puntos = puntos + 1 WHERE division = %s", (self.division_key,))
                if self.division_key == "URA":
                    cursor.execute("INSERT INTO ura_top_misiones (user_id, misiones) VALUES (%s, 1) ON CONFLICT (user_id) DO UPDATE SET misiones = ura_top_misiones.misiones + 1", (interaction.user.id,))
                embed.add_field(name="☀️ Diaria: COMPLETADA", value=f"✅ **{n_d}** (+{recompensa_d:.2f}){msg_racha}", inline=False)
                mensajes.append(f"diaria {n_d}")
            else: embed.add_field(name="☀️ Diaria: EN CURSO", value=f"⏳ `{n_d}`\nProgreso: **{p_d}/{m_d}**", inline=False)

        if total_recompensa > 0:
            conn.commit()
            actualizar_coins(interaction.user.id, total_recompensa)
            await enviar_log(interaction.client, interaction.user, interaction.user.id, total_recompensa, "misiones_auto", f"Cobro: {', '.join(mensajes)}")
            embed.color = discord.Color.gold()
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ModalPruebas(discord.ui.Modal, title="📸 REGISTRO POR ID"):
    num = discord.ui.TextInput(label="Nº Prueba", max_length=4)
    id_msg = discord.ui.TextInput(label="ID del Mensaje", min_length=17, max_length=21, required=True)

    def __init__(self, m_nombre, p_actual, meta, div_key, tabla):
        super().__init__()
        self.m_nombre, self.meta, self.div_key, self.tabla = m_nombre, meta, div_key, tabla

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        canal_key = f"CANAL_ACT_{self.div_key.upper()}"
        default_channel_id = {"URA": 1474430423894331454, "HALCON": 1474430233351553054, "PDI": 1521300697423941632}.get(self.div_key.upper(), 0)
        c_act_id = obtener_config_int(guild_id, canal_key, default_channel_id)
        c_act = interaction.client.get_channel(c_act_id)
        if not c_act: return await interaction.response.send_message("❌ Canal de subida de pruebas no configurado en el servidor.", ephemeral=True)
        try: msg = await c_act.fetch_message(int(self.id_msg.value))
        except: return await interaction.response.send_message("❌ ID de Mensaje No Encontrado en el canal de la subdivisión.", ephemeral=True)
        if not msg.attachments or msg.author.id != interaction.user.id: return await interaction.response.send_message("❌ Error de foto o autor.", ephemeral=True)

        cursor.execute(f"SELECT progreso FROM {self.tabla} WHERE user_id = %s", (interaction.user.id,))
        res = cursor.fetchone()
        if not res: return await interaction.response.send_message("❌ No hay misión activa.", ephemeral=True)
        
        n_prog = res[0] + 1
        cursor.execute(f"UPDATE {self.tabla} SET progreso = %s WHERE user_id = %s", (n_prog, interaction.user.id))
        conn.commit()

        embed_log = discord.Embed(title=f"📸 PRUEBA - {self.div_key}", color=discord.Color.blue())
        embed_log.add_field(name="Oficial", value=interaction.user.mention)
        embed_log.add_field(name="Progreso", value=f"{n_prog}/{self.meta}")
        embed_log.set_image(url=msg.attachments[0].url)
        
        c_log_id = obtener_config_int(guild_id, "CANAL_LOGS_ID", 1474174294803222528)
        c_log = interaction.client.get_channel(c_log_id)
        if c_log: await c_log.send(embed=embed_log)

        await interaction.response.send_message(f"✅ Registrado. Progreso: **{n_prog}/{self.meta}**.", ephemeral=True)

class ViewPruebas(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Subir Prueba Semanal", style=discord.ButtonStyle.primary, custom_id="btn_pruebas_semanal_v1")
    async def s_semanal(self, i: discord.Interaction, b: discord.ui.Button):
        cursor.execute("SELECT mision_nombre, progreso, division FROM misiones_activas WHERE user_id = %s", (i.user.id,))
        res = cursor.fetchone()
        if not res: return await i.response.send_message("❌ Sin misión.", ephemeral=True)
        await i.response.send_modal(ModalPruebas(res[0], res[1], METAS_MISIONES.get(res[0], 15), res[2], "misiones_activas"))
    @discord.ui.button(label="Subir Prueba Diaria", style=discord.ButtonStyle.success, custom_id="btn_pruebas_diaria_v1")
    async def s_diaria(self, i: discord.Interaction, b: discord.ui.Button):
        cursor.execute("SELECT mision_nombre, progreso, division FROM misiones_diarias_activas WHERE user_id = %s", (i.user.id,))
        res = cursor.fetchone()
        if not res: return await i.response.send_message("❌ Sin misión.", ephemeral=True)
        await i.response.send_modal(ModalPruebas(res[0], res[1], METAS_MISIONES.get(res[0], 1), res[2], "misiones_diarias_activas"))

class ModalRobos(discord.ui.Modal, title="🚨 ROBO ACUDIDO"):
    id_msg = discord.ui.TextInput(label="ID del Mensaje", min_length=17, max_length=21, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        m_id = self.id_msg.value.strip()
        cursor.execute("SELECT 1 FROM evidencias_usadas WHERE msg_id = %s", (m_id,))
        if cursor.fetchone(): return await interaction.response.send_message("❌ Ya cobrado.", ephemeral=True)
        
        canal_prueba_robos_id = obtener_config_int(interaction.guild.id, "CANAL_PRUEBA_ROBOS_ID", 1508933644943884389)
        c_robos = interaction.client.get_channel(canal_prueba_robos_id)
        try: msg = await c_robos.fetch_message(int(m_id))
        except: return await interaction.response.send_message("❌ ID No Encontrado.", ephemeral=True)
        if not msg.attachments or msg.author.id != interaction.user.id: return await interaction.response.send_message("❌ Error de foto o autor.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        hsh = hashlib.md5(await msg.attachments[0].read()).hexdigest()
        cursor.execute("SELECT msg_id FROM evidencias_usadas WHERE image_hash = %s", (hsh,))
        if cursor.fetchone(): return await interaction.followup.send("❌ Foto duplicada.", ephemeral=True)

        cursor.execute("INSERT INTO evidencias_usadas (msg_id, user_id, tipo, image_hash) VALUES (%s, %s, %s, %s)", (m_id, interaction.user.id, "robo", hsh))
        cursor.execute("INSERT INTO robos_acudidos (user_id, total_robos) VALUES (%s, 1) ON CONFLICT(user_id) DO UPDATE SET total_robos = robos_acudidos.total_robos + 1", (interaction.user.id,))
        conn.commit()

        actualizar_coins(interaction.user.id, 0.04)
        await enviar_log(interaction.client, interaction.user, interaction.user.id, 0.04, "misiones_auto", f"Robo ID: {m_id}")
        await interaction.followup.send("✅ Robo registrado. +0.04 coins.", ephemeral=True)

class ViewPanelRobos(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Subir Prueba Robo", style=discord.ButtonStyle.primary, custom_id="btn_subir_robo", emoji="🚓")
    async def btn_s(self, i: discord.Interaction, b: discord.ui.Button):
        roles_permitidos_robos = obtener_config_list(i.guild.id, "ROLES_PERMITIDOS_ROBOS", [1393678701408817284, 1351228669359558809])
        if not any(r.id in roles_permitidos_robos for r in i.user.roles): return await i.response.send_message("⛔ Acceso Denegado.", ephemeral=True)
        await i.response.send_modal(ModalRobos())
    @discord.ui.button(label="Top Robos Acudidos", style=discord.ButtonStyle.secondary, custom_id="btn_top_robos", emoji="🏆")
    async def btn_t(self, i: discord.Interaction, b: discord.ui.Button):
        cursor.execute("SELECT user_id, total_robos FROM robos_acudidos ORDER BY total_robos DESC LIMIT 10")
        res = cursor.fetchall()
        embed = discord.Embed(title="🏆 TOP ROBOS", description="\\n".join([f"• <@{u}>: {t} robos" for u, t in res]), color=discord.Color.dark_red())
        await i.response.send_message(embed=embed, ephemeral=True)

class PanelOperativo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_load(self):
        for key in ("URA", "Halcon", "PDI"): self.bot.add_view(ViewMisiones(division_key=key))
        self.bot.add_view(ViewPruebas())
        self.bot.add_view(ViewPanelRobos())
        self.reset_semanal_misiones.start()
        self.reinicio_diario_sistema.start()

    def cog_unload(self):
        self.reset_semanal_misiones.cancel()
        self.reinicio_diario_sistema.cancel()

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingAnyRole): await interaction.response.send_message("⛔ Rango necesario.", ephemeral=True)

    @app_commands.command(name="panelura")
    async def panelura(self, i: discord.Interaction):
        if not _es_staff_operativo(i): return await i.response.send_message("⛔ Rango necesario.", ephemeral=True)
        await i.channel.send(embed=discord.Embed(title="🚔 U.R.A", color=discord.Color.blue()), view=ViewMisiones("URA"))
        await i.response.send_message("✅", ephemeral=True)

    @app_commands.command(name="panelhalcon")
    async def panelhalcon(self, i: discord.Interaction):
        if not _es_staff_operativo(i): return await i.response.send_message("⛔ Rango necesario.", ephemeral=True)
        await i.channel.send(embed=discord.Embed(title="🦅 HALCÓN", color=discord.Color.red()), view=ViewMisiones("Halcon"))
        await i.response.send_message("✅", ephemeral=True)

    @app_commands.command(name="panelpdi")
    async def panelpdi(self, i: discord.Interaction):
        if not _es_staff_operativo(i): return await i.response.send_message("⛔ Rango necesario.", ephemeral=True)
        await i.channel.send(embed=discord.Embed(title="🕵️ P.D.I", color=discord.Color.dark_grey()), view=ViewMisiones("PDI"))
        await i.response.send_message("✅", ephemeral=True)

    @app_commands.command(name="panelpruebas")
    async def panelpruebas(self, i: discord.Interaction):
        if not _es_staff_operativo(i): return await i.response.send_message("⛔ Rango necesario.", ephemeral=True)
        await i.channel.send(embed=discord.Embed(title="📸 PRUEBAS", color=discord.Color.gold()), view=ViewPruebas())
        await i.response.send_message("✅", ephemeral=True)

    @app_commands.command(name="panelrobos")
    async def panelrobos(self, i: discord.Interaction):
        if not _es_staff_operativo(i): return await i.response.send_message("⛔ Rango necesario.", ephemeral=True)
        await i.channel.send(embed=discord.Embed(title="🚓 REGISTRO ROBOS", color=discord.Color.dark_red()), view=ViewPanelRobos())
        await i.response.send_message("✅", ephemeral=True)

    @app_commands.command(name="reset_misiones_semanal")
    async def reset_misiones_semanal_manual(self, i: discord.Interaction):
        if not _es_staff_operativo(i): return await i.response.send_message("⛔ Rango necesario.", ephemeral=True)
        cursor.execute("DELETE FROM misiones_completadas"); cursor.execute("DELETE FROM misiones_activas"); conn.commit()
        await i.response.send_message(embed=discord.Embed(title="🔄 REINICIO SEMANAL DE OPERATIVOS", color=discord.Color.blue())) 

    @app_commands.command(name="reset_total_usuario")
    async def reset_total_usuario(self, i: discord.Interaction, usuario: discord.Member):
        if not _es_staff_operativo(i): return await i.response.send_message("⛔ Rango necesario.", ephemeral=True)
        cursor.execute("DELETE FROM misiones_activas WHERE user_id = %s", (usuario.id,))
        cursor.execute("DELETE FROM misiones_completadas WHERE user_id = %s", (usuario.id,))
        conn.commit()
        await enviar_log(self.bot, i.user, usuario.id, 0, "reset_mision", "Reset total")
        await i.response.send_message(f"✅ Reset a {usuario.mention}.", ephemeral=True)  

    @app_commands.command(name="limpiar_diarias_ahora")
    async def limpiar_diarias_ahora(self, i: discord.Interaction):
        if not _es_staff_operativo(i): return await i.response.send_message("⛔ Rango necesario.", ephemeral=True)
        ayer = (discord.utils.utcnow() - datetime.timedelta(days=1)).date().strftime("%Y-%m-%d")
        cursor.execute("UPDATE rachas_diarias SET contador = 0 WHERE ultima_fecha != %s", (ayer,))
        cursor.execute("DELETE FROM misiones_diarias_activas")
        conn.commit()
        await i.response.send_message("✅ Diarias limpiadas.", ephemeral=True)

    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=datetime.timezone.utc))
    async def reset_semanal_misiones(self):
        if discord.utils.utcnow().weekday() != 0: return
        try:
            for guild in self.bot.guilds:
                cursor.execute("SELECT division, puntos FROM competencia_subdivisiones")
                res = cursor.fetchall()
                max_p = max([r[1] for r in res]) if res else 0
                if max_p > 0 and [r[1] for r in res].count(max_p) == 1:
                    div = next(r[0] for r in res if r[1] == max_p)
                    roles_div = obtener_roles_division(guild.id, div)
                    for m in guild.members:
                        if any(r.id in roles_div for r in m.roles):
                            actualizar_coins(m.id, 0.20)
                
                canal_general_id = obtener_config_int(guild.id, "CANAL_GENERAL_ID", 1351225457864867963)
                c = guild.get_channel(canal_general_id)
                if c:
                    await c.send(embed=discord.Embed(title="🔄 ¡NUEVA SEMANA OPERATIVA!", color=discord.Color.blue()))
                    
            cursor.execute("UPDATE competencia_subdivisiones SET puntos = 0")
            cursor.execute("DELETE FROM misiones_completadas")
            cursor.execute("DELETE FROM misiones_activas")
            conn.commit()
        except:
            pass

    @tasks.loop(time=datetime.time(hour=1, minute=0, tzinfo=datetime.timezone.utc)) 
    async def reinicio_diario_sistema(self):
        try:
            ayer = (discord.utils.utcnow() - datetime.timedelta(days=1)).date().strftime("%Y-%m-%d")
            cursor.execute("UPDATE rachas_diarias SET contador = 0 WHERE ultima_fecha != %s", (ayer,))
            cursor.execute("DELETE FROM misiones_diarias_activas")
            conn.commit()
        except: pass

async def setup(bot):
    await bot.add_cog(PanelOperativo(bot))