import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import datetime
from utils.core import cursor, conn
from utils.config import obtener_config_int, obtener_config_list

CANAL_BAJAS_ID = 1478857758756573354 
ROL_BAJA_ID = 1351240431882600530    
ROLES_PERMITIDOS_BAJA = [1393678701408817284] 
CANAL_REGISTRO_BAJAS_ID = 1364055828155465729 

CANAL_AUSENCIAS_ID = 1478878806885400628 
ROL_AUSENTE_ID = 1464030189066653963     
ROLES_PERMITIDOS_AUSENCIA = [1393678701408817284] 
ROLES_APROBAR_AUSENCIAS = [1461995989446557777, 1351228669359558809, 1390055851657789481, 1411483502142029866]
ROLES_PARA_ADMIN_STAFF = [1351228669359558809, 1390055851657789481, 1411483502142029866]

class ModalBaja(discord.ui.Modal, title="Formulario de Baja Voluntaria"):
    rango = discord.ui.TextInput(label="Rango Actual", placeholder="Ej: Oficial I", required=True)
    motivo = discord.ui.TextInput(label="Motivo de la Baja", style=discord.TextStyle.paragraph, placeholder="Explica brevemente por qué solicitas la baja...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        canal_bajas_id = obtener_config_int(interaction.guild.id, "CANAL_BAJAS_ID", CANAL_BAJAS_ID)
        canal_bajas = interaction.guild.get_channel(canal_bajas_id)
        embed_log = discord.Embed(title="🚨 NUEVA SOLICITUD DE BAJA", color=discord.Color.red(), timestamp=discord.utils.utcnow())
        embed_log.add_field(name="👤 Identidad del Oficial", value=f"{interaction.user.mention}\n**ID:** `{interaction.user.id}`\n**Usuario:** `{interaction.user.display_name}`", inline=False)
        embed_log.add_field(name="🎖️ Rango", value=self.rango.value, inline=True)
        embed_log.add_field(name="📝 Motivo", value=self.motivo.value, inline=False)
        embed_log.set_thumbnail(url=interaction.user.display_avatar.url)
        if canal_bajas: await canal_bajas.send(embed=embed_log)

        canal_registro_id = obtener_config_int(interaction.guild.id, "CANAL_REGISTRO_BAJAS_ID", CANAL_REGISTRO_BAJAS_ID)
        canal_registro = interaction.guild.get_channel(canal_registro_id)
        if canal_registro: await canal_registro.send(f"{interaction.user.mention} > Expulsado > Baja.")

        try:
            rol_baja_id = obtener_config_int(interaction.guild.id, "ROL_BAJA_ID", ROL_BAJA_ID)
            nuevo_rol = interaction.guild.get_role(rol_baja_id)
            if nuevo_rol:
                await interaction.user.edit(roles=[nuevo_rol])
                await interaction.response.send_message("✅ Tu solicitud ha sido procesada. Se te han retirado los roles policiales.", ephemeral=True)
            else: await interaction.response.send_message("✅ Formulario enviado.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("✅ Formulario enviado al Staff.", ephemeral=True)

class ViewPanelBaja(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Solicitar Baja", style=discord.ButtonStyle.danger, emoji="🚪", custom_id="btn_solicitar_baja_v1")
    async def btn_baja(self, interaction: discord.Interaction, button: discord.ui.Button):
        roles_permitidos_baja = obtener_config_list(interaction.guild.id, "ROLES_PERMITIDOS_BAJA", ROLES_PERMITIDOS_BAJA)
        roles_staff = obtener_config_list(interaction.guild.id, "ROLES_PARA_ADMIN_STAFF", ROLES_PARA_ADMIN_STAFF)
        tiene_rol = any(rol.id in roles_permitidos_baja for rol in interaction.user.roles)
        es_staff = any(rol.id in roles_staff for rol in interaction.user.roles)
        if not tiene_rol and not es_staff:
            return await interaction.response.send_message("⛔ **Acceso Denegado.**", ephemeral=True)
        await interaction.response.send_modal(ModalBaja())

class ModalAusencia(discord.ui.Modal):
    def __init__(self, dias_restantes: int = 14):
        super().__init__(title="Solicitud de Ausencia")
        self.dias_restantes = dias_restantes
        self.dias_input = discord.ui.TextInput(label=f"Días a solicitar (Te quedan {dias_restantes})", max_length=2, required=True)
        self.motivo_input = discord.ui.TextInput(label="Motivo de la ausencia", style=discord.TextStyle.paragraph, required=True)
        self.add_item(self.dias_input)
        self.add_item(self.motivo_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            dias_int = int(self.dias_input.value)
            if dias_int < 1 or dias_int > self.dias_restantes: raise ValueError
        except ValueError:
            return await interaction.response.send_message(f"❌ Error: Debes ingresar un número válido entre 1 y {self.dias_restantes}.", ephemeral=True)

        ahora = discord.utils.utcnow()
        fecha_fin = ahora + datetime.timedelta(days=dias_int)
        timestamp_fin = int(fecha_fin.timestamp())

        canal_ausencias_id = obtener_config_int(interaction.guild.id, "CANAL_AUSENCIAS_ID", CANAL_AUSENCIAS_ID)
        canal_rrhh = interaction.guild.get_channel(canal_ausencias_id)
        embed_log = discord.Embed(title="⏳ SOLICITUD DE LICENCIA PENDIENTE", color=discord.Color.orange(), timestamp=ahora)
        embed_log.add_field(name="Oficial", value=f"{interaction.user.mention}", inline=True)
        embed_log.add_field(name="Duración Solicitada", value=f"**{dias_int} días**\n*(Hasta el <t:{timestamp_fin}:d>)*", inline=True)
        embed_log.add_field(name="Motivo", value=self.motivo_input.value, inline=False)
        embed_log.set_thumbnail(url=interaction.user.display_avatar.url)
        embed_log.set_footer(text=f"ID:{interaction.user.id}|FIN:{timestamp_fin}|DIAS:{dias_int}")
        if canal_rrhh: await canal_rrhh.send(embed=embed_log, view=ViewAprobarAusencia())

        mes_actual = ahora.strftime("%Y-%m")
        cursor.execute("SELECT 1 FROM registro_pedidos_ausencia WHERE user_id = %s", (interaction.user.id,))
        if cursor.fetchone():
            cursor.execute("""
                UPDATE registro_pedidos_ausencia SET 
                    conteo_mes = CASE WHEN ultima_fecha = %s THEN COALESCE(conteo_mes, 0) + 1 ELSE 1 END,
                    dias_usados_mes = CASE WHEN ultima_fecha = %s THEN COALESCE(dias_usados_mes, 0) + %s ELSE %s END,
                    ultima_fecha = %s WHERE user_id = %s
            """, (mes_actual, mes_actual, dias_int, dias_int, mes_actual, interaction.user.id))
        else:
            cursor.execute("INSERT INTO registro_pedidos_ausencia (user_id, ultima_fecha, conteo_mes, dias_usados_mes) VALUES (%s, %s, 1, %s)", (interaction.user.id, mes_actual, dias_int))
        conn.commit()

        await interaction.response.send_message(f"✅ Tu solicitud de licencia por **{dias_int} días** ha sido enviada.", ephemeral=True)

class ModalRechazoAusencia(discord.ui.Modal):
    motivo = discord.ui.TextInput(
        label="Motivo del Rechazo",
        style=discord.TextStyle.paragraph,
        placeholder="Escribe la razón por la cual se rechaza la solicitud...",
        required=True,
        max_length=500
    )

    def __init__(self, message: discord.Message, embed: discord.Embed):
        super().__init__(title="Rechazar Solicitud de Ausencia")
        self.message = message
        self.embed = embed

    async def on_submit(self, interaction: discord.Interaction):
        if "Procesado" in self.embed.footer.text:
            return await interaction.response.send_message("⚠️ Esta solicitud ya fue procesada.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        footer_data = self.embed.footer.text.split("|")
        user_id = int(footer_data[0].split(":")[1])

        self.embed.title, self.embed.color = "❌ AUSENCIA RECHAZADA", discord.Color.red()
        self.embed.add_field(name="👨‍⚖️ Rechazado por", value=interaction.user.mention, inline=False)
        self.embed.add_field(name="📝 Motivo del Rechazo", value=self.motivo.value, inline=False)
        self.embed.set_footer(text="Estado: Procesado (Rechazada)")
        await self.message.edit(embed=self.embed, view=None)

        miembro = interaction.guild.get_member(user_id)
        if miembro:
            try:
                embed_dm = discord.Embed(
                    title="❌ SOLICITUD DE AUSENCIA RECHAZADA",
                    description="Hola. Te informamos que tu solicitud de ausencia temporal en la institución ha sido **rechazada** por la administración.",
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow()
                )
                embed_dm.set_author(name="Policía Federal Argentina - Ibiza Roleplay", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
                embed_dm.add_field(name="📝 Motivo del Rechazo", value=self.motivo.value, inline=False)
                embed_dm.add_field(name="👮 Rechazado por", value=f"{interaction.user.mention} (`{interaction.user.display_name}`)", inline=False)
                embed_dm.set_thumbnail(url=miembro.display_avatar.url)
                embed_dm.set_footer(text="Departamento de Recursos Humanos — P.F.A")
                await miembro.send(embed=embed_dm)
            except Exception as e:
                print(f"Error al enviar MD al oficial rechazado: {e}")

        await interaction.followup.send("❌ Solicitud rechazada y notificada correctamente.", ephemeral=True)

class ViewAprobarAusencia(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Aceptar", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_aceptar_aus_v1")
    async def btn_aceptar(self, interaction: discord.Interaction, button: discord.ui.Button):
        roles_aprobar = obtener_config_list(interaction.guild.id, "ROLES_APROBAR_AUSENCIAS", ROLES_APROBAR_AUSENCIAS)
        if not any(rol.id in roles_aprobar for rol in interaction.user.roles): return await interaction.response.send_message("⛔ Acceso Denegado.", ephemeral=True)
        embed = interaction.message.embeds[0]
        if "Procesado" in embed.footer.text: return await interaction.response.send_message("⚠️ Ya procesada.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)

        footer_data = embed.footer.text.split("|")
        user_id = int(footer_data[0].split(":")[1])
        timestamp_fin = int(footer_data[1].split(":")[1])

        cursor.execute("SELECT 1 FROM ausencias_activas WHERE user_id = %s", (user_id,))
        if cursor.fetchone(): cursor.execute("UPDATE ausencias_activas SET fecha_fin = %s WHERE user_id = %s", (timestamp_fin, user_id))
        else: cursor.execute("INSERT INTO ausencias_activas (user_id, fecha_fin) VALUES (%s, %s)", (user_id, timestamp_fin))
        conn.commit()

        miembro = interaction.guild.get_member(user_id)
        if miembro:
            rol_ausente_id = obtener_config_int(interaction.guild.id, "ROL_AUSENTE_ID", ROL_AUSENTE_ID)
            rol_ausente = interaction.guild.get_role(rol_ausente_id)
            if rol_ausente: await miembro.add_roles(rol_ausente)
            try: await miembro.send("✅ **Tu solicitud de Ausencia ha sido APROBADA.**")
            except: pass

        embed.title, embed.color = "✅ AUSENCIA APROBADA", discord.Color.green()
        embed.add_field(name="👨‍⚖️ Autorizado por", value=interaction.user.mention, inline=False)
        embed.set_footer(text="Estado: Procesado (Aceptada)")
        await interaction.message.edit(embed=embed, view=None)
        await interaction.followup.send("Aprobada.", ephemeral=True)

    @discord.ui.button(label="Rechazar", style=discord.ButtonStyle.danger, emoji="❌", custom_id="btn_rechazar_aus_v1")
    async def btn_rechazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        roles_aprobar = obtener_config_list(interaction.guild.id, "ROLES_APROBAR_AUSENCIAS", ROLES_APROBAR_AUSENCIAS)
        if not any(rol.id in roles_aprobar for rol in interaction.user.roles): return await interaction.response.send_message("⛔ Acceso Denegado.", ephemeral=True)
        embed = interaction.message.embeds[0]
        if "Procesado" in embed.footer.text: return await interaction.response.send_message("⚠️ Ya procesada.", ephemeral=True)
        
        await interaction.response.send_modal(ModalRechazoAusencia(message=interaction.message, embed=embed))

class ViewPanelAusencia(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Solicitar Ausencia", style=discord.ButtonStyle.secondary, emoji="✈️", custom_id="btn_solicitar_ausencia_v1")
    async def btn_ausencia(self, interaction: discord.Interaction, button: discord.ui.Button):
        roles_permitidos_ausencia = obtener_config_list(interaction.guild.id, "ROLES_PERMITIDOS_AUSENCIA", ROLES_PERMITIDOS_AUSENCIA)
        roles_staff = obtener_config_list(interaction.guild.id, "ROLES_PARA_ADMIN_STAFF", ROLES_PARA_ADMIN_STAFF)
        if not any(rol.id in roles_permitidos_ausencia for rol in interaction.user.roles) and not any(rol.id in roles_staff for rol in interaction.user.roles):
            return await interaction.response.send_message("⛔ **Acceso Denegado.**", ephemeral=True)

        cursor.execute("SELECT 1 FROM ausencias_activas WHERE user_id = %s", (interaction.user.id,))
        if cursor.fetchone(): return await interaction.response.send_message("⚠️ Ya tienes una ausencia activa en curso.", ephemeral=True)

        mes_actual = discord.utils.utcnow().strftime("%Y-%m")
        cursor.execute("SELECT ultima_fecha, conteo_mes, dias_usados_mes FROM registro_pedidos_ausencia WHERE user_id = %s", (interaction.user.id,))
        resultado = cursor.fetchone()

        dias_restantes, conteo_mes = 14, 0
        if resultado and resultado[0] == mes_actual:
            conteo_mes = resultado[1] or 0
            dias_restantes = 14 - (resultado[2] or 0)

        if conteo_mes >= 5: return await interaction.response.send_message("❌ Límite Mensual Alcanzado.", ephemeral=True)
        if dias_restantes <= 0: return await interaction.response.send_message("❌ Sin días disponibles este mes.", ephemeral=True)

        await interaction.response.send_modal(ModalAusencia(dias_restantes=dias_restantes))

    @discord.ui.button(label="Finalizar Ausencia", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_finalizar_ausencia_v1")
    async def btn_finalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor.execute("SELECT 1 FROM ausencias_activas WHERE user_id = %s", (interaction.user.id,))
        if not cursor.fetchone(): return await interaction.response.send_message("⚠️ No tienes ausencia activa.", ephemeral=True)

        cursor.execute("DELETE FROM ausencias_activas WHERE user_id = %s", (interaction.user.id,))
        conn.commit()

        rol_ausente_id = obtener_config_int(interaction.guild.id, "ROL_AUSENTE_ID", ROL_AUSENTE_ID)
        rol_ausente = interaction.guild.get_role(rol_ausente_id)
        if rol_ausente and rol_ausente in interaction.user.roles: await interaction.user.remove_roles(rol_ausente)

        canal_ausencias_id = obtener_config_int(interaction.guild.id, "CANAL_AUSENCIAS_ID", CANAL_AUSENCIAS_ID)
        canal_rrhh = interaction.guild.get_channel(canal_ausencias_id)
        if canal_rrhh:
            embed_log = discord.Embed(title="✅ REINCORPORACIÓN", description=f"{interaction.user.mention} regresó al servicio.", color=discord.Color.green())
            embed_log.set_thumbnail(url=interaction.user.display_avatar.url)
            await canal_rrhh.send(embed=embed_log)
        await interaction.response.send_message("✅ Has finalizado tu ausencia exitosamente.", ephemeral=True)
            
    @discord.ui.button(label="Ver Activos (Staff)", style=discord.ButtonStyle.primary, emoji="👀", custom_id="btn_ver_activos_ausencia_v1")
    async def btn_ver_activos(self, interaction: discord.Interaction, button: discord.ui.Button):
        roles_aprobar = obtener_config_list(interaction.guild.id, "ROLES_APROBAR_AUSENCIAS", ROLES_APROBAR_AUSENCIAS)
        if not any(rol.id in roles_aprobar for rol in interaction.user.roles): return await interaction.response.send_message("⛔ Acceso Denegado.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        cursor.execute("SELECT user_id, fecha_fin FROM ausencias_activas")
        resultados = cursor.fetchall()
        if not resultados: return await interaction.followup.send("📭 Ningún oficial con licencia activa.", ephemeral=True)
        embed = discord.Embed(title="✈️ Oficiales con Licencia", description="\\n".join([f"• <@{uid}> — Regresa: <t:{ts}:D>" for uid, ts in resultados])[:4000], color=discord.Color.orange())
        await interaction.followup.send(embed=embed, ephemeral=True)

class PanelRRHH(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_load(self):
        self.bot.add_view(ViewPanelBaja())
        self.bot.add_view(ViewPanelAusencia())
        self.bot.add_view(ViewAprobarAusencia())
        self.revisar_ausencias_expiradas.start()

    def cog_unload(self):
        self.revisar_ausencias_expiradas.cancel()

    @tasks.loop(hours=1)
    async def revisar_ausencias_expiradas(self):
        ahora_timestamp = int(discord.utils.utcnow().timestamp())
        cursor.execute("SELECT user_id FROM ausencias_activas WHERE fecha_fin <= %s", (ahora_timestamp,))
        expiradas = cursor.fetchall()
        if not expiradas:
            return

        ids_expirados = [user_id for (user_id,) in expiradas]
        for guild in self.bot.guilds:
            rol_ausente_id = obtener_config_int(guild.id, "ROL_AUSENTE_ID", ROL_AUSENTE_ID)
            rol_ausente = guild.get_role(rol_ausente_id) if rol_ausente_id else None
            if not rol_ausente:
                continue
            for user_id in ids_expirados:
                miembro = guild.get_member(user_id)
                if miembro:
                    try: await miembro.remove_roles(rol_ausente)
                    except: pass

        for user_id in ids_expirados:
            cursor.execute("DELETE FROM ausencias_activas WHERE user_id = %s", (user_id,))
        conn.commit()

    @revisar_ausencias_expiradas.before_loop
    async def before_revisar(self):
        await self.bot.wait_until_ready()

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingAnyRole): await interaction.response.send_message("⛔ No tienes el rango necesario.", ephemeral=True)

    @app_commands.command(name="crearpanelbaja", description="Despliega el panel de RRHH para solicitar la baja.")
    async def crearpanelbaja(self, i: discord.Interaction):
        es_staff = i.user.id == i.guild.owner_id or i.user.guild_permissions.administrator
        roles_staff = obtener_config_list(i.guild.id, "ROLES_PARA_ADMIN_STAFF", [1351228669359558809, 1390055851657789481, 1411483502142029866])
        if not (es_staff or any(r.id in roles_staff for r in i.user.roles)):
            return await i.response.send_message("⛔ No tienes el rango necesario.", ephemeral=True)
        embed = discord.Embed(title="🚪 PANEL DE SOLICITAR BAJA - P.F.A", description="Si deseas retirarte de la Institución, completa el formulario. Se retirarán tus roles.", color=discord.Color.dark_red())
        await i.channel.send(embed=embed, view=ViewPanelBaja())
        await i.response.send_message("✅ Creado.", ephemeral=True)

    @app_commands.command(name="crearpanelausencia", description="Despliega el panel para solicitar licencias temporales.")
    async def crearpanelausencia(self, i: discord.Interaction):
        es_staff = i.user.id == i.guild.owner_id or i.user.guild_permissions.administrator
        roles_staff = obtener_config_list(i.guild.id, "ROLES_PARA_ADMIN_STAFF", [1351228669359558809, 1390055851657789481, 1411483502142029866])
        if not (es_staff or any(r.id in roles_staff for r in i.user.roles)):
            return await i.response.send_message("⛔ No tienes el rango necesario.", ephemeral=True)
        embed = discord.Embed(title="✈️ REGISTRO DE AUSENCIAS", description="Panel de gestión de licencias. Límite 14 días / 5 solicitudes mensuales.", color=discord.Color.dark_theme())
        await i.channel.send(embed=embed, view=ViewPanelAusencia())
        await i.response.send_message("✅ Creado.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PanelRRHH(bot))