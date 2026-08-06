import discord
from discord.ext import commands, tasks
from discord import app_commands
import re
from utils.core import cursor, conn, obtener_coins, actualizar_coins, enviar_log
from cogs.panel_cupones import enviar_log_cupon
from utils.config import obtener_config_int, obtener_config_list

PRECIOS_SHOP = {
    "💰 30M IC": 3, 
    "⚠️ Remover 1 Advertencia": 3, 
    "🚫 Remover 1 Strike": 8, 
    "🎖 Promote Subdivisionario": 10, 
    "🏅 Promote Faccionario": 16, 
    "👕 Ropa Personalizada": 22, 
    "🚗 Auto del Mes": 26, 
    "🌴 VIP Ibiza": 24
}

# ═══════════════════════════════════════════════════════════════════
#  MODALES Y FORMULARIOS
# ═══════════════════════════════════════════════════════════════════

class ModalVerCoins(discord.ui.Modal, title="Consultar Coins de Usuario"):
    user_id_input = discord.ui.TextInput(label="ID de Discord", max_length=20)
    
    async def on_submit(self, interaction: discord.Interaction):
        try: 
            target_id = int(self.user_id_input.value)
        except ValueError: 
            return await interaction.response.send_message("❌ ID inválido.", ephemeral=True)
            
        coins = obtener_coins(target_id)
        coins_f = f"{coins:,.2f}".replace(",", ".")
        await interaction.response.send_message(f"👤 El usuario <@{target_id}> tiene **{coins_f} coins**.", ephemeral=True)

class ModalMonedas(discord.ui.Modal):
    def __init__(self, tipo):
        self.tipo = tipo
        super().__init__(title="Añadir Monedas" if tipo == "dar" else "Retirar Monedas")
        self.u_input = discord.ui.TextInput(label="ID de Discord", max_length=20)
        self.c_input = discord.ui.TextInput(label="Cantidad de Coins")
        self.add_item(self.u_input)
        self.add_item(self.c_input)

    async def on_submit(self, interaction: discord.Interaction):
        try: 
            t_id = int(self.u_input.value)
            c = float(self.c_input.value.replace(",", "."))
            if c <= 0: raise ValueError
        except ValueError: 
            return await interaction.response.send_message("❌ Datos inválidos.", ephemeral=True)
            
        actualizar_coins(t_id, c if self.tipo == "dar" else -c)
        await enviar_log(interaction.client, interaction.user, t_id, c, self.tipo)

        c_f = f"{c:,.2f}".replace(",", ".")
        verbo = "entregadas a" if self.tipo == "dar" else "retiradas de"
        await interaction.response.send_message(
            f"✅ **{c_f}** coins {verbo} <@{t_id}>.",
            ephemeral=True,
        )

class ModalMultipleCoins(discord.ui.Modal, title="Dar Coins a Múltiples Usuarios"):
    cantidad_input = discord.ui.TextInput(
        label="Cantidad de Coins (para cada uno)",
        placeholder="Ej: 5.00",
        max_length=10,
        required=True
    )
    ids_input = discord.ui.TextInput(
        label="IDs de usuarios (uno por línea)",
        style=discord.TextStyle.paragraph,
        placeholder="<@123...> <@456...>\n789...",
        max_length=4000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cantidad = float(self.cantidad_input.value.replace(",", "."))
            if cantidad <= 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Cantidad inválida.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        texto = self.ids_input.value

        # Las menciones <@ID> o <@!ID> tienen delimitadores propios, así que se
        # detectan correctamente incluso si están pegadas una a la otra sin
        # espacios ni comas (ej: "<@111><@222><@333>").
        ids_mencion = re.findall(r"<@!?(\d{15,20})>", texto)

        # IDs sueltos (sin formato de mención) separados por espacio, coma o salto de línea.
        texto_sin_menciones = re.sub(r"<@!?\d{15,20}>", " ", texto)
        ids_sueltos = re.findall(r"\d{15,20}", texto_sin_menciones)

        # Se preserva el orden y se eliminan duplicados.
        ids_unicos = list(dict.fromkeys(ids_mencion + ids_sueltos))

        if not ids_unicos:
            return await interaction.followup.send(
                "⚠️ No se detectó ningún ID válido. Verificá que sean IDs de Discord de 15 a 20 dígitos.",
                ephemeral=True,
            )

        exitosos, fallidos = [], []

        for id_str in ids_unicos:
            try:
                user_id = int(id_str)
                actualizar_coins(user_id, cantidad)
                await enviar_log(interaction.client, interaction.user, user_id, cantidad, "dar")
                exitosos.append(user_id)
            except Exception as e:
                fallidos.append((id_str, str(e)))

        embed = discord.Embed(
            title="🪙 Entrega Múltiple de Coins",
            color=discord.Color.green() if exitosos and not fallidos else (
                discord.Color.orange() if exitosos else discord.Color.red()
            ),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="💰 Coins entregadas", value=f"`{cantidad:.2f}` por usuario", inline=True)
        embed.add_field(name="✅ Entregado a", value=f"`{len(exitosos)}` usuario/s", inline=True)
        embed.add_field(name="❌ Fallidos", value=f"`{len(fallidos)}` usuario/s", inline=True)

        if exitosos:
            lista = "\n".join(f"<@{uid}>" for uid in exitosos)
            if len(lista) > 1000:
                lista = lista[:1000].rsplit("\n", 1)[0] + f"\n... y {len(exitosos) - lista[:1000].count('<@')} más"
            embed.add_field(name="Usuarios", value=lista, inline=False)

        if fallidos:
            lista_fallidos = "\n".join(f"`{id_str}` — {motivo}" for id_str, motivo in fallidos[:10])
            if len(fallidos) > 10:
                lista_fallidos += f"\n... y {len(fallidos) - 10} más"
            embed.add_field(name="IDs con error", value=lista_fallidos, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════════════════════════════
#  INTERFACES DE PANELES (BOTONES)
# ═══════════════════════════════════════════════════════════════════

class PanelStaff(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Dar Monedas", style=discord.ButtonStyle.primary, custom_id="staff_dar_btn")
    async def dar_btn(self, interaction: discord.Interaction, button: discord.ui.Button): 
        await interaction.response.send_modal(ModalMonedas("dar"))
        
    @discord.ui.button(label="Dar Múltiples Coins", style=discord.ButtonStyle.primary, custom_id="staff_dar_multi_btn")
    async def dar_multi_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModalMultipleCoins())
        
    @discord.ui.button(label="Quitar Monedas", style=discord.ButtonStyle.danger, custom_id="staff_quitar_btn")
    async def quitar_btn(self, interaction: discord.Interaction, button: discord.ui.Button): 
        await interaction.response.send_modal(ModalMonedas("quitar"))
        
    @discord.ui.button(label="Ver Coins", style=discord.ButtonStyle.success, custom_id="staff_ver_btn")
    async def ver_btn(self, interaction: discord.Interaction, button: discord.ui.Button): 
        await interaction.response.send_modal(ModalVerCoins())

class PanelCoins(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Ver mis coins", style=discord.ButtonStyle.success, custom_id="boton_ver_coins_unico")
    async def ver(self, interaction: discord.Interaction, button: discord.ui.Button):
        roles_para_ver = obtener_config_list(interaction.guild.id, "ROLES_PARA_VER", [1393678701408817284, 1390022409381216388, 1418013190075322428, 1441595283808063610, 1448157942066184354])
        if not any(r.id in roles_para_ver for r in interaction.user.roles): 
            return await interaction.response.send_message("⛔ Acceso Denegado.", ephemeral=True)
            
        coins = obtener_coins(interaction.user.id)
        coins_f = f"{coins:,.2f}".replace(",", ".")
        await interaction.response.send_message(f'🪙 Tienes **{coins_f} coins**.', ephemeral=True)

    @discord.ui.button(label="Ranking Subdivisiones", style=discord.ButtonStyle.secondary, custom_id="btn_ranking_subdivs_v1")
    async def ranking_subdivs_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        roles_para_ver = obtener_config_list(interaction.guild.id, "ROLES_PARA_VER", [1393678701408817284, 1390022409381216388, 1418013190075322428, 1441595283808063610, 1448157942066184354])
        if not any(rol.id in roles_para_ver for rol in interaction.user.roles):
            return await interaction.response.send_message("⛔ No tienes el rango necesario para visualizar el ranking.", ephemeral=True)

        cursor.execute("SELECT division, puntos FROM competencia_subdivisiones ORDER BY puntos DESC")
        stats = cursor.fetchall()
        
        embed = discord.Embed(
            title="📊 COMPETENCIA SEMANAL DE SUBDIVISIONES", 
            description="Estado actual de misiones completadas por cada unidad:\n\n",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        if not stats:
            embed.description += "*No hay datos registrados aún.*"
        else:
            desc = ""
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            for i, (div, pts) in enumerate(stats, start=1):
                m = medals.get(i, "🎖️")
                desc += f"{m} **{div}**: `{pts}` misiones\n"
            embed.description += desc

        embed.set_footer(text="Bono de 0.20 coins: Todos los domingos a las 21:00 Arg")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ShopSelect(discord.ui.Select):
    def __init__(self):
        opts = [discord.SelectOption(label=item, description=f"Costo: {precio} Coins", value=item) for item, precio in PRECIOS_SHOP.items()]
        super().__init__(placeholder="Selecciona un premio...", options=opts, custom_id="shop_select")
        
    async def callback(self, interaction: discord.Interaction):
        for option in self.options: 
            option.default = (option.value == self.values[0])
        await interaction.response.edit_message(view=self.view)

class ViewShop(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShopSelect())
        
    @discord.ui.button(label="Canjear Premio", style=discord.ButtonStyle.success, custom_id="btn_canjear")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        select = next((x for x in self.children if isinstance(x, ShopSelect)), None)
        if not select or not select.values: 
            return await interaction.response.send_message("❌ Elige un objeto primero.", ephemeral=True)
            
        item_elegido = select.values[0]
        costo = PRECIOS_SHOP[item_elegido]
        saldo_actual = obtener_coins(interaction.user.id)
        
        if saldo_actual < costo: 
            return await interaction.response.send_message(f"❌ Saldo insuficiente. Tienes {saldo_actual:.2f}.", ephemeral=True)

        actualizar_coins(interaction.user.id, -costo)
        await enviar_log(interaction.client, interaction.user, interaction.user.id, -costo, "compra", item_elegido)
        
        for option in select.options:
            option.default = False

        mensaje_extra = "⚠️ **PARA RECLAMAR:** Abre TICKET adjuntando una captura."

        if "Strike" in item_elegido:
            cursor.execute("INSERT INTO cupones_usuario (user_id, tipo_cupon, cantidad) VALUES (%s, 'strike', 1) ON CONFLICT (user_id, tipo_cupon) DO UPDATE SET cantidad = cupones_usuario.cantidad + 1", (interaction.user.id,))
            conn.commit()
            await enviar_log_cupon(bot=interaction.client, tipo="shop", usuario=interaction.user, tipo_cupon="strike", item_comprado=item_elegido)
            mensaje_extra = "🎟️ **¡SECRETO DESBLOQUEADO!**\nSe ha añadido **1 Cupón de Strike** a tu panel de cupones."
            
        elif "Advertencia" in item_elegido:
            cursor.execute("INSERT INTO cupones_usuario (user_id, tipo_cupon, cantidad) VALUES (%s, 'advertencia', 1) ON CONFLICT (user_id, tipo_cupon) DO UPDATE SET cantidad = cupones_usuario.cantidad + 1", (interaction.user.id,))
            conn.commit()
            await enviar_log_cupon(bot=interaction.client, tipo="shop", usuario=interaction.user, tipo_cupon="advertencia", item_comprado=item_elegido)
            mensaje_extra = "🎟️ **¡SECRETO DESBLOQUEADO!**\nSe ha añadido **1 Cupón de Advertencia** a tu panel de cupones."

        elif "Promote Faccionario" in item_elegido:
            cursor.execute("INSERT INTO cupones_usuario (user_id, tipo_cupon, cantidad) VALUES (%s, 'promote_faccionario', 1) ON CONFLICT (user_id, tipo_cupon) DO UPDATE SET cantidad = cupones_usuario.cantidad + 1", (interaction.user.id,))
            conn.commit()
            await enviar_log_cupon(bot=interaction.client, tipo="shop", usuario=interaction.user, tipo_cupon="promote_faccionario", item_comprado=item_elegido)
            mensaje_extra = "🎟️ **¡SECRETO DESBLOQUEADO!**\nSe ha añadido **1 Cupón de Promote Faccionario** a tu panel de cupones."

        embed_compra = discord.Embed(
            title="✅ CANJE EXITOSO", 
            description=f"Canjeaste: **{item_elegido}**\n💰 Se te descontaron **{costo} coins**.\n\n{mensaje_extra}", 
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed_compra, ephemeral=True)
        await interaction.edit_original_response(view=self.view)

class ViewAirdrop(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)
        
    @discord.ui.button(label="🎁 RECLAMAR RECOMPENSA", style=discord.ButtonStyle.success, custom_id="btn_airdrop_unico")
    async def reclamar_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children: 
            child.disabled = True
            
        recompensa = 0.50
        actualizar_coins(interaction.user.id, recompensa)
        await enviar_log(interaction.client, interaction.user, interaction.user.id, recompensa, "airdrop_reclamado", "Ganador del Airdrop")
        
        embed_ganador = discord.Embed(
            title="🎁 AIRDROP RECLAMADO", 
            description=f"¡Felicidades {interaction.user.mention}!\nHas sido el más rápido y ganaste **0.50 coins**.", 
            color=discord.Color.gold()
        )
        await interaction.response.edit_message(embed=embed_ganador, view=self)


# ═══════════════════════════════════════════════════════════════════
#  CLASE PRINCIPAL DEL COG
# ═══════════════════════════════════════════════════════════════════

class PanelEconomia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mensaje_top = None

    def _es_staff(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator:
            return True
        roles_staff = obtener_config_list(interaction.guild.id, "ROLES_PARA_ADMIN_STAFF", [1351228669359558809, 1390055851657789481, 1411483502142029866])
        return any(r.id in roles_staff for r in interaction.user.roles)

    def cog_load(self):
        self.bot.add_view(PanelCoins())
        self.bot.add_view(PanelStaff())
        self.bot.add_view(ViewShop())
        self.bot.add_view(ViewAirdrop())
        self.actualizar_top_loop.start()

    def cog_unload(self):
        self.actualizar_top_loop.cancel()

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingAnyRole): 
            await interaction.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)

    @app_commands.command(name="crearpanel", description="Genera el panel de banco PFA.")
    async def crearpanel(self, interaction: discord.Interaction):
        if not self._es_staff(interaction):
            return await interaction.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)

        embed = discord.Embed(
            title="🏦 SISTEMA BANCARIO P.F.A", 
            description="Gestione sus activos y consulte el desempeño de su unidad operativa.\n\n💰 **Ver mis coins:** Consulta tu saldo personal en tiempo real.",
            color=discord.Color.green()
        )
        await interaction.channel.send(embed=embed, view=PanelCoins())
        await interaction.response.send_message("✅ Panel desplegado.", ephemeral=True)

    @app_commands.command(name="panelstaff", description="Panel de gestión económica para la administración.")
    async def panelstaff(self, interaction: discord.Interaction):
        if not self._es_staff(interaction):
            return await interaction.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)

        await interaction.channel.send(embed=discord.Embed(title="🛡️ STAFF", description="Gestión Económica.", color=discord.Color.red()), view=PanelStaff())
        await interaction.response.send_message("✅ Staff creado.", ephemeral=True)

    @app_commands.command(name="crearshop", description="Despliega la tienda oficial de la PFA.")
    async def crearshop(self, interaction: discord.Interaction):
        if not self._es_staff(interaction):
            return await interaction.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)

        embed = discord.Embed(
            title="🛒 SHOP P.F.A", 
            description="Sistema de canje de recompensas por activity.\n\nSelecciona el objeto en el menú desplegable y presiona Canjear.",
            color=discord.Color.dark_blue()
        )
        await interaction.channel.send(embed=embed, view=ViewShop())
        await interaction.response.send_message("✅ Shop desplegado.", ephemeral=True)

    @app_commands.command(name="airdropcoins", description="Lanza un maletín con coins en el chat.")
    async def airdropcoins(self, interaction: discord.Interaction):
        es_staff = interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator
        roles_airdrop = obtener_config_list(interaction.guild.id, "ROLES_LANZAR_AIRDROP", [1351228669359558809])
        if not (es_staff or any(r.id in roles_airdrop for r in interaction.user.roles)):
            return await interaction.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)

        await enviar_log(self.bot, interaction.user, interaction.user.id, 0, "airdrop_lanzado")
        canal_general_id = obtener_config_int(interaction.guild.id, "CANAL_GENERAL_ID", 1351225457864867963)
        canal_general = self.bot.get_channel(canal_general_id)
        
        embed = discord.Embed(
            title="🎁 ¡ATENCIÓN: AIRDROP DE COINS!", 
            description="¡Un administrador lanzó un maletín!\nEl primero en tocar gana **0.50 coins**.", 
            color=discord.Color.blue()
        )
        embed.set_image(url="https://i.imgur.com/r6A4oXW.png")
        
        if canal_general:
            await canal_general.send(content="@everyone", embed=embed, view=ViewAirdrop())
        await interaction.response.send_message("✅ Airdrop lanzado con éxito.", ephemeral=True)

    # --- BUCLE AUTOMÁTICO: TOP GLOBAL (ACTUALIZADO CON DISEÑO MULTI-SERVIDOR) ---
    @tasks.loop(minutes=5)
    async def actualizar_top_loop(self):
        for guild in self.bot.guilds:
            canal_top_id = obtener_config_int(guild.id, "CANAL_TOP_ID", 1474150864099737752)
            if not canal_top_id:
                continue
                
            canal = guild.get_channel(canal_top_id)
            if not canal:
                continue
                
            cursor.execute("SELECT user_id, coins FROM usuarios ORDER BY coins DESC LIMIT 5")
            top_usuarios = cursor.fetchall()
            
            embed = discord.Embed(
                title="🏆 Tabla de Clasificación Global", 
                color=0xFFD700, 
                timestamp=discord.utils.utcnow()
            )
            
            if not top_usuarios:
                embed.description = "🕸️ *La bóveda está vacía.*"
            else:
                desc = ""
                medals = {1: "🥇", 2: "🥈", 3: "🥉", 4: "🏅", 5: "🏅"}
                for i, (user_id, coins) in enumerate(top_usuarios, start=1):
                    coins_f = f"{coins:,.2f}".replace(",", ".")
                    medalla = medals.get(i, "🏅")
                    desc += f"{medalla} **Posición #{i}** ━ <@{user_id}>\n└ 🪙 **{coins_f}** Coins\n\n"
                embed.description = desc
                
            # Buscar si ya hay un mensaje del bot en el canal
            last_msg = None
            try:
                async for msg in canal.history(limit=5):
                    if msg.author == self.bot.user:
                        last_msg = msg
                        break
                
                if last_msg:
                    await last_msg.edit(embed=embed)
                else:
                    await canal.purge(limit=5)
                    await canal.send(embed=embed)
            except Exception:
                try:
                    await canal.purge(limit=5)
                    await canal.send(embed=embed)
                except Exception:
                    pass

    @actualizar_top_loop.before_loop
    async def before_actualizar_top(self):
        await self.bot.wait_until_ready()

async def setup(bot): 
    await bot.add_cog(PanelEconomia(bot))