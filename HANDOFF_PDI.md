# Handoff — Sistema Operativo P.D.I · Ibiza Roleplay

> Documento de referencia técnica y operativa para redactar la normativa de la P.D.I.
> Cubre exactamente lo que el bot implementa. Todo lo relacionado a P.D.I vive en un único
> archivo compartido con otras dos subdivisiones (URA y Halcón): `cogs/panel_operativo.py`.

---

## 1. Contexto: la P.D.I no es un sistema aislado

La P.D.I (División de Investigaciones) es una de **tres subdivisiones** que comparten exactamente
el mismo motor de misiones, pruebas y recompensas del bot. Las otras dos son **U.R.A** y **Halcón**.
No hay código exclusivo de P.D.I — hay un sistema genérico parametrizado por división, y P.D.I es
uno de los tres valores posibles (`"URA"`, `"Halcon"`, `"PDI"`).

Esto importa para la normativa: cualquier regla que se escriba sobre "cómo se cargan pruebas" o
"cómo se cobran misiones" aplica igual a las tres divisiones, salvo que la normativa decida
diferenciarlas explícitamente (el bot ya las diferencia solo en el **contenido** de las misiones,
no en el mecanismo).

---

## 2. Roles involucrados

| Rol | Función |
|---|---|
| Rol específico de P.D.I | Habilita usar `/panelpdi` (vía `ViewMisiones`) y contar como "miembro de PDI" para el bono de competencia semanal |
| Rol compartido (aparece en las 3 divisiones + admin + robos) | Acceso transversal — probablemente un rol de mando/staff con permiso en todo el sistema operativo |
| `ROLES_PARA_ADMIN_STAFF` | Puede desplegar todos los paneles (`/panelpdi`, `/panelpruebas`, `/panelrobos`, etc.) y ejecutar los comandos de reset manual |

> **Nota técnica:** el rol compartido (`1351228669359558809`) figura simultáneamente en la lista
> de roles de URA, Halcón, PDI y en `ROLES_PARA_ADMIN_STAFF`. Si la normativa quiere que un oficial
> pertenezca a una sola subdivisión a la vez, **el bot no lo impide** — nada bloquea que alguien
> tenga el rol de PDI y el de URA simultáneamente y participe de ambas misiones.

---

## 3. El comando `/panelpdi`

Despliega un panel con:
- Un menú desplegable de **misión semanal**
- Un menú desplegable de **misión diaria**
- Botón **🟢 Empezar Misión**
- Botón **🔴 Tarea Finalizada**

Solo puede desplegarlo alguien con rol en `ROLES_PARA_ADMIN_STAFF`.

---

## 4. Misiones de P.D.I — contenido exacto

| Tipo | Misión | Meta | Recompensa al completar |
|---|---|---|---|
| Semanal | Procesar 10 personas en una semana | 10 | **5.00 coins** |
| Diaria | Procesar 3 personas en un día | 3 | **1.50 coins** (+0.50 extra si hay racha de 7 días seguidos) |

**Reglas del bot (no negociables sin tocar código):**
- Un oficial solo puede tener **una misión semanal activa** y **una misión diaria activa** a la vez.
- Una vez completada la semanal, **no se puede repetir** hasta el reinicio semanal (lunes).
- La diaria sí se puede repetir todos los días, pero **solo una vez por día**.
- El progreso se carga manualmente subiendo pruebas — el bot no detecta nada en el juego, es 100%
  reporte de honor + evidencia fotográfica.

---

## 5. Flujo completo de una misión

```
1. El oficial abre el panel P.D.I
2. Selecciona la misión semanal y/o diaria en el desplegable
3. Presiona "Empezar Misión"
   → El bot valida que no tenga ya una misión activa del mismo tipo
   → Si ya la completó esta semana (semanal) o este día (diaria), lo bloquea
4. El oficial actúa en el servidor y sube capturas como evidencia
5. Por cada procedimiento, usa el panel de pruebas (/panelpruebas)
   → Sube el ID del mensaje que contiene la foto en el canal de actividades de PDI
   → El bot valida: que el mensaje exista, que tenga adjunto, que el autor sea el mismo oficial
   → Si todo es correcto, progreso +1 (queda registrado en canal de logs con la imagen)
6. Cuando progreso >= meta, el oficial debe presionar "Tarea Finalizada" en el panel de misiones
   → El bot recién ahí acredita la recompensa y libera el slot para la próxima misión
```

> **Importante para la normativa:** el bot **no cobra automáticamente** al llegar a la meta.
> Si un oficial llega a 10 procedimientos y nunca toca "Tarea Finalizada", la misión queda
> "en curso" indefinidamente y no cobra nada, pero tampoco puede iniciar una nueva.

---

## 6. Sistema de pruebas — validaciones exactas

El botón "Subir Prueba Semanal" / "Subir Prueba Diaria" abre un modal que pide el **ID del mensaje**
(no la imagen directamente). El bot:

1. Busca ese mensaje en el canal de actividades correspondiente a la división (`CANALES_ACTIVIDADES["PDI"]`)
2. Verifica que el mensaje **tenga un adjunto** (imagen)
3. Verifica que el **autor del mensaje sea el mismo oficial** que está reclamando el progreso
4. Si pasa, suma +1 al progreso y postea un log con la imagen en el canal de logs

**Lo que el bot NO valida:**
- Que la imagen sea realmente evidencia de un procedimiento de PDI y no una captura reciclada de otra ocasión
- Que la misma imagen no se suba dos veces en mensajes distintos (a diferencia del sistema de robos, que sí compara hash de imagen — ver sección 8)
- Contenido de la imagen en sí (no hay verificación visual automática, es 100% confianza + revisión manual del log)

---

## 7. Competencia semanal entre subdivisiones (URA vs Halcón vs PDI)

Cada vez que un oficial completa una misión (semanal o diaria, de cualquier división), su división
suma **1 punto** en la tabla `competencia_subdivisiones`.

Al cierre de semana (ver sección 9), si **una única división** tiene estrictamente más puntos que
las otras dos, **todos los miembros con rol de esa división** reciben **+0.20 coins** de bono.
Si hay empate en el primer puesto, nadie cobra el bono esa semana.

El ranking se puede consultar en cualquier momento desde el panel de economía (botón
"Ranking Subdivisiones").

---

## 8. Sistema de "Robos Acudidos" — ¿es parte de P.D.I?

Existe un sistema paralelo (`/panelrobos`) donde un oficial sube evidencia de haber acudido a un
robo y cobra **0.04 coins** por cada uno, con protección **anti-duplicado real**: el bot calcula el
hash MD5 de la imagen adjunta y rechaza si esa misma foto ya fue usada antes (a diferencia del
sistema de pruebas de misiones, que solo valida ID de mensaje + autor, no el contenido de la imagen).

**No está confirmado en el código si este sistema es exclusivo de P.D.I.** El rol habilitado para
usarlo (`ROLES_PERMITIDOS_ROBOS`) no coincide exactamente con el rol específico de P.D.I —
comparte el rol transversal, pero tiene un ID de rol propio distinto al de PDI. Si la normativa de
P.D.I va a incluir este sistema, conviene confirmar primero qué rol de Discord es ese antes de
redactarlo, porque tal como está el bot podría estar pensado para otra unidad (posiblemente
investigación de robos como tarea específica, no necesariamente exclusiva de todo el plantel PDI).

---

## 9. Reinicios automáticos — ⚠️ BUG DETECTADO

### Reinicio diario (01:00 UTC)
Limpia diariamente las misiones diarias que quedaron activas sin completar y resetea rachas rotas.
Este sí funciona sin problemas.

### Reinicio semanal (lunes 00:00 UTC) — **actualmente roto**
Debería, cada lunes:
1. Calcular qué división ganó la competencia semanal
2. Pagar el bono de 0.20 coins a todos sus miembros
3. Resetear puntos de competencia a 0
4. Borrar todas las misiones activas y completadas (arranca la semana en blanco)
5. Anunciar "¡NUEVA SEMANA OPERATIVA!" en el canal general

**El código de este reinicio (`cogs/panel_operativo.py`, función `reset_semanal_misiones`)
usa `os.getenv(...)` para obtener el `GUILD_ID`, pero el archivo nunca importa el módulo `os`.**
Esto provoca un `NameError` en tiempo de ejecución la primera vez que se intenta calcular el
ganador de la semana. Como todo el bloque está envuelto en un `try/except: pass` silencioso,
**el error no se ve en ningún lado — el reinicio simplemente no ocurre nunca**, ni el pago del
bono, ni el borrado de misiones, ni el anuncio semanal.

> Esto significa que, tal como está el bot hoy, las misiones semanales **nunca se resetean solas**
> y el bono de subdivisión ganadora **nunca se paga**. El único reset que funciona es el manual vía
> `/reset_misiones_semanal` (borra misiones pero no paga el bono tampoco, ya que ese comando no
> incluye la lógica de premiación).

Si querés, puedo arreglar este bug por separado (agregar `import os` al archivo) — no lo toqué
todavía porque me pediste específicamente el handoff, no el fix. Avisame si querés que lo corrija.

---

## 10. Comandos disponibles para staff

| Comando | Rol requerido | Qué hace |
|---|---|---|
| `/panelpdi` | Admin/Staff | Despliega el panel operativo de PDI |
| `/panelpruebas` | Admin/Staff | Despliega el panel para subir evidencia |
| `/panelrobos` | Admin/Staff | Despliega el panel de robos acudidos |
| `/reset_misiones_semanal` | Admin/Staff | Borra manualmente todas las misiones activas y completadas (sin pagar bono de división) |
| `/reset_total_usuario <usuario>` | Admin/Staff | Borra la misión activa y completada de un oficial puntual |
| `/limpiar_diarias_ahora` | Admin/Staff | Fuerza la limpieza de misiones diarias y rachas rotas |

---

## 11. Tablas en base de datos relevantes a P.D.I

| Tabla | Qué almacena |
|---|---|
| `misiones_activas` | Misión semanal en curso por usuario (con su `division` y `progreso`) |
| `misiones_diarias_activas` | Misión diaria en curso por usuario |
| `misiones_completadas` | Historial de semanales completadas |
| `misiones_diarias_completadas` | Registro de qué día ya se hizo la diaria (para bloquear repetición) |
| `rachas_diarias` | Contador de racha de días consecutivos completando la diaria |
| `competencia_subdivisiones` | Puntos acumulados por URA / Halcón / PDI en la semana |
| `evidencias_usadas` | Hashes de imágenes usadas en el sistema de robos (anti-duplicado) |
| `robos_acudidos` | Contador total de robos acudidos por usuario |

---

## 12. Lo que el bot NO define — pendiente de normativa

- **Qué cuenta como "procesar una persona"** a los fines de la meta semanal/diaria — el bot no
  tiene ninguna noción de esto, solo cuenta capturas subidas manualmente
- **Qué es evidencia válida** — formato, ángulo, contenido mínimo de la foto (el bot solo valida
  que exista un adjunto y que lo suba el propio autor, nada de contenido)
- **Qué pasa si un oficial sube una foto vieja o de otra sesión** — no hay control de fecha/hora
  en la imagen, solo se valida el autor del mensaje
- **Sanciones por farmeo de misiones** — este sistema es independiente del sistema de sanciones
  ya documentado (ver `HANDOFF_SANCIONES.md`); si un oficial abusa del sistema de pruebas, la
  única herramienta disponible hoy es aplicarle manualmente una advertencia/strike con motivo
  "Farmeo de horas" u "Otro", no hay detección automática de fraude en las pruebas de PDI
- **Requisitos para entrar a P.D.I** — jerarquía mínima, evaluación de ingreso, período de prueba:
  nada de esto está en el bot, es puramente asignación manual del rol
- **Qué hace un encargado de P.D.I frente a un oficial que nunca completa misiones** — el bot no
  tiene ningún reporte de inactividad específico de P.D.I (a diferencia del sistema de limpieza de
  inactivos general, que es por rol @PFA completo, no por subdivisión)
- **Cómo se reparte/valida el rol compartido** que aparece en las tres divisiones — si es
  intencional que habilite pertenecer a más de una subdivisión a la vez o es un descuido de
  configuración de roles

---

## 13. Valores hardcodeados que la normativa debería citar tal cual

| Parámetro | Valor actual |
|---|---|
| Meta misión semanal PDI | **10 personas procesadas** |
| Meta misión diaria PDI | **3 personas procesadas** |
| Recompensa semanal | **5.00 coins** |
| Recompensa diaria | **1.50 coins** |
| Bono por racha de 7 días diarios seguidos | **+0.50 coins** extra |
| Bono semanal a la división ganadora | **0.20 coins por miembro** (actualmente no se paga, ver sección 9) |
| Recompensa por robo acudido | **0.04 coins** por evidencia única |
