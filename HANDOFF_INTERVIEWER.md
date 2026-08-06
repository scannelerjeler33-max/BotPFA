# Handoff — Sistema de Interviewer PFA · Ibiza Roleplay

> Documento de referencia técnica y operativa para redactar las normativas del cuerpo de Interviewers.
> Cubre exactamente lo que el bot implementa, lo que deja abierto, y qué decisiones de política quedan pendientes.

---

## 1. ¿Qué es un Interviewer?

Un Interviewer es el oficial autorizado para tomar las oposiciones de ingreso a la PFA. Es el único rol habilitado para abrir una sesión oficial, evaluar postulantes y cerrarla. Todo lo que hace queda registrado en la base de datos con su ID de Discord, fecha y resultado.

---

## 2. Roles del sistema

| Rol | Qué puede hacer |
|---|---|
| `@Interviewer` | Operar el panel: abrir/cerrar sesiones, evaluar, ver sus propias estadísticas |
| `@Encargado Interviewer` | Todo lo anterior + ver estadísticas de todo el equipo, consultar interviewers individuales, ejecutar el cierre semanal. También puede desplegar los paneles |
| `@Panel Admin` | Igual que Encargado — rol técnico de administración del bot |

---

## 3. Mecánica completa del sistema (lo que el bot hace)

### 3.1 Ciclo de una sesión

```
[Interviewer abre oposiciones]
        ↓
   Bot crea registro en DB (oposiciones_sesiones)
   Bot publica anuncio en CANAL_POSTULACIONES con @civil + link al canal de postulaciones
   Bot registra apertura en CANAL_BITACORA con timestamp
        ↓
[Interviewer evalúa postulantes — uno por uno]
        ↓
   Si nota ≥ 10/15 → aprobación
   Si nota ≤ 9/15  → desaprobación + cooldown 3 días
        ↓
[Interviewer cierra oposiciones]
        ↓
   Bot valida mínimo de 30 minutos desde apertura
   Bot publica resumen en CANAL_BITACORA (duración, evaluados, aprobados/desaprobados)
   Bot publica aviso de cierre en CANAL_POSTULACIONES
```

### 3.2 Apertura de oposiciones — detalle

El interviewer completa un modal con:
- Horario de inicio
- Horario de cierre estimado
- Mensaje adicional opcional (ej: "traer cédula del personaje")

El bot publica en `CANAL_POSTULACIONES`:
```
📋 OPOSICIONES EN CURSO PARA INGRESAR A LA P.F.A!
Las oposiciones de ingreso [...] actualmente activas, a cargo de [Nombre del Interviewer].
⏰ Horario estimado: HH:MM — HH:MM
@civil
[mensaje_extra si lo hay]
Ingresa a #canal-de-postulaciones para postularte y aguardá a ser llamado.
```

**Restricción del bot:** Un interviewer solo puede tener **una sesión activa a la vez**. Si intenta abrir otra sin cerrar la anterior, el bot lo bloquea.

### 3.3 Evaluación — detalle

El interviewer carga en el modal:
- ID de Discord del postulante
- Nota obtenida (0–15)
- ID del invitador (opcional — si el postulante fue referenciado por alguien)

**El bot determina automáticamente si aprueba o desaprueba según la nota.**

**Restricción del bot:** No se puede evaluar sin tener una sesión activa abierta.

#### Si aprueba (nota ≥ 10):
1. Verifica que el postulante no tenga ya el rol @PFA (evita duplicados)
2. Asigna roles: `@PFA`, `@LowPFA`, `@Cadete`, `@NuevoIngresante`
3. Llama al sistema de Nuevo Ingresante (timer de 7 días para quitar @NuevoIngresante)
4. Limpia el cooldown del postulante si lo tenía de un intento anterior
5. Publica en `CANAL_RESULTADOS`:
   ```
   ✅ @Postulante aprobó las oposiciones con X/15 respuestas correctas. ¡Bienvenido/a a la PFA! 🎉
   👮 Interviewer: @Interviewer
   👥 Invitado/a por: @Invitador  ← solo si aplica
   ```
6. Publica en `CANAL_CAMBIOS_PFA`:
   ```
   ✅ @Postulante > cadete > Nuevo [Autorizado por: @Interviewer]
   📝 Nota: X/15 | 👥 Invitado por: @Invitador  ← solo si aplica
   ```
7. Envía DM de bienvenida al postulante con canales esenciales y aviso de doble facción
8. Si el invitador acumula un múltiplo de 3 invitaciones aprobadas (3, 6, 9...), el bot notifica en `CANAL_CAMBIOS_PFA` que un encargado debe evaluar su reconocimiento

#### Si desaprueba (nota ≤ 9):
1. Registra el resultado en DB
2. Aplica cooldown de **3 días** al postulante (fecha exacta almacenada en DB)
3. Publica en `CANAL_RESULTADOS`:
   ```
   ❌ @Postulante no aprobó las oposiciones (X/15).
   Podés volver a postularte en 3 días. ¡Mucha suerte la próxima! 💪
   👮 Interviewer: @Interviewer
   ```
4. Envía DM al postulante con la nota, el mínimo requerido y la fecha exacta desde la que puede volver a postularse

### 3.4 Cierre de sesión — detalle

**Validación del bot:** La sesión debe tener al menos **30 minutos** de antigüedad. Si no pasaron, el bot lo bloquea con un mensaje indicando cuántos minutos faltan.

Al cerrar, el bot publica en `CANAL_BITACORA`:
```
🔴 Oposición #N — Semana XX
A cargo de: @Interviewer
📅 Apertura: HH:MM  |  📅 Cierre: HH:MM  |  ⏰ Duración: Xh Ym
👥 Cuestionarios tomados: N personas evaluadas
✅ X aprobaron · ❌ Y desaprobaron
```

Y publica en `CANAL_POSTULACIONES`:
```
🔴 Las oposiciones han finalizado.
La sesión a cargo de [Nombre] ha concluido. ¡Gracias a todos los que se presentaron!
```

---

## 4. Canales involucrados

| Canal | Qué se publica ahí |
|---|---|
| `CANAL_POSTULACIONES` | Anuncio de apertura (público, con @civil) · Aviso de cierre |
| `CANAL_RESULTADOS` | Resultado de cada evaluación (aprobado / desaprobado) con nombre del interviewer |
| `CANAL_BITACORA_OPOS` | Registro interno de apertura y cierre de cada sesión con estadísticas |
| `CANAL_CAMBIOS_PFA` | Registro de ingresos y milestones de invitaciones |

---

## 5. Sistema de estadísticas

### Vista del Interviewer (solo sus propios datos)
Accesible desde el panel con "📊 Mis Estadísticas". Muestra la semana en curso:
- Cantidad de sesiones abiertas
- Horas totales de oposiciones
- Total evaluados / aprobados / desaprobados
- Lista nominada de postulantes aprobados con su nota
- Si hay sesión activa, muestra la hora de apertura

### Vista del Encargado (todos los interviewers)
Accesible desde el panel de encargado. Botones disponibles:

| Botón | Qué muestra |
|---|---|
| 📊 Resumen Semanal | Stats de todos los interviewers: sesiones, horas, aprobados, desaprobados |
| 🏆 TOP Interviewers | Ranking ordenado por cantidad de aprobados, con medallas para el top 3 |
| 🔍 Consultar Interviewer | Informe individual completo: evaluación por evaluación, notas, invitadores |
| 📋 Oposiciones Activas | Qué interviewers tienen sesión abierta ahora mismo y desde hace cuánto |
| 📅 Historial de la Semana | Todas las sesiones cerradas de la semana con horarios y duración |

---

## 6. Cierre semanal — `/cierresemanal`

Comando exclusivo del Encargado Interviewer o Panel Admin. Hace lo siguiente:

1. **Verifica** que la semana no haya sido cerrada ya (solo un cierre por semana ISO)
2. **Fuerza el cierre** de cualquier sesión que haya quedado abierta sin cerrar
3. **Archiva** el resumen completo en la tabla `oposiciones_cierre_semanal` con JSON detallado
4. **Publica el informe** en `CANAL_BITACORA_OPOS` con totales globales y tabla por interviewer

> **El "reset" de estadísticas es automático e implícito:** no hay un comando de reset. Las estadísticas de cada semana son independientes porque cada registro almacena el número de semana ISO. Al cambiar de semana, los paneles automáticamente muestran datos del nuevo período (vacíos hasta que haya actividad).

---

## 7. Sistema de invitaciones

Cuando un postulante aprueba y se registra un invitador, el bot cuenta el total histórico de invitaciones aprobadas de ese oficial. Cada vez que alcanza un **múltiplo de 3** (3, 6, 9, 12...), el bot publica en `CANAL_CAMBIOS_PFA`:

```
🌟 @Invitador alcanzó N invitaciones aprobadas. ¡Un encargado debe evaluar su reconocimiento!
```

El bot **solo notifica** — no asigna rol ni ejecuta ninguna acción adicional. La decisión de recompensar al invitador es manual.

---

## 8. Tablas en base de datos

| Tabla | Qué almacena |
|---|---|
| `oposiciones_sesiones` | Cada sesión (apertura, cierre, interviewer, semana ISO, número de opo de la semana, estado activo) |
| `oposiciones_resultados` | Cada evaluación individual (postulante, nota, aprobado, invitador, interviewer, semana ISO) |
| `oposiciones_cooldown` | Fecha desde la cual un postulante puede volver a intentarlo |
| `oposiciones_cierre_semanal` | Archivo histórico de cada cierre semanal con JSON completo de stats |

---

## 9. Lo que el bot NO define — pendiente de normativas

El bot ejecuta mecánicas, no toma decisiones de criterio. Todo lo que sigue **necesita una normativa escrita**:

### 9.1 Sobre los requisitos para ser Interviewer
- ¿Qué jerarquía mínima dentro de la PFA se necesita para ser Interviewer?
- ¿Se necesita una evaluación o prueba interna para obtener el rol?
- ¿Existe un período de prueba como Interviewer antes de ser confirmado?
- ¿Cuántos Interviewers puede haber simultáneamente en el servidor?

### 9.2 Sobre la conducta durante las oposiciones
- ¿Cómo debe presentarse el Interviewer al abrir oposiciones? (en voz, en texto, ambos)
- ¿Debe el Interviewer identificarse con su nombre PFA o puede usar el de Discord?
- ¿Puede un Interviewer evaluar a alguien que conoce o con quien tiene relación directa? (conflicto de interés)
- ¿Puede el Interviewer suspender una sesión en curso si no hay postulantes?

### 9.3 Sobre el cuestionario
- El bot registra la nota pero **no sabe qué preguntas se hacen**. ¿El cuestionario es estándar y fijo?
- ¿Quién elabora y actualiza las preguntas?
- ¿El cuestionario puede ser adaptado o el Interviewer tiene margen de criterio?
- ¿Hay penalización por copiar respuestas o asistencia externa durante el examen?

### 9.4 Sobre la frecuencia y organización
- ¿Cuántas veces por semana puede (o debe) abrir sesiones un Interviewer?
- ¿Existe un mínimo de sesiones semanales para mantener el rol?
- ¿Deben coordinarse entre sí los Interviewers para no abrir varias sesiones simultáneas?
- ¿Hay horarios preferidos o restricciones de horario para abrir oposiciones?

### 9.5 Sobre los resultados
- ¿Un Interviewer puede rechazar a un postulante por razones que no sean la nota? (actitud, historial, etc.)
- Si un postulante es problemático durante las oposiciones, ¿el Interviewer puede descalificarlo sin evaluarlo?
- ¿Un Interviewer puede aprobar con nota justa (10/15) a alguien que considera que "no está listo"?

### 9.6 Sobre el sistema de invitaciones
- ¿Qué recibe un oficial cuando alcanza 3, 6, 9 invitaciones aprobadas?
- ¿Las invitaciones se acumulan de forma permanente o se reinician?
- ¿Solo los Interviewers pueden invitar o cualquier oficial puede referenciar postulantes?

### 9.7 Sobre las consecuencias de malas prácticas
- ¿Qué pasa si un Interviewer aprueba a alguien que claramente no está preparado?
- ¿Qué pasa si no cierra una sesión y la deja abierta indefinidamente?
- ¿El bot puede registrar una sesión falsa (abrir sin tomar a nadie)? ¿Está prohibido?
- ¿Qué métricas del Encargado activan una revisión del desempeño de un Interviewer?

---

## 10. Valores hardcodeados en el bot

Estos valores están definidos en el código y no se cambian desde Discord. Si las normativas los mencionan, deben coincidir exactamente:

| Parámetro | Valor actual |
|---|---|
| Nota máxima del examen | **15 respuestas** |
| Nota mínima para aprobar | **10/15** |
| Cooldown tras desaprobar | **3 días** |
| Duración mínima de una sesión | **30 minutos** |
| Múltiplo de invitaciones que genera notificación | **cada 3** |

> Si se decide cambiar alguno de estos valores, se modifica directamente en el código (`panel_interviewer.py`, constantes `NOTA_MAXIMA`, `NOTA_MINIMA`, `COOLDOWN_DIAS`).

---

## 11. Flujo de referencia rápida para las normativas

```
ANTES DE ABRIR
  → ¿Tengo el rol @Interviewer activo?
  → ¿Tengo disponibilidad real para al menos 30 minutos?
  → ¿Me coordiné con otros interviewers activos? (si aplica por normativa)

AL ABRIR
  → Completar modal: horario inicio, horario cierre, mensaje adicional
  → El bot publica el anuncio automáticamente con @civil

DURANTE LA SESIÓN
  → Llamar postulantes y evaluar con el cuestionario oficial
  → Cargar nota en el bot con el ID del postulante
  → El bot maneja el resultado, los roles y los DMs automáticamente

AL CERRAR
  → Solo se puede cerrar luego de 30 minutos
  → El bot publica el resumen automáticamente

LUEGO DEL CIERRE
  → Las estadísticas quedan disponibles para el Encargado
  → Si hay invitaciones aprobadas en esta sesión, verificar milestones en CANAL_CAMBIOS_PFA
```
