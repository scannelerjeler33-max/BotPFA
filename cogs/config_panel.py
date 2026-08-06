import discord
from discord.ext import commands
from discord import app_commands
from utils.config import obtener_config, establecer_config, obtener_config_int, obtener_config_list

class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Canales", value="canales", emoji="💬", description="Configura canales de logs, misiones, robos, etc."),
            discord.SelectOption(label="Roles Base / PFA", value="roles_base", emoji="🛡️", description="Roles de base PFA, Tiers, Cadete, Blacklist, etc."),
            discord.SelectOption(label="Roles Staff / Economía", value="roles_staff", emoji="👮", description="Configura roles de administración y coins."),
            discord.SelectOption(label="Roles Subdivisiones", value="roles_subdivs", emoji="👥", description="Roles pertenecientes a URA, Halcón, PDI, etc."),
            discord.SelectOption(label="Rangos PFA (Jerarquía)", value="rangos_pfa", emoji="🎖️", description="Configura los 34 rangos de la jerarquía PFA."),
            discord.SelectOption(label="Subdivisiones (URA / Halcón)", value="subdivs_gestion", emoji="✈️", description="Configura URA y Halcón (roles, logs, rangos)."),
            discord.SelectOption(label="Oposiciones / Interviewer", value="interviewer_gestion", emoji="📝", description="Configura canales, roles de postulaciones e interviewers."),
            discord.SelectOption(label="RRHH (Bajas / Ausencias)", value="rrhh_gestion", emoji="🧑‍💼", description="Canales y roles para bajas y licencias temporales."),
            discord.SelectOption(label="Cambio de Nombre", value="cambionombre_gestion", emoji="✏️", description="Canal y roles del sistema de cambio de nombre."),
            discord.SelectOption(label="Doble Facción", value="dobleFaccion_gestion", emoji="⚖️", description="Canal, rol y normativa de doble facción."),
            discord.SelectOption(label="Casino y Sugerencias", value="casino_sugerencias_gestion", emoji="🎰", description="Roles del casino y canal de sugerencias."),
            discord.SelectOption(label="Logs del Sistema", value="logs_gestion", emoji="🗒️", description="Canales de logs de roles, voz y propietario de logs."),
            discord.SelectOption(label="Turnos y Farmeo", value="turnos_farmeo_gestion", emoji="🕒", description="Canal de turnos y roles de Farmero.")
        ]
        super().__init__(placeholder="Elige una categoría de configuración...", options=options, custom_id="cfg_category_select")

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        
        if val == "canales":
            view.add_item(ChannelSettingSelect())
            embed = discord.Embed(
                title="⚙️ Configuración: Canales",
                description="Selecciona la variable de canal que deseas configurar abajo y luego elige el canal correspondiente.",
                color=discord.Color.blue()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        elif val == "roles_base":
            view.add_item(RoleBaseSettingSelect())
            embed = discord.Embed(
                title="⚙️ Configuración: Roles Base / PFA",
                description="Selecciona el rol base que deseas configurar y luego elígelo de la lista.",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        elif val == "roles_staff":
            view.add_item(RoleStaffSettingSelect())
            embed = discord.Embed(
                title="⚙️ Configuración: Roles Staff & Economía",
                description="Selecciona la variable de staff que deseas configurar y luego elígelo de la lista.",
                color=discord.Color.orange()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        elif val == "roles_subdivs":
            view.add_item(RoleSubdivsSettingSelect())
            embed = discord.Embed(
                title="⚙️ Configuración: Roles de Subdivisiones",
                description="Configura los roles permitidos para las subdivisiones (URA, Halcón, PDI) y cobro de robos.",
                color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        elif val == "rangos_pfa":
            view.add_item(RangoTierSelect())
            embed = discord.Embed(
                title="⚙️ Configuración: Jerarquía PFA",
                description="Selecciona el tier de la jerarquía que contiene los rangos que deseas configurar.",
                color=discord.Color.dark_teal()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        elif val == "subdivs_gestion":
            view.add_item(SubdivsSettingSelect())
            embed = discord.Embed(
                title="⚙️ Configuración: URA / Halcón",
                description="Ajusta los canales de logs, roles bases, tiers y jerarquías de URA y Halcón.",
                color=discord.Color.dark_magenta()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        elif val == "interviewer_gestion":
            view.add_item(InterviewerSettingSelect())
            embed = discord.Embed(
                title="⚙️ Configuración: Oposiciones / Interviewer",
                description="Configura canales de postulaciones, roles de interviewers y canales de bienvenida de ingresantes.",
                color=discord.Color.dark_blue()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        elif val == "rrhh_gestion":
            view.add_item(RRHHSettingSelect())
            embed = discord.Embed(
                title="⚙️ Configuración: RRHH (Bajas / Ausencias)",
                description="Configura los canales y roles de las solicitudes de baja y de licencia temporal.",
                color=discord.Color.dark_orange()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        elif val == "cambionombre_gestion":
            view.add_item(CambioNombreSettingSelect())
            embed = discord.Embed(
                title="⚙️ Configuración: Cambio de Nombre",
                description="Configura el canal de aprobación y los roles del sistema de cambio de nombre.",
                color=discord.Color.blurple()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        elif val == "dobleFaccion_gestion":
            view.add_item(DobleFaccionSettingSelect())
            embed = discord.Embed(
                title="⚙️ Configuración: Doble Facción",
                description="Configura el canal de registro, el rol de doble facción y el canal con la normativa.",
                color=discord.Color.dark_gold()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        elif val == "casino_sugerencias_gestion":
            view.add_item(CasinoSugerenciasSettingSelect())
            embed = discord.Embed(
                title="⚙️ Configuración: Casino y Sugerencias",
                description="Configura el rol de aviso del casino, los roles permitidos y el canal de sugerencias.",
                color=discord.Color.gold()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        elif val == "logs_gestion":
            view.add_item(LogsSettingSelect())
            embed = discord.Embed(
                title="⚙️ Configuración: Logs del Sistema",
                description="Configura los canales de logs de roles, voz y el usuario propietario que recibe alertas de logs eliminados.",
                color=discord.Color.dark_grey()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        elif val == "turnos_farmeo_gestion":
            view.add_item(TurnosFarmeoSettingSelect())
            embed = discord.Embed(
                title="⚙️ Configuración: Turnos y Farmeo",
                description="Configura el canal de turnos y los 3 roles escalables de Farmero.",
                color=discord.Color.teal()
            )
            await interaction.response.edit_message(embed=embed, view=view)


# --- SELECCIÓN DE CANALES ---
class ChannelSettingSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Canal de Strikes", value="CANAL_STRIKES_ID", description="Alertas de strikes"),
            discord.SelectOption(label="Canal de Advertencias", value="CANAL_ADVERTENCIAS_ID", description="Alertas de warns"),
            discord.SelectOption(label="Canal Logs de Cupones", value="CANAL_LOGS_CUPONES_ID", description="Registro de uso de cupones"),
            discord.SelectOption(label="Canal Logs de Coins", value="CANAL_LOGS_ID", description="Logs generales de economía"),
            discord.SelectOption(label="Canal General", value="CANAL_GENERAL_ID", description="Para eventos y Airdrops"),
            discord.SelectOption(label="Canal de Ranking (Top)", value="CANAL_TOP_ID", description="Tabla de clasificación global"),
            discord.SelectOption(label="Canal Misiones URA", value="CANAL_ACT_URA", description="Subida de misiones URA"),
            discord.SelectOption(label="Canal Misiones Halcon", value="CANAL_ACT_HALCON", description="Subida de misiones Halcón"),
            discord.SelectOption(label="Canal Misiones PDI", value="CANAL_ACT_PDI", description="Subida de misiones PDI"),
            discord.SelectOption(label="Canal Prueba Robos", value="CANAL_PRUEBA_ROBOS_ID", description="Verificación de pruebas de robos"),
            discord.SelectOption(label="Canal Registro Robos", value="CANAL_REGISTRO_ROBOS_ID", description="Registro/Logs de robos acudidos"),
            discord.SelectOption(label="Canal Cambios PFA", value="CANAL_CAMBIOS_PFA_ID", description="Auditoría de cambios y ascensos PFA"),
            discord.SelectOption(label="Canal de Tickets", value="CANAL_TICKETS_ID", description="Usado en el botón de apelación de strikes/advertencias"),
            discord.SelectOption(label="Canal Bitácoras (Limpieza)", value="CANAL_BITACORAS_ID", description="Analizado por /limpieza para detectar inactividad"),
            discord.SelectOption(label="Canal Reinicio de Sanciones", value="CANAL_REINICIO_ID", description="Confirmación al retirar a un oficial con sanciones activas")
        ]
        super().__init__(placeholder="Elige qué canal configurar...", options=options, custom_id="cfg_channel_setting_select")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        view.add_item(ChannelSelectSelector(setting))
        
        embed = discord.Embed(
            title=f"Seleccionar Canal para {setting}",
            description=f"Elige el canal del menú desplegable de abajo para asignar a `{setting}`.",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)


class ChannelSelectSelector(discord.ui.ChannelSelect):
    def __init__(self, setting: str):
        self.setting = setting
        super().__init__(placeholder="Selecciona un canal de texto...", channel_types=[discord.ChannelType.text], custom_id="cfg_channel_selector")

    async def callback(self, interaction: discord.Interaction):
        canal = self.values[0]
        establecer_config(interaction.guild.id, self.setting, str(canal.id))
        
        embed = discord.Embed(
            title="✅ Configuración Actualizada",
            description=f"Se ha asignado el canal {canal.mention} (`{canal.id}`) a `{self.setting}` correctamente.",
            color=discord.Color.green()
        )
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        await interaction.response.edit_message(embed=embed, view=view)


# --- SELECCIÓN DE ROLES BASE ---
class RoleBaseSettingSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Rol PFA", value="ROL_PFA_ID", description="Rol institucional base"),
            discord.SelectOption(label="Rol Low PFA", value="ROL_LOWPFA_ID", description="Rol de Tier Low"),
            discord.SelectOption(label="Rol High PFA", value="ROL_HIGHPFA_ID", description="Rol de Tier High"),
            discord.SelectOption(label="Rol Head PFA", value="ROL_HEAD_PFA_ID", description="Rol de Tier Head"),
            discord.SelectOption(label="Rol Cadete", value="ROL_CADETE_ID", description="Rol de Cadete inicial"),
            discord.SelectOption(label="Rol Nuevo Ingresante", value="ROL_NUEVO_INGRESANTE_ID", description="Rol temporal para ingresantes"),
            discord.SelectOption(label="Rol Blacklist PFA", value="ROL_BLACKLIST_PFA_ID", description="Rol asignado a blacklist")
        ]
        super().__init__(placeholder="Elige qué rol base configurar...", options=options, custom_id="cfg_role_base_select")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        view.add_item(RoleStaffSelector(setting))
        
        embed = discord.Embed(
            title=f"Seleccionar Rol para {setting}",
            description=f"Elige el rol del menú desplegable de abajo para asignar a `{setting}`.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=view)


# --- SELECCIÓN DE ROLES STAFF / ECONOMÍA ---
class RoleStaffSettingSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Rol de Panel Admin (Único)", value="ROL_PANEL_ADMIN_ID", description="Rol de administrador principal del panel"),
            discord.SelectOption(label="Rol de Permisos/Staff (Único)", value="ROL_PERMS", description="Rol de permisos generales de staff"),
            discord.SelectOption(label="Roles Admin Staff (Lista)", value="ROLES_PARA_ADMIN_STAFF", description="Roles autorizados para administrar la economía"),
            discord.SelectOption(label="Roles para Ver Coins (Lista)", value="ROLES_PARA_VER", description="Roles autorizados para consultar saldo/ranking"),
            discord.SelectOption(label="Roles lanzar Airdrop (Lista)", value="ROLES_LANZAR_AIRDROP", description="Roles autorizados para tirar maletines")
        ]
        super().__init__(placeholder="Elige qué rol staff configurar...", options=options, custom_id="cfg_role_staff_select")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        
        if setting in ["ROLES_PARA_ADMIN_STAFF", "ROLES_PARA_VER", "ROLES_LANZAR_AIRDROP"]:
            view.add_item(RoleEcoSelector(setting))
            desc = f"Elige **uno o más** roles del menú de abajo para asignar a la lista `{setting}`."
        else:
            view.add_item(RoleStaffSelector(setting))
            desc = f"Elige el rol único del menú de abajo para asignar a `{setting}`."
            
        embed = discord.Embed(
            title=f"Configurar Rol para {setting}",
            description=desc,
            color=discord.Color.orange()
        )
        await interaction.response.edit_message(embed=embed, view=view)


class RoleStaffSelector(discord.ui.RoleSelect):
    def __init__(self, setting: str):
        self.setting = setting
        super().__init__(placeholder="Selecciona un rol...", custom_id="cfg_role_staff_selector")

    async def callback(self, interaction: discord.Interaction):
        rol = self.values[0]
        establecer_config(interaction.guild.id, self.setting, str(rol.id))
        
        embed = discord.Embed(
            title="✅ Configuración Actualizada",
            description=f"Se ha asignado el rol **{rol.name}** (`{rol.id}`) a `{self.setting}` correctamente.",
            color=discord.Color.green()
        )
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        await interaction.response.edit_message(embed=embed, view=view)


# --- SELECCIÓN DE ROLES SUBDIVISIONES PFA ---
class RoleSubdivsSettingSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Roles URA (Lista)", value="ROLE_SUB_URA", description="Roles pertenecientes a URA"),
            discord.SelectOption(label="Roles Halcon (Lista)", value="ROLE_SUB_HALCON", description="Roles pertenecientes a Halcón"),
            discord.SelectOption(label="Roles PDI (Lista)", value="ROLE_SUB_PDI", description="Roles pertenecientes a PDI"),
            discord.SelectOption(label="Roles Permitidos Robos (Lista)", value="ROLES_PERMITIDOS_ROBOS", description="Roles autorizados a subir pruebas de robos")
        ]
        super().__init__(placeholder="Elige qué opción configurar...", options=options, custom_id="cfg_role_subdivs_select")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        view.add_item(RoleEcoSelector(setting))
        
        embed = discord.Embed(
            title=f"Configurar Roles para {setting}",
            description=f"Elige **uno o más** roles del menú de abajo para asignar a `{setting}`.",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=view)


class RoleEcoSelector(discord.ui.RoleSelect):
    def __init__(self, setting: str):
        self.setting = setting
        super().__init__(placeholder="Selecciona roles (puedes elegir varios)...", min_values=1, max_values=10, custom_id="cfg_role_eco_selector")

    async def callback(self, interaction: discord.Interaction):
        roles = self.values
        ids_str = ",".join(str(r.id) for r in roles)
        establecer_config(interaction.guild.id, self.setting, ids_str)
        
        nombres = ", ".join(f"**{r.name}**" for r in roles)
        embed = discord.Embed(
            title="✅ Configuración Actualizada",
            description=f"Se han asignado los roles {nombres} a `{self.setting}` correctamente.",
            color=discord.Color.green()
        )
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        await interaction.response.edit_message(embed=embed, view=view)


# --- SELECCIÓN DE TIERS JERARQUÍA PFA ---
class RangoTierSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Low PFA (Rango 0 a 12)", value="low", description="De Cadete a Sub Teniente"),
            discord.SelectOption(label="High PFA (Rango 13 a 25)", value="high", description="De Teniente a Sub Comisario"),
            discord.SelectOption(label="Head PFA (Rango 26 a 33)", value="head", description="De Comisario a Dueño")
        ]
        super().__init__(placeholder="Elige un Tier de Rangos PFA...", options=options, custom_id="cfg_rango_tier_select")

    async def callback(self, interaction: discord.Interaction):
        tier = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        view.add_item(RangoSelectorSelect(tier))
        
        embed = discord.Embed(
            title=f"Configuración: Rangos ({tier.upper()})",
            description="Selecciona qué rango específico deseas asociar a un rol en tu servidor.",
            color=discord.Color.dark_teal()
        )
        await interaction.response.edit_message(embed=embed, view=view)


class RangoSelectorSelect(discord.ui.Select):
    def __init__(self, tier: str):
        from cogs.panel_gestion_pfa import JERARQUIA_PFA
        options = []
        for r in JERARQUIA_PFA:
            if r.tier == tier:
                options.append(discord.SelectOption(
                    label=f"[{r.nivel:02d}] {r.nombre}",
                    value=r.env_var,
                    description=f"Variable: {r.env_var}"
                ))
        super().__init__(placeholder="Elige el rango a configurar...", options=options, custom_id="cfg_rango_selector_select")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        view.add_item(RoleStaffSelector(setting))
        
        embed = discord.Embed(
            title=f"Asignar Rol a {setting}",
            description=f"Elige el rol del menú desplegable de abajo para asignar a `{setting}`.",
            color=discord.Color.dark_teal()
        )
        await interaction.response.edit_message(embed=embed, view=view)


# --- SELECCIÓN DE VARIABLES URA / HALCÓN ---
class SubdivsSettingSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Canal Logs URA", value="CANAL_LOGS_URA_ID", description="Logs de la gestión URA"),
            discord.SelectOption(label="Canal Logs Halcon", value="CANAL_LOGS_HALCON_ID", description="Logs de la gestión Halcón"),
            discord.SelectOption(label="Canal Cierre Top URA", value="CANAL_TOP_MISIONES_URA_ID", description="Cierre del ranking URA"),
            discord.SelectOption(label="Rol Base URA", value="ROL_URA_ID", description="Rol base para pilotos URA"),
            discord.SelectOption(label="Rol Base Halcon", value="ROL_HALCON_ID", description="Rol base para miembros Halcón"),
            discord.SelectOption(label="Rol Panel URA Admin", value="ROL_PANEL_URA_ADMIN_ID", description="Rol para manejar panel URA"),
            discord.SelectOption(label="Rol Panel Halcon Admin", value="ROL_PANEL_HALCON_ADMIN_ID", description="Rol para manejar panel Halcón"),
            discord.SelectOption(label="Rol Tier Low URA", value="ROL_LOW_URA_ID"),
            discord.SelectOption(label="Rol Tier High URA", value="ROL_HIGH_URA_ID"),
            discord.SelectOption(label="Rol Tier Head URA", value="ROL_HEAD_URA_ID"),
            discord.SelectOption(label="Rol Tier Low Halcon", value="ROL_LOW_HALCON_ID"),
            discord.SelectOption(label="Rol Tier High Halcon", value="ROL_HIGH_HALCON_ID"),
            discord.SelectOption(label="Rol Tier Head Halcon", value="ROL_HEAD_HALCON_ID"),
            discord.SelectOption(label="Configurar Rangos URA", value="rangos_ura_menu", emoji="🚁"),
            discord.SelectOption(label="Configurar Rangos Halcon", value="rangos_halcon_menu", emoji="🦅")
        ]
        super().__init__(placeholder="Elige una opción de URA / Halcón...", options=options, custom_id="cfg_subdivs_setting_select")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        
        if setting == "rangos_ura_menu":
            view.add_item(RangoSubdivSelectorSelect("URA"))
            embed = discord.Embed(
                title="Configuración: Rangos de URA",
                description="Selecciona qué rango de URA deseas configurar con un rol.",
                color=discord.Color.dark_magenta()
            )
            return await interaction.response.edit_message(embed=embed, view=view)
        elif setting == "rangos_halcon_menu":
            view.add_item(RangoSubdivSelectorSelect("HALCON"))
            embed = discord.Embed(
                title="Configuración: Rangos de Halcón",
                description="Selecciona qué rango de Halcón deseas configurar con un rol.",
                color=discord.Color.dark_magenta()
            )
            return await interaction.response.edit_message(embed=embed, view=view)
            
        if "CANAL" in setting:
            view.add_item(ChannelSelectSelector(setting))
            desc = f"Elige el canal de logs/top para asignar a `{setting}`."
            color = discord.Color.blue()
        else:
            view.add_item(RoleStaffSelector(setting))
            desc = f"Elige el rol de tier/base para asignar a `{setting}`."
            color = discord.Color.red()
            
        embed = discord.Embed(
            title=f"Asignar recurso a {setting}",
            description=desc,
            color=color
        )
        await interaction.response.edit_message(embed=embed, view=view)


class RangoSubdivSelectorSelect(discord.ui.Select):
    def __init__(self, subdiv: str):
        self.subdiv = subdiv
        options = []
        if subdiv == "URA":
            from cogs.panel_gestion_ura import JERARQUIA_URA
            for item in JERARQUIA_URA:
                nombre = item[0]
                raw_name = nombre.replace(" ", "_").replace("º", "_").replace("1", "1_").upper()
                import re
                clean_name = re.sub(r"[^A-Z0-9_]", "", raw_name)
                key = f"ROL_URA_RANGO_{clean_name}"
                options.append(discord.SelectOption(label=nombre, value=key, description=f"Variable: {key}"))
        else:
            from cogs.panel_gestion_halcon import JERARQUIA_HALCON
            for item in JERARQUIA_HALCON:
                nombre = item[0]
                raw_name = nombre.replace(" ", "_").replace("º", "_").replace("1", "1_").upper()
                import re
                clean_name = re.sub(r"[^A-Z0-9_]", "", raw_name)
                key = f"ROL_HALCON_RANGO_{clean_name}"
                options.append(discord.SelectOption(label=nombre, value=key, description=f"Variable: {key}"))
                
        super().__init__(placeholder=f"Elige el rango de {subdiv}...", options=options, custom_id="cfg_rango_subdiv_selector")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        view.add_item(RoleStaffSelector(setting))
        
        embed = discord.Embed(
            title=f"Asignar Rol a rango {self.subdiv}",
            description=f"Elige el rol del menú desplegable de abajo para asignar a `{setting}`.",
            color=discord.Color.dark_magenta()
        )
        await interaction.response.edit_message(embed=embed, view=view)


# --- SELECCIÓN DE VARIABLES INTERVIEWER / OPOSICIONES ---
class InterviewerSettingSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Canal Postulaciones", value="CANAL_POSTULACIONES_ID", description="Canal de anuncios de oposiciones"),
            discord.SelectOption(label="Canal Resultados", value="CANAL_RESULTADOS_ID", description="Canal de resultados de oposiciones"),
            discord.SelectOption(label="Canal Bitácora Opos", value="CANAL_BITACORA_OPOS_ID", description="Bitácora de oposiciones"),
            discord.SelectOption(label="Canal Top Interviewers", value="CANAL_TOP_INTERVIEWERS_ID", description="Anuncio del ranking semanal de interviewers"),
            discord.SelectOption(label="Canal Sala de Postulantes", value="CANAL_SALA_POSTULANTES_ID", description="Enlazado en el anuncio de apertura de oposiciones"),
            discord.SelectOption(label="Rol Interviewer", value="ROL_INTERVIEWER_ID", description="Rol para dar acceso a panel de interviewer"),
            discord.SelectOption(label="Rol Encargado Interviewer", value="ROL_ENCARGADO_INTERVIEWER_ID", description="Rol para encargados de oposiciones"),
            discord.SelectOption(label="Rol Civil (Ping)", value="ROL_CIVIL_ID", description="Rol al que se le hace ping al abrir oposiciones"),
            discord.SelectOption(label="Canales Bienvenida PFA", value="bienvenida_pfa_menu", emoji="👋", description="Configura los canales referenciados en el DM de bienvenida")
        ]
        super().__init__(placeholder="Elige una opción...", options=options, custom_id="cfg_interviewer_setting_select")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        
        if setting == "bienvenida_pfa_menu":
            view.add_item(BienvenidaChannelsSelect())
            embed = discord.Embed(
                title="Configuración: Canales del DM de Bienvenida",
                description="Ajusta los canales que recibe el postulante por mensaje directo al ser aprobado.",
                color=discord.Color.dark_blue()
            )
            return await interaction.response.edit_message(embed=embed, view=view)
            
        if "CANAL" in setting:
            view.add_item(ChannelSelectSelector(setting))
            desc = f"Elige el canal para asignar a `{setting}`."
            color = discord.Color.blue()
        else:
            view.add_item(RoleStaffSelector(setting))
            desc = f"Elige el rol para asignar a `{setting}`."
            color = discord.Color.red()
            
        embed = discord.Embed(
            title=f"Asignar recurso a {setting}",
            description=desc,
            color=color
        )
        await interaction.response.edit_message(embed=embed, view=view)


class BienvenidaChannelsSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Canal Cambio de Nombre", value="CANAL_NOMBRE_PFA_ID"),
            discord.SelectOption(label="Canal Indumentaria", value="CANAL_INDUMENTARIA_ID"),
            discord.SelectOption(label="Canal Config TS3", value="CANAL_TS3_ID"),
            discord.SelectOption(label="Canal Video Intro", value="CANAL_VIDEO_INTRO_ID"),
            discord.SelectOption(label="Canal Doble Facción Info", value="CANAL_DF_INFO_ID"),
            discord.SelectOption(label="Canal Doble Facción Postulación", value="CANAL_DF_POSTULACION_ID"),
            discord.SelectOption(label="Canal Jerarquía PFA", value="CANAL_JERARQUIA_ID"),
            discord.SelectOption(label="Canal Encargados", value="CANAL_ENCARGADOS_ID")
        ]
        super().__init__(placeholder="Elige qué canal de bienvenida configurar...", options=options, custom_id="cfg_bienvenida_channels_select")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        view.add_item(ChannelSelectSelector(setting))
        
        embed = discord.Embed(
            title=f"Configurar canal para {setting}",
            description=f"Elige el canal de texto para asociar a `{setting}`.",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)


# --- SELECCIÓN: RRHH (BAJAS / AUSENCIAS) ---
class RRHHSettingSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Canal Bajas (Solicitudes)", value="CANAL_BAJAS_ID", description="Recibe el formulario de baja voluntaria"),
            discord.SelectOption(label="Canal Registro de Bajas", value="CANAL_REGISTRO_BAJAS_ID", description="Log de bajas procesadas"),
            discord.SelectOption(label="Rol de Baja (Retirado)", value="ROL_BAJA_ID", description="Rol que queda tras darse de baja"),
            discord.SelectOption(label="Roles Permitidos Solicitar Baja (Lista)", value="ROLES_PERMITIDOS_BAJA"),
            discord.SelectOption(label="Canal Ausencias (Licencias)", value="CANAL_AUSENCIAS_ID", description="Recibe las solicitudes de licencia"),
            discord.SelectOption(label="Rol Ausente (Licencia activa)", value="ROL_AUSENTE_ID", description="Excluye al oficial de la limpieza por inactividad"),
            discord.SelectOption(label="Roles Permitidos Solicitar Ausencia (Lista)", value="ROLES_PERMITIDOS_AUSENCIA"),
            discord.SelectOption(label="Roles Aprobar Ausencias (Lista)", value="ROLES_APROBAR_AUSENCIAS"),
        ]
        super().__init__(placeholder="Elige qué configurar de RRHH...", options=options, custom_id="cfg_rrhh_select")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())

        if "CANAL" in setting:
            view.add_item(ChannelSelectSelector(setting))
            desc = f"Elige el canal para asignar a `{setting}`."
            color = discord.Color.blue()
        elif setting in ("ROLES_PERMITIDOS_BAJA", "ROLES_PERMITIDOS_AUSENCIA", "ROLES_APROBAR_AUSENCIAS"):
            view.add_item(RoleEcoSelector(setting))
            desc = f"Elige uno o más roles para `{setting}`."
            color = discord.Color.orange()
        else:
            view.add_item(RoleStaffSelector(setting))
            desc = f"Elige el rol para asignar a `{setting}`."
            color = discord.Color.red()

        embed = discord.Embed(title=f"Configurar {setting}", description=desc, color=color)
        await interaction.response.edit_message(embed=embed, view=view)


# --- SELECCIÓN: CAMBIO DE NOMBRE ---
class CambioNombreSettingSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Canal Aprobación de Nombre", value="CANAL_APROBACION_NOMBRE_ID", description="Recibe las solicitudes de cambio de nombre"),
            discord.SelectOption(label="Roles que Aprueban/Rechazan (Lista)", value="ROLES_APROBAR_NOMBRE"),
            discord.SelectOption(label="Roles Permitidos Solicitar (Lista)", value="ROLES_PERMITIDOS_NOMBRE"),
            discord.SelectOption(label="Roles Admin Staff del Panel (Lista)", value="ROLES_ADMIN_STAFF", description="Quién puede desplegar el panel"),
        ]
        super().__init__(placeholder="Elige qué configurar de Cambio de Nombre...", options=options, custom_id="cfg_cambionombre_select")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())

        if "CANAL" in setting:
            view.add_item(ChannelSelectSelector(setting))
            desc = f"Elige el canal para asignar a `{setting}`."
            color = discord.Color.blue()
        else:
            view.add_item(RoleEcoSelector(setting))
            desc = f"Elige uno o más roles para `{setting}`."
            color = discord.Color.orange()

        embed = discord.Embed(title=f"Configurar {setting}", description=desc, color=color)
        await interaction.response.edit_message(embed=embed, view=view)


# --- SELECCIÓN: DOBLE FACCIÓN ---
class DobleFaccionSettingSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Canal Registro Doble Facción", value="CANAL_REGISTRO_DF_ID", description="Recibe solicitudes y bajas de doble facción"),
            discord.SelectOption(label="Canal Normativa Doble Facción", value="CANAL_NORMATIVA_DF_ID", description="Enlazado en el panel de postulación"),
            discord.SelectOption(label="Rol Doble Facción", value="ROL_DOBLE_FACCION_ID", description="Rol otorgado al aprobarse"),
        ]
        super().__init__(placeholder="Elige qué configurar de Doble Facción...", options=options, custom_id="cfg_dobleFaccion_select")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())

        if "CANAL" in setting:
            view.add_item(ChannelSelectSelector(setting))
            desc = f"Elige el canal para asignar a `{setting}`."
            color = discord.Color.blue()
        else:
            view.add_item(RoleStaffSelector(setting))
            desc = f"Elige el rol para asignar a `{setting}`."
            color = discord.Color.red()

        embed = discord.Embed(title=f"Configurar {setting}", description=desc, color=color)
        await interaction.response.edit_message(embed=embed, view=view)


# --- SELECCIÓN: CASINO Y SUGERENCIAS ---
class CasinoSugerenciasSettingSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Rol Aviso Casino", value="ROL_AVISO_CASINO", description="Recibe el ping cuando abre el casino"),
            discord.SelectOption(label="Roles Permitidos Casino (Lista)", value="ROLES_PERMITIDOS_CASINO"),
            discord.SelectOption(label="Canal Sugerencias", value="CANAL_SUGERENCIAS_ID", description="Canal donde se publican las sugerencias"),
        ]
        super().__init__(placeholder="Elige qué configurar...", options=options, custom_id="cfg_casino_sugerencias_select")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())

        if setting == "CANAL_SUGERENCIAS_ID":
            view.add_item(ChannelSelectSelector(setting))
            desc = f"Elige el canal para asignar a `{setting}`."
            color = discord.Color.blue()
        elif setting == "ROLES_PERMITIDOS_CASINO":
            view.add_item(RoleEcoSelector(setting))
            desc = f"Elige uno o más roles para `{setting}`."
            color = discord.Color.orange()
        else:
            view.add_item(RoleStaffSelector(setting))
            desc = f"Elige el rol para asignar a `{setting}`."
            color = discord.Color.red()

        embed = discord.Embed(title=f"Configurar {setting}", description=desc, color=color)
        await interaction.response.edit_message(embed=embed, view=view)


# --- SELECCIÓN: LOGS DEL SISTEMA ---
class LogsSettingSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Canal Logs de Roles (Base)", value="CANAL_LOGS_ROLES_ID", description="Respaldo si no configurás los separados"),
            discord.SelectOption(label="Canal Logs de Roles (Usuarios/Staff)", value="CANAL_LOGS_ROLES_USUARIOS_ID"),
            discord.SelectOption(label="Canal Logs de Roles (Bots)", value="CANAL_LOGS_ROLES_BOTS_ID"),
            discord.SelectOption(label="Canal Logs de Voz", value="CANAL_LOGS_VOICE_ID"),
        ]
        super().__init__(placeholder="Elige qué canal de logs configurar...", options=options, custom_id="cfg_logs_select")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())
        view.add_item(ChannelSelectSelector(setting))

        embed = discord.Embed(
            title=f"Configurar canal para {setting}",
            description=f"Elige el canal de texto para asociar a `{setting}`.",
            color=discord.Color.dark_grey()
        )
        await interaction.response.edit_message(embed=embed, view=view)


# --- SELECCIÓN: TURNOS Y FARMEO ---
class TurnosFarmeoSettingSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Canal de Turnos", value="CANAL_TURNOS_ID", description="Anuncios de inicio/fin de servicio"),
            discord.SelectOption(label="Rol Farmero (Nivel 1)", value="ROL_FARMERO_1_ID", description="1ª sanción por farmeo de horas en la semana"),
            discord.SelectOption(label="Rol Farmero 2 (Nivel 2)", value="ROL_FARMERO_2_ID", description="2ª sanción por farmeo de horas en la semana"),
            discord.SelectOption(label="Rol Farmero 3 (Nivel 3)", value="ROL_FARMERO_3_ID", description="3ª o más sanción por farmeo de horas en la semana"),
        ]
        super().__init__(placeholder="Elige qué configurar de Turnos/Farmeo...", options=options, custom_id="cfg_turnos_farmeo_select")

    async def callback(self, interaction: discord.Interaction):
        setting = self.values[0]
        view = discord.ui.View(timeout=300)
        view.add_item(CategorySelect())

        if setting == "CANAL_TURNOS_ID":
            view.add_item(ChannelSelectSelector(setting))
            desc = f"Elige el canal para asignar a `{setting}`."
            color = discord.Color.blue()
        else:
            view.add_item(RoleStaffSelector(setting))
            desc = f"Elige el rol para asignar a `{setting}`."
            color = discord.Color.red()

        embed = discord.Embed(title=f"Configurar {setting}", description=desc, color=color)
        await interaction.response.edit_message(embed=embed, view=view)


# --- VISTA PRINCIPAL DEL PANEL ---
class ConfigPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(CategorySelect())


class ConfigPanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="configuracion", description="[ADMIN] Abre el panel interactivo de configuración del bot.")
    async def configuracion(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        es_owner_o_admin = (
            interaction.user.id == interaction.guild.owner_id or
            interaction.user.guild_permissions.administrator
        )
        rol_admin = obtener_config_int(guild_id, "ROL_PANEL_ADMIN_ID")
        rol_perms = obtener_config_int(guild_id, "ROL_PERMS")
        tiene_rol_admin = rol_admin and any(r.id == rol_admin for r in interaction.user.roles)
        tiene_rol_perms = rol_perms and any(r.id == rol_perms for r in interaction.user.roles)

        if not (es_owner_o_admin or tiene_rol_admin or tiene_rol_perms):
            return await interaction.response.send_message("⛔ No tienes permisos de Administrador o el rango necesario para usar este comando.", ephemeral=True)

        embed = discord.Embed(
            title="⚙️ PANEL DE CONFIGURACIÓN DEL BOT",
            description=(
                "Bienvenido al panel de configuración. Aquí puedes ajustar dinámicamente "
                "todos los canales y roles del bot para adaptarlo a tu servidor.\n\n"
                "**Categorías disponibles:**\n"
                "🔹 **Canales:** Configura canales de logs, de subida de misiones por subdivisión, de verificación de robos, etc.\n"
                "🔹 **Roles Base / PFA:** Ajusta los roles básicos (PFA, Tiers, Cadete, Blacklist, etc.).\n"
                "🔹 **Roles Staff / Economía:** Controla accesos administrativos y consultas de coins.\n"
                "🔹 **Roles Subdivisiones:** Configura qué roles forman parte de URA, Halcón, PDI y autorizados a robos.\n"
                "🔹 **Rangos PFA (Jerarquía):** Enlaza cada uno de los 34 rangos con sus correspondientes roles de Discord.\n"
                "🔹 **Subdivisiones (URA / Halcón):** Configura logs, bases, tiers y los 22 rangos de URA / 21 de Halcón.\n"
                "🔹 **Oposiciones / Interviewer:** Configura postulaciones, logs y canales del DM de bienvenida.\n"
                "🔹 **RRHH (Bajas / Ausencias):** Canales y roles de solicitudes de baja y licencias temporales.\n"
                "🔹 **Cambio de Nombre:** Canal y roles del sistema de cambio de nombre.\n"
                "🔹 **Doble Facción:** Canal de registro, normativa y rol de doble facción.\n"
                "🔹 **Casino y Sugerencias:** Roles del casino y canal de sugerencias.\n"
                "🔹 **Logs del Sistema:** Canales de logs de roles y voz.\n"
                "🔹 **Turnos y Farmeo:** Canal de turnos y los 3 roles escalables de Farmero.\n\n"
                "*Selecciona una categoría abajo para empezar.*"
            ),
            color=discord.Color.dark_grey()
        )
        view = ConfigPanelView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ConfigPanelCog(bot))
