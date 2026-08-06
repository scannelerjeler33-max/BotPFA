# Handoff General — Bot P.F.A · Ibiza Roleplay

> Documento de referencia completo: qué hace el bot hoy, cómo está armado, y qué
> mejoras quedan pendientes. Para el detalle fino de Sanciones, Interviewer y
> P.D.I ya existen documentos dedicados (`HANDOFF_SANCIONES.md`,
> `HANDOFF_INTERVIEWER.md`, `HANDOFF_PDI.md`) — acá se resume todo el resto y se
> conecta el panorama completo.

---

## 1. Arquitectura general

### 1.1 Entry point
`BotCoins.py` es el único archivo que arranca el proceso. Su rol:
1. Corre `ejecutar_mantenimiento_db()` (crea/actualiza tablas al boot).
2. Levanta un mini servidor HTTP (`aiohttp`) en el puerto que asigna Render, solo
   para que el health check del hosting no falle (el bot en sí no necesita HTTP).
3. Carga ~24 extensiones (cogs) definidas en `setup_hook()`.
4. En `on_ready()`, sincroniza los slash commands en **todos los servidores**
   donde esté el bot (no un ID fijo — ver sección 4).

### 1.2 Estructura de carpetas
```
BotCoins.py          → entry point + loader de extensiones
cogs/                → un archivo por sistema/feature
logs/                → listeners de auditoría (roles.py, voice.py)
utils/
  core.py            → conexión DB compartida, coins, envío de logs de economía
  config.py          → sistema de configuración por servidor (ver sección 4)
databases/
  connection.py       → psycopg2.connect(DATABASE_URL)
```

### 1.3 Base de datos
Postgres. Cada cog abre su propia conexión vía `get_connection()` (patrón repetido
en todo el proyecto — no hay pool centralizado). La mayoría usa `autocommit = True`.

### 1.4 Deploy
Corre en Render. Es un bot de polling (no necesita recibir tráfico HTTP), por lo
que si el servicio está configurado como **Web Service** el health-check por
puerto falla — se resolvió agregando un servidor HTTP mínimo en `BotCoins.py`.
Alternativa más prolija: migrar a un servicio tipo **Background Worker**.

---

## 2. Sistemas del bot, por dominio

### 2.1 Economía — `panel_economia.py`
- Banco de coins (`usuarios.coins`, tipo `NUMERIC(12,2)`, nunca negativo).
- Panel público (`/crearpanel`): ver saldo propio, ranking de subdivisiones.
- Panel staff (`/panelstaff`): dar/quitar coins a un usuario, dar a múltiples
  usuarios a la vez (parseo robusto de menciones pegadas sin espacios), consultar
  saldo de cualquiera.
- Shop (`/crearshop`): canjear coins por premios (30M IC, remover advertencia/strike,
  promotes, ropa, auto del mes, VIP). Remover strike/advertencia y promote
  faccionario generan **cupones** en vez de aplicarse directo (ver 2.6).
- Airdrops (`/airdropcoins`): maletín público, el primero en tocar el botón gana.
- TOP semanal automático: cada 5 min actualiza (o crea) un embed con el ranking
  global de coins en el canal configurado, por servidor.

### 2.2 Casino — `panel_casino.py`
- **Blackjack vs bot** (`/crearblackjack`): apuesta fija 0.25, animado con delays.
- **Ruleta europea multijugador** (`/crearruleta`): ventana de apuestas de 10s,
  colores/números/pleno, límite de apuesta por casilla.
- **Blackjack 1v1** (`/panelbj1v1`): sistema de cola/matchmaking entre oficiales.
- Todo el casino solo abre de horario configurado (00:00–02:00 Arg, hardcodeado
  en el código, no vía config). Aviso automático de apertura todos los días a
  las 00:00 Arg, mencionando el rol de aviso — ahora itera todos los servidores.

### 2.3 Cupones — `panel_cupones.py`
- Inventario de cupones por usuario (`quitar strike`, `quitar advertencia`,
  `promote faccionario`).
- Canjear cupón de sanción pide el ID exacto de la sanción a eliminar.
- Canjear cupón de promote asciende un rango automáticamente usando la
  jerarquía PFA (`panel_gestion_pfa.py`).
- Comandos admin: `/darcupon`, `/quitarcupon`.

### 2.4 Sanciones — `panel_strikes.py` + `panel_advertencias.py` + `panel_farmeo.py`
> Detalle completo en `HANDOFF_SANCIONES.md`. Resumen:
- Strikes y advertencias con motivo elegido desde un menú desplegable (con
  opción "Otro" para texto libre).
- 3 advertencias acumuladas → 1 strike automático.
- Motivo **"Farmeo de horas"** (disponible en ambos paneles) alimenta un
  contador semanal independiente que asigna roles escalables **Farmero / Farmero
  2 / Farmero 3**. Se resetean todos los lunes 00:00 con aviso en el canal general.
- Botón de apelación en el DM de sanción, enlaza a un canal de tickets.
- Reinicio de sanciones al dar de baja: `panel_reinicio_sanciones.py` detecta
  cuando se retira el rol @PFA y, si el oficial tiene sanciones activas, le
  pregunta al Head PFA si quiere limpiarlas (quedan igual en el historial).

### 2.5 Gestión de facción — PFA / URA / Halcón
- **`panel_gestion_pfa.py`**: alta, baja, ascenso (selector guiado o +1),
  descenso y blacklist de los 34 rangos de la jerarquía PFA (Cadete → Dueño,
  divididos en tiers Low/High/Head). Sincroniza automáticamente el rol de tier
  al cambiar de rango.
- **`panel_gestion_ura.py`** / **`panel_gestion_halcon.py`**: mismo patrón
  (alta/baja/ascenso/descenso + tiers) para las subdivisiones URA (22 rangos) y
  Halcón (21 rangos). URA además tiene un TOP de misiones semanal con reset los
  domingos a las 12:00 Arg.
- **`panel_operativo.py`**: sistema genérico de misiones semanales/diarias para
  URA, Halcón y PDI (reutiliza el mismo motor, solo cambia el contenido de las
  misiones). Incluye sistema de "robos acudidos" con verificación anti-duplicado
  por hash de imagen. Competencia semanal entre las 3 divisiones con bono a la
  ganadora. Reset semanal (domingo→lunes 00:00 UTC) y diario (01:00 UTC).
  > Detalle de PDI específicamente en `HANDOFF_PDI.md`.

### 2.6 Oposiciones / Interviewer — `panel_interviewer.py` + `panel_encargado_interviewer.py`
> Detalle completo en `HANDOFF_INTERVIEWER.md`. Resumen: apertura/cierre de
> sesiones de oposiciones, evaluación de postulantes (aprueba con nota ≥ 10/15),
> asignación automática de roles + DM de bienvenida, estadísticas semanales por
> interviewer y ranking, `/cierresemanal` para archivar y reiniciar el período.

### 2.7 RRHH — `panel_rrhh.py`
- **Bajas voluntarias**: formulario → notifica a RRHH, retira roles del oficial.
- **Ausencias/licencias**: máximo 14 días acumulados y 5 solicitudes por mes,
  requiere aprobación de un encargado (con motivo si se rechaza), asigna rol
  @Ausente mientras dura, expira automáticamente (tarea cada 1h, revisa todos
  los servidores).

### 2.8 Otros paneles administrativos
- **`panel_cambionombre.py`**: solicitud de cambio de nombre/placa → aprobación
  o rechazo (con motivo) por un superior, aplica el nick automáticamente si el
  bot tiene jerarquía suficiente.
- **`panel_doble_faccion.py`**: postulación a doble facción (requiere escribir
  "ACEPTO"), aprobación/rechazo, revocación voluntaria, lista de activos.
- **`panel_nuevo_ingresante.py`**: al asignarse @PFA, da automáticamente
  @Nuevo Ingresante por 7 días (vía DB + tarea horaria, no vía Discord timeout
  nativo — sobrevive reinicios del bot).
- **`panel_limpieza.py`** (`/limpieza`): analiza el canal de bitácoras del
  servidor FiveM (últimas 2 semanas) y detecta oficiales @PFA con menos de 5h
  registradas, excluyendo ausentes y nuevos ingresantes. Incluye `/bitacorasdebug`
  para inspeccionar el formato de un embed cuando el parser falla.
- **`panel_turnos.py`**: fichaje de turnos de patrulla (abrir/cerrar), autocierre
  a las 3 horas, verificación anti-AFK por DM cada 30 minutos, TOP semanal,
  reset los domingos.
- **`sugerencias_setup.py`**: cualquier mensaje en el canal de sugerencias se
  borra y se re-postea como embed con reacciones ✅/❌ y un hilo de debate.

### 2.9 Moderación — `cogs/lockdown.py`
`/lock`, `/unlock` (canal específico o el actual), `/lockdown` (todos los
canales de texto del servidor), `/unlockdown` (revierte todo). Guarda el estado
de permisos previos en `lockdown_state.json` para poder restaurarlo exacto.

### 2.10 Logs de auditoría — `logs/roles.py`, `logs/voice.py`
- **Roles**: detecta cambios de roles vía `on_member_update`, cruza con el
  audit log para identificar quién lo hizo (usuario vs bot), separa logs por
  canal según el origen. Si alguien borra un log, le avisa por DM al propietario
  configurado y le manda una copia reconstruida del embed eliminado.
- **Voice**: conectar/desconectar/mover/mute/deafen en canales de voz, también
  cruzando con el audit log para detectar acción de un admin vs voluntaria.

### 2.11 Configuración multi-servidor — `cogs/config_panel.py` + `utils/config.py`
El corazón de por qué el bot ahora puede instalarse en cualquier servidor:
- `utils/config.py`: tabla `configuracion_servidor (guild_id, clave, valor)` +
  caché en memoria. `obtener_config_int/list(guild_id, clave, default)` — si no
  hay nada en la DB, cae al `.env` (compatibilidad con el servidor original), y
  si tampoco hay nada ahí, usa el `default` que pasa cada cog.
- `/configuracion`: panel interactivo con categorías (Canales, Roles Base/PFA,
  Roles Staff/Economía, Roles Subdivisiones, Rangos PFA, URA/Halcón, Oposiciones/
  Interviewer, RRHH, Cambio de Nombre, Doble Facción, Casino/Sugerencias, Logs,
  Turnos/Farmeo) donde cualquier admin carga sus propios canales y roles sin
  tocar una sola línea de código ni el `.env`.

---

## 3. Tablas de base de datos (por sistema)

| Sistema | Tablas |
|---|---|
| Economía | `usuarios`, `competencia_subdivisiones` |
| Casino | (sin persistencia — todo en memoria de proceso) |
| Cupones | `cupones_usuario` |
| Strikes / Advertencias | `strikes`, `strikes_historial`, `advertencias`, `advertencias_historial` |
| Farmeo | `farmeo_horas_semanal` |
| PFA / Blacklist | `pfa_blacklist` |
| Nuevo ingresante | `nuevos_ingresantes` |
| Ausencias / RRHH | `ausencias_activas`, `registro_pedidos_ausencia` |
| Cambio de nombre | `historial_nombres` |
| Doble facción | `doble_faccion_solicitudes` |
| Oposiciones / Interviewer | `oposiciones_sesiones`, `oposiciones_resultados`, `oposiciones_cooldown`, `oposiciones_cierre_semanal`, `oposiciones_ajustes` |
| Operativo (URA/Halcón/PDI) | `misiones_activas`, `misiones_diarias_activas`, `misiones_completadas`, `misiones_diarias_completadas`, `rachas_diarias`, `evidencias_usadas`, `robos_acudidos`, `ura_top_misiones` |
| Turnos | `turnos_oficiales` |
| Configuración multi-servidor | `configuracion_servidor` |

---

## 4. Multi-servidor: qué quedó resuelto y qué no

En la sesión anterior se completó la migración de **todos** los canales y roles
a config por servidor (24 archivos revisados, todos con fallback al `.env` para
no romper el servidor actual). Quedan dos limitaciones conocidas, deliberadamente
no resueltas porque requieren cambios de esquema de datos, no solo de config:

1. **Tablas sin `guild_id`**: `oposiciones_sesiones/resultados/ajustes`,
   `farmeo_horas_semanal` y `ura_top_misiones` no distinguen de qué servidor
   viene cada registro. Si el bot corre en **dos o más servidores a la vez**,
   estas estadísticas específicas se mezclarían entre servidores. El resto del
   sistema (coins, strikes, advertencias, sanciones, blacklist, etc.) sí está
   completamente aislado por servidor porque usa `guild_id` propio o resuelve
   todo por `interaction.guild`.
2. **`PROPIETARIO_LOGS_ID`** (quién recibe el DM de alerta cuando se borra un
   log) solo es configurable vía `.env`, no desde `/configuracion` — es un ID de
   usuario, no un canal/rol, y los selectores actuales del panel no cubren ese
   tipo de dato.

---

## 5. Mejoras futuras recomendadas

Priorizadas de mayor a menor impacto:

### 5.1 Aislar por servidor las tablas que faltan (alto impacto si se usa multi-servidor)
Agregar columna `guild_id` a `oposiciones_sesiones`, `oposiciones_resultados`,
`oposiciones_ajustes`, `farmeo_horas_semanal` y `ura_top_misiones`, y filtrar
todas las queries correspondientes. Es el único bloqueante real para que el bot
sea 100% multi-servidor sin salvedades.

### 5.2 Pool de conexiones a la base de datos
Cada cog abre su propia conexión psycopg2 al importar el módulo (~15 conexiones
persistentes simultáneas). Funciona, pero no escala bien y hace más frágil el
reinicio en caliente de un cog individual. Migrar a un pool compartido
(`psycopg2.pool` o `asyncpg` con un pool async) reduciría el numero de conexiones
abiertas y evitaría fugas si algún cog no maneja bien un error de conexión.

### 5.3 Auditoría de permisos por comando
Varios comandos usan chequeos manuales repetidos (`es_staff = ... or ...`) en
vez de un decorador único reutilizable. Sería más mantenible un decorador
`@requiere_rol("ROL_PANEL_ADMIN_ID", "ROL_PERMS")` centralizado que resuelva la
config por servidor automáticamente, en vez de repetir la misma lógica de 3
líneas en 40+ lugares.

### 5.4 UI para `PROPIETARIO_LOGS_ID` y otros valores no-rol/no-canal
Agregar un modal genérico "Configurar valor de texto/ID" en `/configuracion`
para los pocos casos que no son canal ni rol (como el ID de usuario propietario
de logs), en vez de dejarlos únicamente en `.env`.

### 5.5 Normativas escritas (trabajo humano, no de código)
El bot ejecuta mecánicas pero no define criterio. Ya existen documentos con las
preguntas abiertas pendientes de definir por escrito:
- `HANDOFF_SANCIONES.md` — qué es falta leve vs grave, qué pasa a los 3 strikes.
- `HANDOFF_INTERVIEWER.md` — requisitos para ser interviewer, criterio de evaluación.
- `HANDOFF_PDI.md` — qué cuenta como "procesar una persona", validación de evidencia.

### 5.6 Límite de horario del casino configurable
El horario del casino (00:00–02:00 Arg) está hardcodeado en el código en varios
lugares (`panel_casino.py`). Si alguna vez se quiere cambiar el horario o hacerlo
configurable por servidor, hoy requiere tocar código en 3 lugares distintos.

### 5.7 Observabilidad
No hay ningún log centralizado de errores (solo `print()` sueltos). Para un bot
de este tamaño, un canal de Discord dedicado a errores no manejados (capturando
excepciones no atrapadas por cog vía `bot.on_error` / `cog_app_command_error`
genérico) ayudaría a detectar bugs como los dos que se encontraron y arreglaron
en la sesión anterior (`panel_operativo.py` con `DIVISION_ROLES` inexistente,
y `panel_advertencias.py` con un `AttributeError` en `/paneladvertencias`) antes
de que un usuario los reporte.

### 5.8 Tests automatizados
No hay ningún test. Dado el tamaño del proyecto (26 archivos, DB compartida
entre todos), incluso una suite mínima que verifique que todos los cogs cargan
sin excepción (`bot.load_extension` contra una DB de prueba) habría detectado
ambos bugs mencionados arriba sin necesidad de una revisión manual completa.

### 5.9 Consolidar la duplicación de helpers repetidos
Funciones como `_fmt_horas`, `_ahora_str`, `buscar_miembro`, `es_panel_*` /
`limpiar_paneles_*` están copiadas casi idénticas en varios cogs (interviewer,
encargado_interviewer, gestion_ura, gestion_halcon). Moverlas a un módulo
`utils/` compartido reduciría el mantenimiento cuando se corrige un bug en una
de ellas y se olvida replicarlo en las demás copias.
