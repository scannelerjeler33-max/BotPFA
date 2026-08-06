# Handoff — Sistema de Sanciones PFA · Ibiza Roleplay

## 1. Contexto general

La PFA (Policía Federal Argentina) es una facción dentro del servidor de FiveM Ibiza Roleplay, gestionada íntegramente a través de un bot de Discord. El bot administra ingresos, roles, oposiciones y sanciones. Este documento cubre exclusivamente el subsistema de sanciones.

---

## 2. Tipos de sanción implementados

El bot distingue dos tipos de sanción formales, independientes entre sí pero interconectadas por una regla automática.

### 2.1 Advertencia (Warn)

| Campo | Detalle |
|---|---|
| Tabla DB | `advertencias` + `advertencias_historial` |
| Límite visible | 3 (se muestra como X/3) |
| ID | Alfanumérico de 13 caracteres (ej: `aB3kR7mQz2Xpw`) |
| Canal de registro | `CANAL_ADVERTENCIAS_ID` |
| Notificación al sancionado | DM automático con Warn ID, razón, contador y botón de ticket de apelación |
| Historial de acciones | AGREGADA · ELIMINADA · CONVERTIDA |

**Regla automática de conversión:** Al acumularse **3 advertencias activas**, el bot las elimina automáticamente y genera **1 Strike** con razón `"Acumulación de 3 advertencias"`. El evento queda registrado tanto en el canal de advertencias como en el canal de strikes.

### 2.2 Strike

| Campo | Detalle |
|---|---|
| Tabla DB | `strikes` + `strikes_historial` |
| Límite visible | 3 (se muestra como X/3) |
| ID | Alfanumérico de 13 caracteres |
| Canal de registro | `CANAL_STRIKES_ID` |
| Notificación al sancionado | DM automático con Strike ID, razón, contador y botón de ticket de apelación |
| Historial de acciones | AGREGADO · ELIMINADO |

> ⚠️ **El bot actualmente no ejecuta ninguna acción automática al llegar a 3 strikes.** El techo de 3 es solo visual/informativo — la consecuencia (baja, suspensión, etc.) la aplica un encargado de forma manual.

---

## 3. Flujo de escalada (mecánica actual)

```
Warn 1/3
  ↓
Warn 2/3
  ↓
Warn 3/3 → [AUTO] Convierte las 3 warns en Strike 1/3
  ↓
Strike 2/3  (manual)
  ↓
Strike 3/3  (manual)
  ↓
[ACCIÓN MANUAL DEL ENCARGADO — no definida en el bot]
```

---

## 4. Paneles disponibles

### Panel de Advertencias — `/paneladvertencias`
Requiere rol `Panel Admin` o `Perms`.

| Botón | Acción |
|---|---|
| ⚠️ Add Warn | Modal: Discord ID + razón |
| ❌ Remove Warn | Modal: Warn ID + motivo de eliminación |
| 🔍 Search Warn | Modal: Warn ID → embed con info |
| 👤 Search User | Modal: Discord ID → lista de warns activas + botón de historial completo |

### Panel de Strikes — `/panelstrikes`
Requiere rol `Panel Admin` o `Perms`.

| Botón | Acción |
|---|---|
| ⚠️ Add Strike | Modal: Discord ID + razón |
| ❌ Remove Strike | Modal: Strike ID + motivo |
| 🔍 Search Strike | Modal: Strike ID → embed con info |
| 🔎 Search User | Modal: Discord ID → lista de strikes activos + botón de historial completo |

---

## 5. Reinicio de sanciones al retirar un oficial

Cuando se retira a alguien de la PFA (flujo de baja en `panel_gestion_pfa.py`), el bot envía automáticamente a un canal interno una vista con dos botones:

- **Sí, eliminar sanciones** — borra todos los strikes y warns activos del oficial, registrando cada eliminación en los historiales con motivo `"Retiro de facción"`.
- **No, conservar sanciones** — no modifica nada.

La vista tiene un timeout de **10 minutos**. Solo pueden confirmar: Head PFA, Panel Admin y el rol de permisos generales.

---

## 6. Apelaciones

Todo DM de sanción (warn o strike) incluye un botón directo al canal de tickets del servidor. No hay flujo automático de apelación dentro del bot — el ticket lo gestiona el equipo de forma manual.

---

## 7. Lo que el bot NO define (pendiente de política interna)

El bot es un ejecutor de sanciones, no un árbitro. Los siguientes criterios **no están definidos en ninguna parte del sistema** y son los que necesitan un manual:

- Qué conductas califican como **falta leve** → ameritan warn
- Qué conductas califican como **falta grave** → ameritan strike directo (sin pasar por warns)
- Qué conductas son **expulsables inmediatamente** (baja directa sin sanciones previas)
- Qué sucede cuando un oficial acumula **3 strikes** (el bot lo muestra pero no actúa)
- Si los warns/strikes tienen **vencimiento** o son permanentes mientras el oficial esté en la facción
- Criterios de apelación: quién puede revertir una sanción y bajo qué condiciones
- Si hay **diferencia de criterio por jerarquía** (¿un oficial de alto rango recibe la misma sanción que un cadete?)

---

## 8. Roles con acceso al sistema de sanciones

| Rol | Puede aplicar sanciones | Puede confirmar reinicio al dar de baja |
|---|---|---|
| `Panel Admin` | ✅ | ✅ |
| `Perms` | ✅ | ✅ |
| `Head PFA` | ❌ (no tiene acceso al panel) | ✅ |
| Resto | ❌ | ❌ |
