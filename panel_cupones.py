import discord
from discord.ext import commands
from discord import app_commands
import os
import datetime
from utils.core import cursor, conn

# --- VARIABLES DE ENTORNO ---
ROL_PANEL_ADMIN_ID = int(os.getenv("ROL_PANEL_ADMIN_ID", "0"))
ROL_PERMS = int(os.getenv("ROL_PERMS", "0"))
CANAL_ADVERTENCIAS_ID = int(os.getenv("CANAL_ADVERTENCIAS_ID", "0"))
CANAL_STRIKES_ID = int(os.getenv("CANAL_STRIKES_ID", "0"))
CANAL_LOGS_CUPONES_ID = int(os.getenv("CANAL_LOGS_CUPONES_ID", "0") or 0)

def tiene_permiso_staff(miembro: discord.Member) -> bool:
    permitidos = {ROL_PANEL_ADMIN_ID, ROL_PERMS}
    return any(rol.id in permitidos for rol in miembro.roles)

# --- INICIALIZACIÓN DE TABLA ---
cursor.execute("""
    CREATE TABLE IF NOT EXISTS cupones_usuario (
        user_id BIGINT,
        tipo_cupon TEXT,
        cantidad INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, tipo_cupon)
    )
""")
conn.commit()

# --- FUNCIONES DE BASE DE DATOS ---
def obtener_cupones(user_id):
    cursor.execute("SELECT tipo_cupon, cantidad FROM cupones_usuario WHERE user_id = %s", (user_id,))
    return cursor.fetchall()

def obtener_cantidad_cupon(user_id, tipo_cupon):
    cursor.execute("SELECT cantidad FROM cupones_usuario WHERE user_id = %s AND tipo_cupon = %s", (user_id, tipo_cupon))
    resultado = cursor.fetchone()
    return resultado[0] if resultado else 0

def modificar_cupones(user_id, tipo_cupon, cantidad):
    cursor.execute("""
        INSERT INTO cupones_usuario (user_id, tipo_cupon, cantidad)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, tipo_cupon) 
        DO UPDATE SET cantidad = GREATEST(0, cupones_usuario.cantidad + %s)
    """, (user_id, tipo_cupon, cantidad, cantidad))
    conn.commit()

# --- HELPER: LOG DE CUPONES ---
async def enviar_log_cupon(bot, tipo: str, admin=None, usuario=None, tipo_cupon: str = "", cantidad: int = 0, saldo_nuevo: int = 0, id_sancion: str = "", item_comprado: str = ""):
    canal = bot.get_channel(CANAL_LOGS_CUPONES_ID)
    if not canal:
        return

    if tipo_cupon == "strike":
        tipo_display = "Quitar Strike"
    elif tipo_cupon == "advertencia":
        tipo_display = "Quitar Advertencia"
    elif tipo_cupon == "promote_faccionario":
        tipo_display = "Promote Faccionario"
    else:
        tipo_display = tipo_cupon.replace("_", " ").title()

    admin_display = admin.mention if hasattr(admin, "mention") else (str(admin) if admin else "Sistema")
    usuario_display = usuario.mention if hasattr(usuario, "mention") else (str(usuario) if usuario else "Desconocido")

    if tipo == "dar":
        embed = discord.Embed(title="🎟️ Cupón Entregado", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        embed.add_field(name="👮 Administrador", value=admin_display, inline=True)
        embed.add_field(name="👤 Usuario", value=usuario_display, inline=True)
        embed.add_field(name="🎟️ Tipo", value=tipo_display, inline=True)
        embed.add_field(name="📦 Cantidad entregada", value=f"`{cantidad}`", inline=True)
        embed.add_field(name="💼 Saldo nuevo", value=f"`{saldo_nuevo}`", inline=True)

    elif tipo == "quitar":
        embed = discord.Embed(title="🎟️ Cupón Retirado", color=discord.Color.red(), timestamp=discord.utils.utcnow())
        embed.add_field(name="👮 Administrador", value=admin_display, inline=True)
        embed.add_field(name="👤 Usuario", value=usuario_display, inline=True)
        embed.add_field(name="🎟️ Tipo", value=tipo_display, inline=True)
        embed.add_field(name="📦 Cantidad retirada", value=f"`{cantidad}`", inline=True)
        embed.add_field(name="💼 Saldo restante", value=f"`{saldo_nuevo}`", inline=True)

    elif tipo == "canjear":
        embed = discord.Embed(title="🔄 Cupón Canjeado", color=discord.Color.gold(), timestamp=discord.utils.utcnow())
        embed.add_field(name="👤 Usuario", value=usuario_display, inline=True)
        embed.add_field(name="🎟️ Tipo", value=tipo_display, inline=True)
        if id_sancion:
            embed.add_field(name="🆔 ID sanción eliminada", value=f"`{id_sancion}`", inline=True)
        embed.add_field(name="💼 Cupones restantes", value=f"`{saldo_nuevo}`", inline=True)

    elif tipo == "shop":
        embed = discord.Embed(title="🛒 Cupón Generado por Shop", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
        embed.add_field(name="👤 Usuario", value=usuario_display, inline=True)
        embed.add_field(name="🛍️ Item comprado", value=item_comprado, inline=True)
        embed.add_field(name="🎟️ Cupón otorgado", value=tipo_display, inline=True)

    else:
        return

    embed.set_footer(text="Sistema de Cupones — P.F.A")
    await canal.send(embed=embed)


# ═══════════════════════════════════════════════════════════════════
#  MODALES Y VISTAS
# ═══════════════════════════════════════════════════════════════════

# --- MODAL: CANJEAR CUPÓN (PIDE EL ID DE LA SANCIÓN) ---
class ModalCanjearCupon(discord.ui.Modal):
    def __init__(self, tipo_cupon):
        self.tipo_cupon = tipo_cupon
        super().__init__(title=f"Canjear Cupón: Quitar {tipo_cupon.capitalize()}")

    id_sancion = discord.ui.TextInput(
        label="ID de la Sanción",
        placeholder="Ingresa el ID exacto de la sanción...",
        min_length=1,
        max_length=20,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        sancion_id = self.id_sancion.value.strip()
        user_id = interaction.user.id

        # Verificar si aún tiene el cupón
        cantidad = obtener_cantidad_cupon(user_id, self.tipo_cupon)
        if cantidad <= 0:
            return await interaction.response.send_message("❌ Ya no tienes cupones de este tipo.", ephemeral=True)

        motivo_canje = f"Canjeado mediante Cupón por {interaction.user.display_name}"
        ahora_str = discord.utils.utcnow().strftime("%d/%m/%Y %H:%M:%S")

        await interaction.response.defer(ephemeral=True)

        if self.tipo_cupon == "strike":
            cursor.execute("SELECT strike_id FROM strikes WHERE strike_id = %s AND user_id = %s", (sancion_id, user_id))
            if not cursor.fetchone():
                return await interaction.followup.send(f"❌ No se encontró tu Strike con ID `{sancion_id}`.", ephemeral=True)
            
            # Eliminar y guardar historial
            cursor.execute("DELETE FROM strikes WHERE strike_id = %s", (sancion_id,))
            cursor.execute("""
                INSERT INTO strikes_historial (strike_id, user_id, razon, admin_id, fecha, accion, motivo_eliminacion) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (sancion_id, user_id, "Eliminado por cupón", interaction.user.id, ahora_str, "Eliminar", motivo_canje))
            
            cursor.execute("SELECT COUNT(*) FROM strikes WHERE user_id = %s", (user_id,))
            restantes = cursor.fetchone()[0]
            conn.commit()

            canal = interaction.guild.get_channel(CANAL_STRIKES_ID)
            if canal:
                embed = discord.Embed(title=f"🎟️ Strike Eliminado por Cupón ({restantes}/3)", color=discord.Color.brand_green())
                embed.description = f"**Strike ID:** {sancion_id}\n**Usuario:** <@{user_id}>\n**Motivo:** {motivo_canje}\n**Fecha:** {ahora_str}"
                await canal.send(embed=embed)

        elif self.tipo_cupon == "advertencia":
            cursor.execute("SELECT warn_id FROM advertencias WHERE warn_id = %s AND user_id = %s", (sancion_id, user_id))
            if not cursor.fetchone():
                return await interaction.followup.send(f"❌ No se encontró tu Advertencia con ID `{sancion_id}`.", ephemeral=True)
            
            # Eliminar y guardar historial
            cursor.execute("DELETE FROM advertencias WHERE warn_id = %s", (sancion_id,))
            cursor.execute("""
                INSERT INTO advertencias_historial (warn_id, user_id, razon, admin_id, fecha, accion, motivo_eliminacion) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (sancion_id, user_id, "Eliminado por cupón", interaction.user.id, ahora_str, "Eliminar", motivo_canje))
            
            cursor.execute("SELECT COUNT(*) FROM advertencias WHERE user_id = %s", (user_id,))
            restantes = cursor.fetchone()[0]
            conn.commit()

            canal = interaction.guild.get_channel(CANAL_ADVERTENCIAS_ID)
            if canal:
                embed = discord.Embed(title=f"🎟️ Advertencia Eliminada por Cupón ({restantes}/3)", color=discord.Color.brand_green())
                embed.description = f"**Warn ID:** {sancion_id}\n**Usuario:** <@{user_id}>\n**Motivo:** {motivo_canje}\n**Fecha:** {ahora_str}"
                await canal.send(embed=embed)

        # Consumir el cupón
        modificar_cupones(user_id, self.tipo_cupon, -1)
        saldo_restante = obtener_cantidad_cupon(user_id, self.tipo_cupon)
        
        await enviar_log_cupon(
            interaction.client,
            tipo="canjear",
            usuario=interaction.user,
            tipo_cupon=self.tipo_cupon,
            saldo_nuevo=saldo_restante,
            id_sancion=sancion_id
        )
        
        await interaction.followup.send(f"✅ **¡Canje Exitoso!**\nSe ha eliminado tu sanción y consumiste 1 cupón de {self.tipo_cupon}.", ephemeral=True)


# --- MENÚ DESPLEGABLE: ELEGIR QUÉ CUPÓN USAR ---
class SelectCupon(discord.ui.Select):
    def __init__(self):
        opciones = [
            discord.SelectOption(label="Quitar Advertencia", value="advertencia", emoji="⚠️", description="Consume 1 cupón de Advertencia"),
            discord.SelectOption(label="Quitar Strike", value="strike", emoji="🚨", description="Consume 1 cupón de Strike"),
            discord.SelectOption(label="Promote Faccionario", value="promote_faccionario", emoji="🏅", description="Consume 1 cupón de Promote Faccionario")
        ]
        super().__init__(placeholder="Selecciona el cupón que deseas usar...", min_values=1, max_values=1, options=opciones, custom_id="select_cupon_v2")

    async def callback(self, interaction: discord.Interaction):
        tipo_seleccionado = self.values[0]
        cantidad = obtener_cantidad_cupon(interaction.user.id, tipo_seleccionado)
        
        if cantidad <= 0:
            tipo_display = tipo_seleccionado.replace("_", " ")
            return await interaction.response.send_message(f"❌ No tienes cupones de **{tipo_display}** para canjear.", ephemeral=True)
            
        if tipo_seleccionado == "promote_faccionario":
            await interaction.response.defer(ephemeral=True)
            
            # Importación dinámica de helpers de ascenso faccionario
            from cogs.panel_gestion_pfa import _rango_actual, _cambiar_rango, JERARQUIA_PFA, _detalle_cambio_tier, _enviar_log
            
            miembro = interaction.user
            actual = _rango_actual(miembro)
            if actual is None:
                return await interaction.followup.send("❌ No tienes un rango PFA activo para poder ser ascendido.", ephemeral=True)
                
            if actual.nivel >= len(JERARQUIA_PFA) - 1:
                return await interaction.followup.send("❌ Ya has alcanzado el rango máximo en la PFA.", ephemeral=True)
                
            destino = JERARQUIA_PFA[actual.nivel + 1]
            motivo_canje = "Canjeado mediante Cupón de Ascenso Faccionario"
            
            ok, error = await _cambiar_rango(
                miembro,
                destino,
                reason=f"Ascenso por Cupón de Promote Faccionario: {motivo_canje}",
            )
            if not ok:
                return await interaction.followup.send(f"❌ {error}", ephemeral=True)
                
            # Consumir el cupón
            modificar_cupones(interaction.user.id, "promote_faccionario", -1)
            saldo_restante = obtener_cantidad_cupon(interaction.user.id, "promote_faccionario")
            
            # Log de cupones
            await enviar_log_cupon(
                bot=interaction.client,
                tipo="canjear",
                usuario=interaction.user,
                tipo_cupon="promote_faccionario",
                saldo_nuevo=saldo_restante
            )
            
            # Log en el canal de auditoría de PFA
            cambio_tier = _detalle_cambio_tier(actual, destino)
            await _enviar_log(
                interaction,
                "Ascenso de rango PFA (CUPÓN)",
                miembro,
                (
                    f"🎖️ **Rango:** `[{actual.nivel:02}] {actual.nombre}` → "
                    f"`[{destino.nivel:02}] {destino.nombre}`\n"
                    f"📈 **Niveles ascendidos:** 1"
                    f"{cambio_tier}\n"
                    f"📝 **Motivo:** {motivo_canje}"
                ),
                "⭐",
            )
            
            await interaction.followup.send(
                f"✅ **¡Canje Exitoso!**\n"
                f"Has sido ascendido a **{destino.nombre}** (`[{destino.nivel:02}]`).\n"
                f"Consumiste 1 cupón de Promote Faccionario (restantes: `{saldo_restante}`).",
                ephemeral=True
            )
        else:
            await interaction.response.send_modal(ModalCanjearCupon(tipo_seleccionado))


class ViewSelectCupon(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Timeout=None para que no se congele a los 2 minutos
        self.add_item(SelectCupon())


# --- VISTA PRINCIPAL: EL PANEL ---
class ViewPanelCupones(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ver mis cupones", style=discord.ButtonStyle.secondary, emoji="🎟️", custom_id="btn_ver_cupones_v2")
    async def btn_ver(self, interaction: discord.Interaction, button: discord.ui.Button):
        cupones = obtener_cupones(interaction.user.id)
        
        tiene_cupones = any(cant > 0 for _, cant in cupones)
        if not cupones or not tiene_cupones:
            return await interaction.response.send_message("📭 Actualmente no tienes ningún cupón en tu inventario.", ephemeral=True)

        desc = ""
        for tipo, cant in cupones:
            if cant > 0:
                if tipo == "strike":
                    emoji = "🚨"
                    nombre = "Cupón Quitar Strike"
                elif tipo == "advertencia":
                    emoji = "⚠️"
                    nombre = "Cupón Quitar Advertencia"
                elif tipo == "promote_faccionario":
                    emoji = "🏅"
                    nombre = "Cupón Promote Faccionario"
                else:
                    emoji = "🎟️"
                    nombre = f"Cupón {tipo.replace('_', ' ').title()}"
                desc += f"{emoji} **{nombre}:** `{cant}` disponibles\n"

        embed = discord.Embed(title="🎟️ Inventario de Cupones", description=desc, color=discord.Color.gold())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Canjear cupón", style=discord.ButtonStyle.success, emoji="🔄", custom_id="btn_canjear_cupones_v2")
    async def btn_canjear(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("¿Qué tipo de cupón deseas utilizar?", view=ViewSelectCupon(), ephemeral=True)


# ═══════════════════════════════════════════════════════════════════
#  COG PRINCIPAL Y COMANDOS ADMIN
# ═══════════════════════════════════════════════════════════════════

class PanelCupones(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_load(self):
        # Es fundamental registrar TODAS las vistas (incluyendo el submenú de canje)
        self.bot.add_view(ViewPanelCupones())
        self.bot.add_view(ViewSelectCupon())

    @app_commands.command(name="panelcupones", description="Despliega el panel interactivo de Cupones.")
    async def panelcupones(self, interaction: discord.Interaction):
        if not tiene_permiso_staff(interaction.user):
            return await interaction.response.send_message("⛔ No tienes permiso.", ephemeral=True)

        embed = discord.Embed(
            title="🎟️ SISTEMA DE CUPONES - P.F.A",
            description=(
                "Bienvenido al sistema de canje de cupones oficiales.\n\n"
                "**Opciones Disponibles:**\n"
                "👀 **Ver mis cupones:** Revisa tu inventario actual.\n"
                "🔄 **Canjear cupón:** Usa un cupón para eliminar un Strike/Advertencia o aplicar un Ascenso Faccionario.\n\n"
                "⚠️ *Para eliminar sanciones (Strike/Advertencia) necesitarás tener a mano el ID de la sanción. Los ascensos se procesan inmediatamente.*"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url="https://i.imgur.com/r6A4oXW.png")
        await interaction.channel.send(embed=embed, view=ViewPanelCupones())
        await interaction.response.send_message("✅ Panel desplegado.", ephemeral=True)

    @app_commands.command(name="darcupon", description="[STAFF] Otorga un cupón a un oficial de forma manual.")
    @app_commands.describe(usuario="El oficial que recibe el cupón", tipo="Tipo de cupón a dar", cantidad="Cantidad a dar (Por defecto: 1)")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Quitar Strike", value="strike"),
        app_commands.Choice(name="Quitar Advertencia", value="advertencia"),
        app_commands.Choice(name="Promote Faccionario", value="promote_faccionario")
    ])
    async def darcupon(self, interaction: discord.Interaction, usuario: discord.Member, tipo: str, cantidad: int = 1):
        if not tiene_permiso_staff(interaction.user):
            return await interaction.response.send_message("⛔ No tienes permiso para usar este comando.", ephemeral=True)

        if cantidad <= 0:
            return await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)

        modificar_cupones(usuario.id, tipo, cantidad)
        saldo_nuevo = obtener_cantidad_cupon(usuario.id, tipo)
        
        await enviar_log_cupon(
            bot=interaction.client,
            tipo="dar",
            admin=interaction.user,
            usuario=usuario,
            tipo_cupon=tipo,
            cantidad=cantidad,
            saldo_nuevo=saldo_nuevo
        )
        await interaction.response.send_message(f"✅ Se han entregado **{cantidad} cupón/es de '{tipo}'** a {usuario.mention} correctamente.", ephemeral=True)

    @app_commands.command(name="quitarcupon", description="[STAFF] Retira cupones del inventario de un oficial.")
    @app_commands.describe(usuario="El oficial al que se le retira", tipo="Tipo de cupón a quitar", cantidad="Cantidad a quitar (Por defecto: 1)")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Quitar Strike", value="strike"),
        app_commands.Choice(name="Quitar Advertencia", value="advertencia"),
        app_commands.Choice(name="Promote Faccionario", value="promote_faccionario")
    ])
    async def quitarcupon(self, interaction: discord.Interaction, usuario: discord.Member, tipo: str, cantidad: int = 1):
        if not tiene_permiso_staff(interaction.user):
            return await interaction.response.send_message("⛔ No tienes permiso para usar este comando.", ephemeral=True)

        if cantidad <= 0:
            return await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)

        cupones_actuales = obtener_cantidad_cupon(usuario.id, tipo)
        if cupones_actuales < cantidad:
            return await interaction.response.send_message(f"❌ No puedes quitarle {cantidad} cupones. El usuario solo tiene **{cupones_actuales}**.", ephemeral=True)

        modificar_cupones(usuario.id, tipo, -cantidad)
        saldo_nuevo = obtener_cantidad_cupon(usuario.id, tipo)
        
        await enviar_log_cupon(
            bot=interaction.client,
            tipo="quitar",
            admin=interaction.user,
            usuario=usuario,
            tipo_cupon=tipo,
            cantidad=cantidad,
            saldo_nuevo=saldo_nuevo
        )
        await interaction.response.send_message(f"➖ Se han retirado **{cantidad} cupón/es de '{tipo}'** a {usuario.mention}.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(PanelCupones(bot))