import discord
from discord.ext import commands
from discord import app_commands
import os
from databases.connection import get_connection
from utils.config import obtener_config_int

# Variables de entorno
ROL_PERMS = int(os.getenv("ROL_PERMS", "0"))
ROL_PANEL_ADMIN_ID = int(os.getenv("ROL_PANEL_ADMIN_ID", "0"))
ROL_DOBLE_FACCION_ID = int(os.getenv("ROL_DOBLE_FACCION_ID", "0") or 0)
CANAL_REGISTRO_DF_ID = int(os.getenv("CANAL_REGISTRO_DF_ID", "0") or 0)

# Base de datos
conn = get_connection()
conn.autocommit = True
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS doble_faccion_solicitudes (
        user_id BIGINT PRIMARY KEY,
        estado TEXT DEFAULT 'pendiente'
    )
""")


# --- MODAL: POSTULACIÓN ---
class ModalPostulacionDF(discord.ui.Modal, title="Postulación — Doble Facción"):
    nombre_ic = discord.ui.TextInput(
        label="Nombre IC",
        placeholder="Tu nombre en el roleplay...",
        max_length=50,
        required=True
    )
    organizacion = discord.ui.TextInput(
        label="Organización Criminal",
        placeholder="Nombre de la mafia u organización...",
        max_length=60,
        required=True
    )
    rango_org = discord.ui.TextInput(
        label="Rango en la organización",
        placeholder="Tu rango dentro de esa organización...",
        max_length=50,
        required=True
    )
    motivo = discord.ui.TextInput(
        label="Motivo de postulación",
        style=discord.TextStyle.paragraph,
        placeholder="¿Por qué querés acceder a la doble facción?",
        max_length=500,
        required=True
    )
    confirmacion = discord.ui.TextInput(
        label="Escribí ACEPTO si leíste las condiciones",
        placeholder="ACEPTO",
        max_length=10,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmacion.value.strip().upper() != "ACEPTO":
            return await interaction.response.send_message(
                "❌ Debés escribir **ACEPTO** en el campo de confirmación para enviar la solicitud.",
                ephemeral=True
            )

        canal_registro_id = obtener_config_int(interaction.guild.id, "CANAL_REGISTRO_DF_ID", CANAL_REGISTRO_DF_ID)
        canal = interaction.guild.get_channel(canal_registro_id)
        if not canal:
            return await interaction.response.send_message(
                "❌ Error: Canal de registro no configurado.", ephemeral=True
            )

        cursor.execute(
            "INSERT INTO doble_faccion_solicitudes (guild_id, user_id, estado) VALUES (%s, %s, 'pendiente') ON CONFLICT (guild_id, user_id) DO NOTHING", (interaction.guild.id, interaction.user.id)
        )

        embed = discord.Embed(
            title="📋 SOLICITUD DE DOBLE FACCIÓN",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="👤 Oficial", value=interaction.user.mention, inline=True)
        embed.add_field(name="🎭 Nombre IC", value=self.nombre_ic.value, inline=True)
        embed.add_field(name="🏴 Organización Criminal", value=self.organizacion.value, inline=True)
        embed.add_field(name="🎖️ Rango en la organización", value=self.rango_org.value, inline=True)
        embed.add_field(name="📝 Motivo", value=self.motivo.value, inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"ID:{interaction.user.id}")

        await canal.send(embed=embed, view=ViewRevisarPostulacionDF())
        await interaction.response.send_message(
            "✅ Tu solicitud fue enviada a Jefatura. Se te notificará por mensaje privado con la decisión.",
            ephemeral=True
        )


# --- MODAL: MOTIVO DE RECHAZO ---
class ModalRechazoDF(discord.ui.Modal):
    def __init__(self, message: discord.Message, user_id: int, embed: discord.Embed):
        super().__init__(title="Motivo de Rechazo")
        self.original_message = message
        self.user_id = user_id
        self.original_embed = embed
        self.motivo_input = discord.ui.TextInput(
            label="Motivo del rechazo",
            style=discord.TextStyle.paragraph,
            placeholder="Explicá el motivo del rechazo...",
            max_length=500,
            required=True
        )
        self.add_item(self.motivo_input)

    async def on_submit(self, interaction: discord.Interaction):
        cursor.execute("DELETE FROM doble_faccion_solicitudes WHERE user_id = %s AND guild_id = %s", (self.user_id, interaction.guild.id))

        embed = self.original_embed
        embed.title = "❌ DOBLE FACCIÓN RECHAZADA"
        embed.color = discord.Color.red()
        embed.add_field(name="👨‍⚖️ Rechazado por", value=interaction.user.mention, inline=False)
        embed.add_field(name="📋 Motivo", value=self.motivo_input.value, inline=False)
        embed.set_footer(text="Estado: Procesado (Rechazada)")
        await self.original_message.edit(embed=embed, view=None)

        miembro = interaction.guild.get_member(self.user_id)
        if miembro:
            try:
                await miembro.send(
                    f"❌ **Tu solicitud de Doble Facción fue RECHAZADA** por la administración.\n"
                    f"**Motivo:** {self.motivo_input.value}\n\n"
                    "Podés volver a postularte en el futuro si las condiciones cambian."
                )
            except Exception:
                pass

        await interaction.response.send_message("Solicitud rechazada correctamente.", ephemeral=True)


# --- VIEW: REVISIÓN DE POSTULACIÓN (STAFF) ---
class ViewRevisarPostulacionDF(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Aceptar", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_aceptar_df_v1")
    async def btn_aceptar(self, interaction: discord.Interaction, button: discord.ui.Button):
        rol_admin = obtener_config_int(interaction.guild.id, "ROL_PANEL_ADMIN_ID", ROL_PANEL_ADMIN_ID)
        if not any(r.id == rol_admin for r in interaction.user.roles):
            return await interaction.response.send_message(
                "⛔ No tenés permiso para aprobar solicitudes.", ephemeral=True
            )

        embed = interaction.message.embeds[0]
        if "Procesado" in embed.footer.text:
            return await interaction.response.send_message(
                "⚠️ Esta solicitud ya fue procesada.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        user_id = int(embed.footer.text.split(":")[1])
        cursor.execute(
            "UPDATE doble_faccion_solicitudes SET estado = 'aprobada' WHERE user_id = %s AND guild_id = %s", (user_id, interaction.guild.id)
        )

        miembro = interaction.guild.get_member(user_id)
        if miembro:
            try:
                rol_df_id = obtener_config_int(interaction.guild.id, "ROL_DOBLE_FACCION_ID", ROL_DOBLE_FACCION_ID)
                rol_df = interaction.guild.get_role(rol_df_id)
                if rol_df:
                    await miembro.add_roles(rol_df)
            except Exception as e:
                print(f"[DF] Error al asignar rol: {e}")

        embed.title = "✅ DOBLE FACCIÓN APROBADA"
        embed.color = discord.Color.green()
        embed.add_field(name="👨‍⚖️ Autorizado por", value=interaction.user.mention, inline=False)
        embed.set_footer(text="Estado: Procesado (Aceptada)")
        await interaction.message.edit(embed=embed, view=None)

        if miembro:
            try:
                await miembro.send(
                    "✅ **Tu solicitud de Doble Facción fue APROBADA.** Se te asignó el rol correspondiente.\n"
                    "Recordá cumplir con las horas de actividad requeridas y respetar la normativa."
                )
            except Exception:
                pass

        await interaction.followup.send("Solicitud aprobada correctamente.", ephemeral=True)

    @discord.ui.button(label="Rechazar", style=discord.ButtonStyle.danger, emoji="❌", custom_id="btn_rechazar_df_v1")
    async def btn_rechazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        rol_admin = obtener_config_int(interaction.guild.id, "ROL_PANEL_ADMIN_ID", ROL_PANEL_ADMIN_ID)
        if not any(r.id == rol_admin for r in interaction.user.roles):
            return await interaction.response.send_message(
                "⛔ No tenés permiso para rechazar solicitudes.", ephemeral=True
            )

        embed = interaction.message.embeds[0]
        if "Procesado" in embed.footer.text:
            return await interaction.response.send_message(
                "⚠️ Esta solicitud ya fue procesada.", ephemeral=True
            )

        user_id = int(embed.footer.text.split(":")[1])
        await interaction.response.send_modal(ModalRechazoDF(interaction.message, user_id, embed))


# --- VIEW: PANEL PÚBLICO ---
class ViewPanelDF(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Postular", style=discord.ButtonStyle.primary, emoji="📋", custom_id="btn_postular_df_v1")
    async def btn_postular(self, interaction: discord.Interaction, button: discord.ui.Button):
        rol_df_id = obtener_config_int(interaction.guild.id, "ROL_DOBLE_FACCION_ID", ROL_DOBLE_FACCION_ID)
        if any(r.id == rol_df_id for r in interaction.user.roles):
            return await interaction.response.send_message(
                "⚠️ Ya tenés la Doble Facción activa. Si querés renunciar, usá el botón **Revocar Doble Facción**.",
                ephemeral=True
            )

        cursor.execute(
            "SELECT estado FROM doble_faccion_solicitudes WHERE user_id = %s AND guild_id = %s", (interaction.user.id, interaction.guild.id)
        )
        resultado = cursor.fetchone()
        if resultado:
            if resultado[0] == "pendiente":
                return await interaction.response.send_message(
                    "⏳ Ya tenés una solicitud pendiente de revisión. Esperá la decisión de Jefatura.",
                    ephemeral=True
                )
            if resultado[0] == "aprobada":
                return await interaction.response.send_message(
                    "⚠️ Tu solicitud ya fue aprobada. Si no tenés el rol asignado, contactá a un superior.",
                    ephemeral=True
                )

        await interaction.response.send_modal(ModalPostulacionDF())

    @discord.ui.button(label="Revocar Doble Facción", style=discord.ButtonStyle.danger, emoji="🚪", custom_id="btn_revocar_df_v1")
    async def btn_revocar(self, interaction: discord.Interaction, button: discord.ui.Button):
        rol_df_id = obtener_config_int(interaction.guild.id, "ROL_DOBLE_FACCION_ID", ROL_DOBLE_FACCION_ID)
        if not any(r.id == rol_df_id for r in interaction.user.roles):
            return await interaction.response.send_message(
                "⚠️ No tenés la Doble Facción activa.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        try:
            rol_df = interaction.guild.get_role(rol_df_id)
            if rol_df:
                await interaction.user.remove_roles(rol_df)
        except Exception as e:
            print(f"[DF] Error al quitar rol: {e}")

        cursor.execute("DELETE FROM doble_faccion_solicitudes WHERE user_id = %s AND guild_id = %s", (interaction.user.id, interaction.guild.id))

        canal_registro_id = obtener_config_int(interaction.guild.id, "CANAL_REGISTRO_DF_ID", CANAL_REGISTRO_DF_ID)
        canal_registro = interaction.guild.get_channel(canal_registro_id)
        if canal_registro:
            log = discord.Embed(
                title="🚪 Baja — Doble Facción",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            log.add_field(name="👤 Oficial", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
            log.add_field(name="📋 Acción", value="Revocación voluntaria", inline=False)
            log.set_footer(text="Sistema Doble Facción — P.F.A")
            await canal_registro.send(embed=log)

        await interaction.followup.send(
            "✅ Tu condición de Doble Facción fue revocada exitosamente. Podés volver a postularte cuando quieras.",
            ephemeral=True
        )

    @discord.ui.button(label="Ver Activos (Head)", style=discord.ButtonStyle.secondary, emoji="👀", custom_id="btn_ver_activos_df_v1")
    async def btn_ver_activos(self, interaction: discord.Interaction, button: discord.ui.Button):
        es_staff = interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator
        rol_admin = obtener_config_int(interaction.guild.id, "ROL_PANEL_ADMIN_ID", ROL_PANEL_ADMIN_ID)
        rol_perms = obtener_config_int(interaction.guild.id, "ROL_PERMS", ROL_PERMS)
        if not (es_staff or any(r.id in (rol_admin, rol_perms) for r in interaction.user.roles)):
            return await interaction.response.send_message(
                "⛔ No tenés permiso para ver la lista de activos.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        cursor.execute("SELECT user_id FROM doble_faccion_solicitudes WHERE guild_id = %s AND estado = 'aprobada'", (interaction.guild.id,))
        resultados = cursor.fetchall()

        if not resultados:
            return await interaction.followup.send(
                "📭 Actualmente no hay ningún oficial con la Doble Facción aprobada.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="👥 Oficiales con Doble Facción Activa",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow()
        )

        lista = ""
        for (uid,) in resultados:
            lista += f"• <@{uid}> (`{uid}`)\n"

        if len(lista) > 4000:
            lista = lista[:3900] + "\n... (lista truncada)"

        embed.description = lista
        embed.set_footer(text=f"Total: {len(resultados)} oficiales")

        await interaction.followup.send(embed=embed, ephemeral=True)


# --- COG ---
class PanelDobleFaccion(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_load(self) -> None:
        self.bot.add_view(ViewPanelDF())
        self.bot.add_view(ViewRevisarPostulacionDF())

    @app_commands.command(name="crearpaneldf", description="Despliega el panel de postulación a Doble Facción.")
    async def crearpaneldf(self, interaction: discord.Interaction):
        es_staff = interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator
        rol_perms = obtener_config_int(interaction.guild.id, "ROL_PERMS", ROL_PERMS)
        if not (es_staff or any(r.id == rol_perms for r in interaction.user.roles)):
            return await interaction.response.send_message(
                "⛔ No tenés permiso para usar este comando.", ephemeral=True
            )

        canal_normativa_df_id = obtener_config_int(interaction.guild.id, "CANAL_NORMATIVA_DF_ID", 1502500311263346738)
        embed = discord.Embed(
            title="⚖️ SISTEMA DE DOBLE FACCIÓN — P.F.A",
            description=(
                "Este sistema permite pertenecer simultáneamente a la **P.F.A** y a una organización criminal, "
                "siempre respetando las normativas establecidas.\n\n"
                "**La doble facción NO es un derecho, es un beneficio revocable.**\n\n"
                "**Normativa general:**\n"
                f" Es completamente necesario leer la normativa dentro de: https://discord.com/channels/{interaction.guild.id}/{canal_normativa_df_id}\n"
                " No podés participar desde PFA en situaciones vinculadas a tu mafia.\n\n"
                "*Todo mal uso conllevará una grave sanción e inhabilitación permanente del beneficio.*"
            ),
            color=discord.Color.dark_gold()
        )
        embed.set_footer(text="Sistema Doble Facción — P.F.A")

        await interaction.channel.send(embed=embed, view=ViewPanelDF())
        await interaction.response.send_message("✅ Panel de Doble Facción desplegado.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(PanelDobleFaccion(bot))