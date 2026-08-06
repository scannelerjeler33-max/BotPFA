import discord
from discord.ext import commands
import os
from aiohttp import web
from dotenv import load_dotenv
from utils.core import ejecutar_mantenimiento_db

# Cargar variables de entorno
load_dotenv()

# Ejecutar creación de tablas y mantenimiento de la BD
ejecutar_mantenimiento_db()

# Configurar Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Inicializar el bot
bot = commands.Bot(command_prefix='!', intents=intents)


async def _iniciar_servidor_web() -> None:
    """
    Levanta un servidor HTTP mínimo para que Render detecte un puerto abierto
    (requisito de los Web Services) y para que un monitor externo (ej: UptimeRobot)
    pueda hacerle ping y mantener el servicio despierto.
    """
    app = web.Application()
    app.router.add_get("/", lambda request: web.Response(text="Bot PFA activo."))

    runner = web.AppRunner(app)
    await runner.setup()

    puerto = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", puerto)
    await site.start()
    print(f"🌐 Servidor de health check escuchando en el puerto {puerto}.")


@bot.event
async def setup_hook():
    await _iniciar_servidor_web()

    extensiones = [
        # --- PANELES ANTIGUOS ---
        "cogs.panel_gestion_pfa",
        "cogs.panel_farmeo",
        "cogs.panel_strikes",
        "cogs.panel_advertencias",
        "cogs.panel_cambionombre",
        "cogs.panel_gestion_halcon",
        "cogs.panel_gestion_ura",
        "cogs.sugerencias_setup",
        "cogs.lockdown",
        "logs.roles",
        "logs.voice",
        "cogs.panel_cupones",
        "cogs.panel_doble_faccion",
        "cogs.panel_limpieza",
        "cogs.panel_reinicio_sanciones",
        "cogs.panel_nuevo_ingresante",
        "cogs.panel_interviewer",
        "cogs.panel_encargado_interviewer",
        "cogs.panel_turnos",
        # --- TUS NUEVOS PANELES (BotCoins Separado) ---
        "cogs.panel_rrhh",
        "cogs.panel_operativo",
        "cogs.panel_economia",
        "cogs.panel_casino",
        "cogs.config_panel"
    ]

    for ext in extensiones:
        try:
            await bot.load_extension(ext)
            print(f"✅ Extensión {ext} cargada correctamente.")
        except Exception as e:
            print(f"❌ Error al cargar {ext}: {e}")

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')

    # Sincronización de Comandos — por servidor, independiente uno del otro.
    # Cada guild se sincroniza en su propio try/except: si uno falla (ej. el bot
    # no tiene el scope applications.commands ahí), no afecta a los demás.
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            print(f"🚀 Comandos sincronizados en el servidor: {guild.name} ({guild.id})")
        except Exception as e:
            print(f"❌ Error al sincronizar comandos en el servidor {guild.name} ({guild.id}): {e}")

    print(f"📡 Sistema Scanneler Economy totalmente operativo y estructurado en Cogs.")

# Iniciar Bot
TOKEN_SEGURO = os.getenv('DISCORD_TOKEN')
bot.run(TOKEN_SEGURO)