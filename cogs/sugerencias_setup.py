import discord
from discord.ext import commands
from utils.config import obtener_config_int

# Usado como fallback si el servidor no configuró nada con /configuracion
CANAL_SUGERENCIAS_ID = 1466908459780935852

class Sugerencias(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1. Ignorar mensajes de bots
        if message.author.bot:
            return
            
        # 2. Verificar que el mensaje sea en el canal de sugerencias
        if message.guild is None:
            return
        canal_sugerencias_id = obtener_config_int(message.guild.id, "CANAL_SUGERENCIAS_ID", CANAL_SUGERENCIAS_ID)
        if message.channel.id != canal_sugerencias_id:
            return
            
        # 3. Borrar el mensaje original para mantener el canal limpio
        try:
            await message.delete()
        except discord.Forbidden:
            print("El bot no tiene permisos para borrar mensajes en el canal de sugerencias.")
            return
        except discord.NotFound:
            pass # El mensaje ya fue borrado

        # 4. Obtener datos del usuario para el embed
        # Buscar el rol más alto que contenga el emoji de policía
        rango_usuario = "Oficial" # Valor por defecto
        # message.author.roles está ordenado de menor a mayor jerarquía
        for rol in reversed(message.author.roles):
            if "👮" in rol.name:
                rango_usuario = rol.name
                break

        # 5. Crear el embed amarillo de diseño UX/UI
        embed = discord.Embed(
            title="💡 NUEVA SUGERENCIA",
            description=f"**Sugerencia:**\n{message.content}",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        
        # Autor con foto y tag
        embed.set_author(
            name=f"Propuesta por {message.author.display_name} ({message.author.name})",
            icon_url=message.author.display_avatar.url
        )
        
        # Campo con el rango
        embed.add_field(name="Rango / Posición", value=f"`{rango_usuario}`", inline=False)
        
        # Footer profesional
        embed.set_footer(text="Sistema de Sugerencias - P.F.A", icon_url=self.bot.user.display_avatar.url if self.bot.user else None)

        # 6. Enviar el embed al canal
        mensaje_embed = await message.channel.send(embed=embed)

        # 7. Añadir reacciones (Checkmark y Cruz)
        try:
            await mensaje_embed.add_reaction("✅")
            await mensaje_embed.add_reaction("❌")
        except discord.Forbidden:
            print("Faltan permisos para añadir reacciones.")

        # 8. Crear un hilo (Thread) vinculado al mensaje para debate
        try:
            nombre_hilo = f"Debate: Sugerencia de {message.author.display_name}"
            # Acortamos el nombre si es muy largo (Discord permite hasta 100 caracteres)
            if len(nombre_hilo) > 100:
                nombre_hilo = nombre_hilo[:97] + "..."
            
            await mensaje_embed.create_thread(
                name=nombre_hilo,
                auto_archive_duration=10080 # 7 días (10080 minutos)
            )
        except discord.Forbidden:
            print("Faltan permisos para crear hilos públicos.")
        except Exception as e:
            print(f"Error al crear el hilo de sugerencias: {e}")

async def setup(bot):
    await bot.add_cog(Sugerencias(bot))
