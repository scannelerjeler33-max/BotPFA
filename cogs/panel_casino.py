import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import asyncio
import datetime
from utils.core import obtener_coins, actualizar_coins, enviar_log
from utils.config import obtener_config_int, obtener_config_list

# --- CONFIGURACIÓN ---
CANAL_GENERAL_ID = 1351225457864867963
ROL_AVISO_CASINO = 1393678701408817284
ROLES_PARA_ADMIN_STAFF = [1351228669359558809, 1390055851657789481, 1411483502142029866] 
ROLES_PERMITIDOS_CASINO = [1393678701408817284, 1351228669359558809]


# ═══════════════════════════════════════════════════════════════════
#  MINIJUEGO 1: BLACKJACK CONTRA EL BOT (ANIMADO)
# ═══════════════════════════════════════════════════════════════════

def calcular_valor_blackjack(mano):
    valor = 0
    ases = 0
    for carta in mano:
        rango = carta[:-2]
        if rango in ['J', 'Q', 'K']: valor += 10
        elif rango == 'A': ases += 1
        else: valor += int(rango)
    for _ in range(ases):
        if valor + 11 <= 21: valor += 11
        else: valor += 1
    return valor

class BlackjackGame(discord.ui.View):
    def __init__(self, interaction, apuesta):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.apuesta = apuesta
        palos = ['♠️', '♥️', '♦️', '♣️']
        valores = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        self.baraja = [v + p for v in valores for p in palos]
        random.shuffle(self.baraja)
        self.mano_jugador = []
        self.mano_bot = []

    def crear_embed(self, titulo, color, final=False, animacion=False):
        embed = discord.Embed(title=titulo, color=color)
        val_j = calcular_valor_blackjack(self.mano_jugador)
        val_b = calcular_valor_blackjack(self.mano_bot)
        
        jugador_str = ", ".join(self.mano_jugador) if self.mano_jugador else "Repartiendo..."
        embed.add_field(name="Tus Cartas", value=f"{jugador_str}\n(Total: **{val_j}**)", inline=True)
        
        if animacion:
            embed.add_field(name="Cartas del Bot", value="🎴 Repartiendo...", inline=True)
        elif final:
            embed.add_field(name="Cartas del Bot", value=f"{', '.join(self.mano_bot)}\n(Total: **{val_b}**)", inline=True)
        else:
            bot_visible = self.mano_bot[0] if self.mano_bot else "🎴"
            embed.add_field(name="Carta del Bot", value=f"{bot_visible}, ❓", inline=True)
            
        embed.set_footer(text=f"Apuesta: {self.apuesta} coins")
        return embed

    async def repartir_inicial(self, interaction):
        for _ in range(2):
            self.mano_jugador.append(self.baraja.pop())
            await interaction.edit_original_response(embed=self.crear_embed("🎴 Repartiendo cartas...", discord.Color.light_grey(), animacion=True))
            await asyncio.sleep(0.6)
            self.mano_bot.append(self.baraja.pop())
            await interaction.edit_original_response(embed=self.crear_embed("🎴 Repartiendo cartas...", discord.Color.light_grey(), animacion=True))
            await asyncio.sleep(0.6)
        
        await interaction.edit_original_response(embed=self.crear_embed("Blackjack - Tu turno", discord.Color.blue()), view=self)

    @discord.ui.button(label="Pedir Carta", style=discord.ButtonStyle.primary)
    async def pedir(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.mano_jugador.append(self.baraja.pop())
        val = calcular_valor_blackjack(self.mano_jugador)
        if val > 21:
            await self.finalizar(interaction, "❌ ¡TE PASASTE! PERDISTE", discord.Color.red(), -self.apuesta)
        else:
            await interaction.response.edit_message(embed=self.crear_embed("Blackjack - Tu turno", discord.Color.blue()), view=self)

    @discord.ui.button(label="Plantarse", style=discord.ButtonStyle.secondary)
    async def plantarse(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(embed=self.crear_embed("🤖 El Bot está analizando la mesa...", discord.Color.orange()), view=self)
        
        while True:
            val_j = calcular_valor_blackjack(self.mano_jugador)
            val_b = calcular_valor_blackjack(self.mano_bot)

            if val_b < 17:
                self.mano_bot.append(self.baraja.pop())
            elif val_b < val_j and val_j <= 21:
                self.mano_bot.append(self.baraja.pop())
            else:
                break

            await asyncio.sleep(1.2)
            await interaction.edit_original_response(embed=self.crear_embed("🤖 El Bot está pidiendo cartas...", discord.Color.orange(), final=True))
            
            if val_b > 21:
                break

        val_j = calcular_valor_blackjack(self.mano_jugador)
        val_b = calcular_valor_blackjack(self.mano_bot)
        
        if val_b > 21:
            msg, res, col = ("🏆 ¡EL BOT SE PASÓ! ¡GANASTE!", self.apuesta, discord.Color.green())
            if val_j == 21: msg, res, col = ("🔥 ¡BLACKJACK! ¡GANASTE (x1.5)! 🏆", self.apuesta * 1.5, discord.Color.gold())
        elif val_j > val_b:
            msg, res, col = ("🏆 ¡LE GANASTE AL BOT! ¡GANASTE!", self.apuesta, discord.Color.green())
            if val_j == 21: msg, res, col = ("🔥 ¡BLACKJACK! ¡GANASTE (x1.5)! 🏆", self.apuesta * 1.5, discord.Color.gold())
        elif val_j < val_b:
            msg, res, col = ("❌ EL BOT TIENE MEJOR MANO. PERDISTE", -self.apuesta, discord.Color.red())
        else:
            msg, res, col = ("⚖️ ¡EMPATE!", 0, discord.Color.light_grey())

        await self.finalizar(interaction, msg, col, res)

    async def finalizar(self, interaction, msg, color, resultado):
        actualizar_coins(self.interaction.user.id, resultado, self.interaction.guild.id)
        # Cambio para utils.core
        await enviar_log(self.interaction.client, self.interaction.user, self.interaction.user.id, resultado, "blackjack", msg)
        
        embed = self.crear_embed(msg, color, final=True)
        saldo_final = f"{obtener_coins(self.interaction.user.id, self.interaction.guild.id):,.2f}".replace(",", ".")
        embed.add_field(name="Saldo Final", value=f"🪙 **{saldo_final}** coins", inline=False)
        
        for child in self.children: child.disabled = True
        await self.interaction.edit_original_response(embed=embed, view=self)

class BlackjackStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Apostar 0.25 y Jugar", style=discord.ButtonStyle.success, custom_id="btn_bj_start")
    async def jugar(self, interaction: discord.Interaction, button: discord.ui.Button):
        ahora_arg = discord.utils.utcnow() - datetime.timedelta(hours=3)
        hora_actual = ahora_arg.hour
        
        roles_staff = obtener_config_list(interaction.guild.id, "ROLES_PARA_ADMIN_STAFF", ROLES_PARA_ADMIN_STAFF)
        roles_casino = obtener_config_list(interaction.guild.id, "ROLES_PERMITIDOS_CASINO", ROLES_PERMITIDOS_CASINO)
        es_staff = any(rol.id in roles_staff for rol in interaction.user.roles)
        tiene_rol_permitido = any(rol.id in roles_casino for rol in interaction.user.roles)

        acceso_concedido = False

        if es_staff:
            acceso_concedido = True  
        elif tiene_rol_permitido:
            if 0 <= hora_actual < 2:
                acceso_concedido = True
            else:
                return await interaction.response.send_message(
                    "🕒 **Fuera de Horario**: Tu rango solo permite jugar de **00:00 a 02:00 AM**.", 
                    ephemeral=True
                )
        else:
            return await interaction.response.send_message(
                "⛔ **Acceso Denegado**: No tienes un rango autorizado para participar en el Casino.", 
                ephemeral=True
            )

        if acceso_concedido:
            apuesta = 0.25
            saldo = obtener_coins(interaction.user.id, interaction.guild.id)
            
            if saldo < apuesta:
                return await interaction.response.send_message(f"❌ Saldo insuficiente.", ephemeral=True)
            
            await interaction.response.send_message("🎴 Preparando mesa...", ephemeral=True)
            juego = BlackjackGame(interaction, apuesta)
            await juego.repartir_inicial(interaction)


# ═══════════════════════════════════════════════════════════════════
#  MINIJUEGO 2: RULETA EUROPEA MULTIJUGADOR EN TIEMPO REAL
# ═══════════════════════════════════════════════════════════════════

ROJOS_RULETA = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
ESTADO_RULETA = "esperando" 
APUESTAS_RONDA = []

async def motor_ruleta(bot, canal, mensaje_panel):
    global ESTADO_RULETA, APUESTAS_RONDA
    ESTADO_RULETA = "apostando"
    
    try:
        for i in range(5):
            embed_activo = mensaje_panel.embeds[0].copy()
            embed_activo.color = discord.Color.green()
            embed_activo.set_footer(text=f"🟢 ¡MESA ABIERTA! Cierra en {10 - (i*2)} segundos...")
            
            nombres = list(set([a["user"].display_name for a in APUESTAS_RONDA]))
            jugadores_str = ", ".join(nombres) if nombres else "Esperando jugadores..."
            
            embed_activo.clear_fields()
            embed_activo.add_field(name="👥 Fichas en la mesa de:", value=f"`{jugadores_str}`", inline=False)
            
            await mensaje_panel.edit(embed=embed_activo)
            await asyncio.sleep(2)
        
        embed_activo = mensaje_panel.embeds[0].copy()
        embed_activo.color = discord.Color.orange()
        embed_activo.set_footer(text="⏳ ¡ÚLTIMOS 5 SEGUNDOS PARA APOSTAR!")
        await mensaje_panel.edit(embed=embed_activo)
        await asyncio.sleep(5)
        
        ESTADO_RULETA = "girando"
        embed_activo = mensaje_panel.embeds[0].copy()
        embed_activo.color = discord.Color.red()
        embed_activo.set_footer(text="🚫 ¡NO VA MÁS! Girando el cilindro...")
        await mensaje_panel.edit(embed=embed_activo)
        
        await asyncio.sleep(3) 
        
        if random.random() < 0.01: 
            resultado_num = 0
        else:
            resultado_num = random.randint(1, 36)
            
        color = "🟢 Verde" if resultado_num == 0 else ("🔴 Rojo" if resultado_num in ROJOS_RULETA else "⚫ Negro")
        
        texto_ganadores = ""
        texto_perdedores = ""
        
        for apuesta in APUESTAS_RONDA:
            u = apuesta["user"]
            r_v, n_v, z_v = apuesta["r"], apuesta["n"], apuesta["z"]
            nums, n_amt = apuesta["nums"], apuesta["n_amt"]
            total_bet = apuesta["total"]
            
            premio = 0.0
            if resultado_num == 0:
                if z_v > 0: premio += z_v * 18
            else:
                if "Rojo" in color and r_v > 0: premio += r_v * 2
                if "Negro" in color and n_v > 0: premio += n_v * 2
                if resultado_num in nums: premio += n_amt * 18
                
            if premio > 0:
                actualizar_coins(u.id, premio, self.interaction.guild.id)
                detalle_log = f"🔸 **Apostó:** `{total_bet:.2f}`\n🔹 **Resultado:** ¡GANÓ! ✅\n🏆 **Premio:** `{premio:.2f}`"
                # Cambio para utils.core
                await enviar_log(bot, u, u.id, premio - total_bet, "ruleta", detalle_log)
                texto_ganadores += f"🎉 {u.mention} (+{premio:.2f})\n"
            else:
                detalle_log = f"🔸 **Apostó:** `{total_bet:.2f}`\n🔹 **Resultado:** PERDIÓ ❌\n💸 **Pérdida:** `{total_bet:.2f}`"
                # Cambio para utils.core
                await enviar_log(bot, u, u.id, -total_bet, "ruleta", detalle_log)
                texto_perdedores += f"💀 {u.mention} (-{total_bet:.2f})\n"
        
        desc_resultados = f"## 🎰 Cayó en: **{resultado_num} {color}** 🎰\n\n"
        
        if texto_ganadores:
            desc_resultados += f"**🏆 GANADORES:**\n{texto_ganadores}\n"
        else:
            desc_resultados += "**🏆 GANADORES:**\n*Nadie acertó.*\n\n"
            
        if texto_perdedores:
            desc_resultados += f"**💸 PERDEDORES:**\n{texto_perdedores}"
            
        embed_res = discord.Embed(description=desc_resultados, color=discord.Color.dark_theme())
        mensaje_resultado = await canal.send(embed=embed_res)
        
        APUESTAS_RONDA.clear()
        ESTADO_RULETA = "esperando"
        
        embed_espera = mensaje_panel.embeds[0].copy()
        embed_espera.color = discord.Color.gold()
        embed_espera.clear_fields() 
        embed_espera.set_footer(text="💤 Mesa esperando apuestas... Toca el botón para iniciar.")
        await mensaje_panel.edit(embed=embed_espera)
        
        await asyncio.sleep(5) 
        try:
            await mensaje_resultado.delete()
        except:
            pass 

    except Exception as e:
        print(f"Error en motor de ruleta: {e}")
        APUESTAS_RONDA.clear()
        ESTADO_RULETA = "esperando"

class ModalRuleta(discord.ui.Modal, title="🎰 Apuestas (Máx 0.10 por casilla)"):
    def __init__(self):
        super().__init__()
        
        self.r_bet = discord.ui.TextInput(label="🔴 Apostar al Rojo", placeholder="Ej: 0.02 (Déjalo vacío si no apuestas)", required=False)
        self.n_bet = discord.ui.TextInput(label="⚫ Apostar al Negro", placeholder="Ej: 0.02 (Déjalo vacío si no apuestas)", required=False)
        self.z_bet = discord.ui.TextInput(label="🟢 Apostar al 0", placeholder="Ej: 0.02 (Déjalo vacío si no apuestas)", required=False)
        self.nums = discord.ui.TextInput(label="🎯 Números (1 al 36 separados por coma)", placeholder="Ej: 17, 8, 24", required=False)
        self.n_amt = discord.ui.TextInput(label="💰 Apuesta POR cada número", placeholder="Ej: 0.01", required=False)

        self.add_item(self.r_bet)
        self.add_item(self.n_bet)
        self.add_item(self.z_bet)
        self.add_item(self.nums)
        self.add_item(self.n_amt)

    async def on_submit(self, interaction: discord.Interaction):
        global ESTADO_RULETA, APUESTAS_RONDA
        
        if ESTADO_RULETA == "girando":
            return await interaction.response.send_message("❌ ¡No va más! La ruleta ya está girando. Espera la próxima ronda.", ephemeral=True)

        try:
            r_val = float(self.r_bet.value.replace(",", ".")) if self.r_bet.value else 0.0
            n_val = float(self.n_bet.value.replace(",", ".")) if self.n_bet.value else 0.0
            z_val = float(self.z_bet.value.replace(",", ".")) if self.z_bet.value else 0.0
            
            if r_val < 0 or n_val < 0 or z_val < 0: raise ValueError
            
            lista_nums = []
            if self.nums.value:
                partes = self.nums.value.split(",")
                for p in partes:
                    num = int(p.strip())
                    if not (1 <= num <= 36):
                        return await interaction.response.send_message("❌ Los números elegidos deben estar entre 1 y 36.", ephemeral=True)
                    lista_nums.append(num)
                    
            n_amt_val = float(self.n_amt.value.replace(",", ".")) if self.n_amt.value else 0.0
            if n_amt_val < 0: raise ValueError
            
            if lista_nums and n_amt_val <= 0:
                return await interaction.response.send_message("❌ Elegiste números pero no pusiste cuánto apostar por cada uno.", ephemeral=True)
            if n_amt_val > 0 and not lista_nums:
                return await interaction.response.send_message("❌ Ingresaste dinero para números, pero no elegiste a qué números.", ephemeral=True)

        except ValueError:
            return await interaction.response.send_message("❌ Error: Usa solo números, puntos y comas válidas. No se permiten valores negativos.", ephemeral=True)

        if r_val > 0.10 or n_val > 0.10 or z_val > 0.10 or n_amt_val > 0.10:
            return await interaction.response.send_message("❌ **Límite Individual:** No puedes apostar más de **0.10 coins** en una sola casilla.", ephemeral=True)

        total_bet = r_val + n_val + z_val + (n_amt_val * len(lista_nums))

        if total_bet <= 0:
            return await interaction.response.send_message("❌ Debes apostar algo para jugar.", ephemeral=True)
        
        if total_bet > 0.10 and len(lista_nums) <= 1:
            return await interaction.response.send_message(f"❌ El límite base es **0.10 coins**. Tu apuesta suma **{total_bet:.2f}**. Solo puedes superar el límite si apuestas a **2 o más números** a la vez.", ephemeral=True)

        saldo = obtener_coins(interaction.user.id, interaction.guild.id)
        if saldo < total_bet:
            return await interaction.response.send_message(f"❌ Saldo insuficiente. Intentas apostar {total_bet:.2f} y tienes {saldo:.2f}.", ephemeral=True)

        actualizar_coins(interaction.user.id, -total_bet, interaction.guild.id)
        
        APUESTAS_RONDA.append({
            "user": interaction.user,
            "total": total_bet,
            "r": r_val,
            "n": n_val,
            "z": z_val,
            "nums": lista_nums,
            "n_amt": n_amt_val
        })

        await interaction.response.send_message(f"✅ Tus fichas están en la mesa (**Total apostado: {total_bet:.2f} coins**).", ephemeral=True)

        if ESTADO_RULETA == "esperando":
            interaction.client.loop.create_task(motor_ruleta(interaction.client, interaction.channel, interaction.message))

class ViewRuletaStart(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Abir Mesa de Apuestas", style=discord.ButtonStyle.success, custom_id="btn_abrir_mesa", emoji="🎰")
    async def btn_mesa(self, interaction: discord.Interaction, button: discord.ui.Button): 
        hora_actual = (discord.utils.utcnow() - datetime.timedelta(hours=3)).hour
        roles_staff = obtener_config_list(interaction.guild.id, "ROLES_PARA_ADMIN_STAFF", ROLES_PARA_ADMIN_STAFF)
        roles_casino = obtener_config_list(interaction.guild.id, "ROLES_PERMITIDOS_CASINO", ROLES_PERMITIDOS_CASINO)
        es_staff = any(rol.id in roles_staff for rol in interaction.user.roles)
        tiene_rol = any(rol.id in roles_casino for rol in interaction.user.roles)

        if not es_staff:
            if not tiene_rol:
                return await interaction.response.send_message("⛔ **Acceso Denegado**: Tu rango no está autorizado.", ephemeral=True)
            if not (0 <= hora_actual < 2):
                return await interaction.response.send_message("🕒 **Cerrado**: Abre de **00:00 a 02:00 AM**.", ephemeral=True)

        await interaction.response.send_modal(ModalRuleta())


# ═══════════════════════════════════════════════════════════════════
#  MINIJUEGO 3: BLACKJACK 1v1 (MATCHMAKING COMPETITIVO)
# ═══════════════════════════════════════════════════════════════════

COLA_BJ_1V1 = []

class ViewBlackjack1v1(discord.ui.View):
    def __init__(self, p1: discord.Member, p2: discord.Member, apuesta: float):
        super().__init__(timeout=180) 
        self.p1 = p1
        self.p2 = p2
        self.apuesta = apuesta
        self.turno = p1 

        palos = ['♠️', '♥️', '♦️', '♣️']
        valores = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        self.baraja = [v + p for v in valores for p in palos]
        random.shuffle(self.baraja)

        self.mano_p1 = [self.baraja.pop(), self.baraja.pop()]
        self.mano_p2 = [self.baraja.pop(), self.baraja.pop()]

    def generar_embed(self, final=False):
        val_p1 = calcular_valor_blackjack(self.mano_p1)
        str_p1 = ", ".join(self.mano_p1)

        if not final and self.turno == self.p1:
            str_p2 = f"{self.mano_p2[0]}, ❓"
            val_p2 = "%s"
        else:
            str_p2 = ", ".join(self.mano_p2)
            val_p2 = calcular_valor_blackjack(self.mano_p2)

        color = discord.Color.blue() if self.turno == self.p1 else discord.Color.orange()
        if final: color = discord.Color.green()

        embed = discord.Embed(title=f"🃏 BLACKJACK 1v1", color=color)
        
        if final:
            embed.description = f"💰 **Pozo Total:** {self.apuesta * 2:.2f} coins\n🏁 **PARTIDA FINALIZADA**\n*(Este mensaje se borrará en 5 segundos)*"
        else:
            embed.description = f"💰 **Pozo Total:** {self.apuesta * 2:.2f} coins\n👉 **Turno actual:** {self.turno.mention}"

        embed.add_field(name=f"Cartas de {self.p1.display_name}", value=f"{str_p1}\n(Total: **{val_p1}**)", inline=True)
        embed.add_field(name=f"Cartas de {self.p2.display_name}", value=f"{str_p2}\n(Total: **{val_p2}**)", inline=True)
        return embed

    async def terminar_partida(self, interaction, ganador, perdedor, empate=False, razon=""):
        for child in self.children: child.disabled = True
        
        embed = self.generar_embed(final=True)
        
        if empate:
            embed.add_field(name="⚖️ RESULTADO: EMPATE", value="Ambos jugadores recuperan sus monedas.", inline=False)
            embed.color = discord.Color.light_grey()
            actualizar_coins(self.p1.id, self.apuesta, getattr(self, 'guild_id', None))
            actualizar_coins(self.p2.id, self.apuesta, getattr(self, 'guild_id', None))
        else:
            embed.add_field(name="🏆 RESULTADO: ¡TENEMOS GANADOR!", value=f"{ganador.mention} se lleva el pozo de **{self.apuesta * 2:.2f} coins**.\n*{razon}*", inline=False)
            actualizar_coins(ganador.id, self.apuesta * 2, getattr(self, 'guild_id', None))
            # Cambio para utils.core (Se envian dos logs, uno al ganador y uno al perdedor)
            await enviar_log(interaction.client, ganador, perdedor.id, self.apuesta, "blackjack", f"1v1 - Ganó contra {perdedor.display_name}")
            await enviar_log(interaction.client, perdedor, ganador.id, -self.apuesta, "blackjack", f"1v1 - Perdió contra {ganador.display_name}")

        await interaction.message.edit(embed=embed, view=self)
        
        await asyncio.sleep(5)
        try:
            await interaction.message.delete()
        except:
            pass 

    @discord.ui.button(label="Pedir Carta", style=discord.ButtonStyle.primary, emoji="🃏")
    async def pedir(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.turno.id:
            return await interaction.response.send_message("⏳ No es tu turno, espera que juegue tu oponente.", ephemeral=True)

        if self.turno == self.p1:
            self.mano_p1.append(self.baraja.pop())
            if calcular_valor_blackjack(self.mano_p1) > 21:
                return await self.terminar_partida(interaction, self.p2, self.p1, razon="¡El Jugador 1 se pasó de 21!")
        else:
            self.mano_p2.append(self.baraja.pop())
            if calcular_valor_blackjack(self.mano_p2) > 21:
                return await self.terminar_partida(interaction, self.p1, self.p2, razon="¡El Jugador 2 se pasó de 21!")

        await interaction.response.edit_message(embed=self.generar_embed(), view=self)

    @discord.ui.button(label="Plantarse", style=discord.ButtonStyle.secondary, emoji="🛑")
    async def plantarse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.turno.id:
            return await interaction.response.send_message("⏳ No es tu turno.", ephemeral=True)

        if self.turno == self.p1:
            self.turno = self.p2
            await interaction.response.edit_message(embed=self.generar_embed(), view=self)
        else:
            val_p1 = calcular_valor_blackjack(self.mano_p1)
            val_p2 = calcular_valor_blackjack(self.mano_p2)

            if val_p1 > val_p2:
                await self.terminar_partida(interaction, self.p1, self.p2, razon="Puntuación más alta.")
            elif val_p2 > val_p1:
                await self.terminar_partida(interaction, self.p2, self.p1, razon="Puntuación más alta.")
            else:
                await self.terminar_partida(interaction, None, None, empate=True)


class PanelBJ1v1(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Buscar Partida (0.25 Coins)", style=discord.ButtonStyle.success, emoji="⚔️", custom_id="btn_buscar_1v1")
    async def buscar(self, interaction: discord.Interaction, button: discord.ui.Button):
        hora_actual = (discord.utils.utcnow() - datetime.timedelta(hours=3)).hour
        roles_staff = obtener_config_list(interaction.guild.id, "ROLES_PARA_ADMIN_STAFF", ROLES_PARA_ADMIN_STAFF)
        roles_casino = obtener_config_list(interaction.guild.id, "ROLES_PERMITIDOS_CASINO", ROLES_PERMITIDOS_CASINO)
        es_staff = any(rol.id in roles_staff for rol in interaction.user.roles)
        tiene_rol = any(rol.id in roles_casino for rol in interaction.user.roles)

        if not es_staff:
            if not tiene_rol:
                return await interaction.response.send_message("⛔ **Acceso Denegado**: Tu rango no está autorizado para jugar en este lobby.", ephemeral=True)
            if not (0 <= hora_actual < 2):
                return await interaction.response.send_message("🕒 **Cerrado**: El lobby competitivo solo abre de **00:00 a 02:00 AM** (Hora Argentina).", ephemeral=True)

        apuesta_fija = 0.25
        saldo = obtener_coins(interaction.user.id, interaction.guild.id)
        
        if saldo < apuesta_fija:
            return await interaction.response.send_message(f"❌ No tienes suficientes coins. Necesitas al menos **{apuesta_fija}**.", ephemeral=True)

        global COLA_BJ_1V1
        
        if any(item["user"].id == interaction.user.id for item in COLA_BJ_1V1):
            return await interaction.response.send_message("⏳ Ya estás en la cola buscando partida.", ephemeral=True)

        while COLA_BJ_1V1:
            esperando = COLA_BJ_1V1.pop(0) 
            p1 = esperando["user"]
            mensaje_busqueda = esperando["mensaje"]
            
            try:
                await mensaje_busqueda.delete()
            except:
                pass
            
            if obtener_coins(p1.id, guild.id) >= apuesta_fija:
                p2 = interaction.user

                actualizar_coins(p1.id, -apuesta_fija, guild.id)
                actualizar_coins(p2.id, -apuesta_fija, guild.id)

                view_game = ViewBlackjack1v1(p1, p2, apuesta_fija)
                embed_game = view_game.generar_embed()
                
                await interaction.response.send_message(f"✅ ¡Partida encontrada con **{p1.display_name}**!", ephemeral=True)
                await interaction.channel.send(content=f"⚔️ **¡DUELO DE BLACKJACK!** {p1.mention} 🆚 {p2.mention}", embed=embed_game, view=view_game)
                return

        embed_anuncio = discord.Embed(
            description=f"🔍 **{interaction.user.display_name}** está buscando un oponente para apostar **{apuesta_fija} coins**.\n¡Toca el botón verde arriba para aceptar el reto!", 
            color=discord.Color.gold()
        )
        msg_publico = await interaction.channel.send(embed=embed_anuncio)
        
        COLA_BJ_1V1.append({"user": interaction.user, "mensaje": msg_publico})
        await interaction.response.send_message(f"🔍 Has entrado a la cola de espera. Todos pueden ver tu anuncio.", ephemeral=True)
    
    @discord.ui.button(label="Cancelar Búsqueda", style=discord.ButtonStyle.danger, emoji="❌", custom_id="btn_cancelar_1v1")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        global COLA_BJ_1V1
        
        encontrado = None
        for item in COLA_BJ_1V1:
            if item["user"].id == interaction.user.id:
                encontrado = item
                break
                
        if encontrado:
            COLA_BJ_1V1.remove(encontrado)
            try:
                await encontrado["mensaje"].delete()
            except:
                pass
            await interaction.response.send_message("🚫 Has salido de la cola de búsqueda y se eliminó tu anuncio.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ No estabas buscando ninguna partida.", ephemeral=True)


# ═══════════════════════════════════════════════════════════════════
#  INTEGRACIÓN AL COG PRINCIPAL
# ═══════════════════════════════════════════════════════════════════

class PanelCasino(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_load(self):
        # Registramos todas las vistas persistentes para que sigan funcionando si el bot se reinicia
        self.bot.add_view(BlackjackStartView())
        self.bot.add_view(ViewRuletaStart())
        self.bot.add_view(PanelBJ1v1())
        self.anuncio_apertura_casino.start()

    def cog_unload(self):
        self.anuncio_apertura_casino.cancel()

    def _es_staff(self, i: discord.Interaction) -> bool:
        if i.user.id == i.guild.owner_id or i.user.guild_permissions.administrator:
            return True
        roles_staff = obtener_config_list(i.guild.id, "ROLES_PARA_ADMIN_STAFF", [1351228669359558809, 1390055851657789481, 1411483502142029866])
        return any(r.id in roles_staff for r in i.user.roles)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingAnyRole): 
            await interaction.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)

    @app_commands.command(name="crearblackjack", description="Crea el panel de Blackjack vs Bot")
    async def crearblackjack(self, i: discord.Interaction):
        if not self._es_staff(i):
            return await i.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)
        embed = discord.Embed(
            title="🃏 CASINO CENTRAL - P.F.A", 
            description=(
                "Bienvenido al sistema de apuestas oficial.\n\n"
                "**Detalles del Juego:**\n"
                "🔹 **Apuesta:** 0.25 Coins\n"
                "🔹 **Premio:** x2.0 (x2.5 en Blackjack)\n\n"
                "🕒 **Horario de Apertura:**\n"
                "`00:00 a 02:00 AM` (Hora Argentina)\n\n"
                "⚠️ *Fuera de este horario, el acceso solo está permitido para mantenimiento por parte del Staff.*"
            ), 
            color=discord.Color.dark_purple()
        )
        embed.set_thumbnail(url="https://i.imgur.com/r6A4oXW.png") 
        embed.set_footer(text="La casa always gana... o quizás no.")

        await i.channel.send(embed=embed, view=BlackjackStartView())
        await i.response.send_message("✅ Panel del Casino desplegado correctamente.", ephemeral=True)


    @app_commands.command(name="crearruleta", description="Crea la mesa multijugador de la Ruleta Europea")
    async def crearruleta(self, i: discord.Interaction):
        if not self._es_staff(i):
            return await i.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)
        embed = discord.Embed(
            title="🎰 RULETA VIP - CASINO P.F.A",
            description=(
                "**¡Bienvenido a la mesa de alto riesgo multijugador!**\n\n"
                "Puedes hacer múltiples apuestas simultáneas. El panel indicará cuando las apuestas estén abiertas.\n\n"
                "**Límites de la Mesa:**\n"
                "💰 **Apuesta Base:** Máximo `0.10` por casilla.\n"
                "⚠️ **Apuestas Mayores:** Solo puedes superar los 0.10 totales si apuestas a **2 o más números** a la vez.\n\n"
                "**Tabla de Pagos:**\n"
                "🔴 ⚫ **Color Rojo/Negro** ➔ Paga **x2**\n"
                "🟢 🎯 **Cualquier Número (0-36)** ➔ Paga **x18**\n\n"
                "🕒 **Horario de Apertura:**\n"
                "`00:00 a 02:00 AM` (Hora Argentina)"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url="https://i.imgur.com/r6A4oXW.png") 
        embed.set_footer(text="💤 Mesa esperando apuestas... Toca el botón para iniciar.")
        
        await i.channel.send(embed=embed, view=ViewRuletaStart())
        await i.response.send_message("✅ Panel de Ruleta creado con sistema Multijugador.", ephemeral=True)


    @app_commands.command(name="panelbj1v1", description="Crea el lobby de emparejamiento para Blackjack 1v1")
    async def crearmatchmaking(self, i: discord.Interaction):
        if not self._es_staff(i):
            return await i.response.send_message("⛔ No tienes el rango necesario para usar este comando.", ephemeral=True)
        embed = discord.Embed(
            title="⚔️ LOBBY COMPETITIVO - BLACKJACK 1v1",
            description=(
                "¡Enfréntate a otros oficiales en un duelo de cartas!\n\n"
                "**¿Cómo funciona?**\n"
                "1️⃣ Toca el botón de `Buscar Partida`.\n"
                "2️⃣ El bot te pondrá en la lista de espera.\n"
                "3️⃣ Cuando otro oficial toque el botón, ¡empieza el duelo!\n\n"
                "🛑 *El ganador se lleva el pozo total de **0.50 Coins**.*\n"
                "⚖️ *Si empatan en puntos, se devuelven las monedas a ambos.*\n"
                "🧹 *Las partidas terminadas se borran a los 5 segundos para mantener el canal limpio.*\n\n"
                "🕒 **Horario de Apertura:**\n"
                "`00:00 a 02:00 AM` (Hora Argentina)"
            ),
            color=discord.Color.dark_grey()
        )
        embed.set_thumbnail(url="https://i.imgur.com/r6A4oXW.png") 
        
        await i.channel.send(embed=embed, view=PanelBJ1v1())
        await i.response.send_message("✅ Panel de Matchmaking creado.", ephemeral=True)


    @tasks.loop(time=datetime.time(hour=3, minute=0, tzinfo=datetime.timezone.utc))
    async def anuncio_apertura_casino(self):
        for guild in self.bot.guilds:
            canal_general_id = obtener_config_int(guild.id, "CANAL_GENERAL_ID", CANAL_GENERAL_ID)
            canal = guild.get_channel(canal_general_id)
            if not canal:
                continue

            rol_aviso_id = obtener_config_int(guild.id, "ROL_AVISO_CASINO", ROL_AVISO_CASINO)

            embed = discord.Embed(
                title="🎰 ¡EL CASINO P.F.A ESTÁ ABIERTO! 🎰",
                description=(
                    "Las puertas de las mesas VIP se han abierto oficialmente.\n\n"
                    "🕒 **Horario de Apuestas:** `00:00 a 02:00 AM` (Hora Arg)\n"
                    "💸 Acérquense a las mesas para jugar a la Ruleta y al Blackjack 1v1 antes de que cierre."
                ),
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_thumbnail(url="https://i.imgur.com/r6A4oXW.png")
            embed.set_footer(text="¡Buena suerte y jueguen con responsabilidad!")

            try:
                await canal.send(content=f"<@&{rol_aviso_id}> ¡Hagan sus apuestas!", embed=embed)
            except Exception as e:
                print(f"Error enviando anuncio del casino: {e}")

async def setup(bot): 
    await bot.add_cog(PanelCasino(bot))