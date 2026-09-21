# Protocolo de eventos de Companion v1

Este es el sistema nervioso de la mascota. Es un protocolo local, append-only
y basado en JSONL. Los productores escriben eventos en `inbox.jsonl`; el
runtime los procesa y escribe acuses en `outbox.jsonl`.

La versión congelada para la serie 1.x es `companion-event-v1`. Los campos
nuevos deben ser opcionales para no romper lectores anteriores. Los tipos de
evento nuevos requieren una actualización menor de versión y de esta
especificación.

## Envoltorio de evento

Campos obligatorios:

```json
{
  "version": "companion-event-v1",
  "id": "evt-001",
  "agent": "terra",
  "created_at": "2026-09-09T12:00:00Z",
  "type": "say",
  "text": "Hola desde mi mascotita",
  "ttl": 8,
  "priority": 0
}
```

`id` debe ser único por productor y `created_at` debe ser una fecha ISO-8601.

Tipos soportados:

- `summon`: mostrar la mascota.
- `hide`: ocultarla.
- `say`: mostrar texto.
- `state`: cambiar estado semántico.
- `mood`: cambiar ánimo/presentación.
- `move`: cambiar posición.
- `status`: publicar información de estado.

Los estados son `idle`, `thinking`, `working`, `success`, `error`, `waiting`
y `hidden`. Las posiciones son `top-left`, `top-right`, `bottom-left`,
`bottom-right`, `dock` y `free`.

Un evento `say` necesita texto no vacío. `ttl` es un número no negativo y
`priority` es un entero; los mensajes con mayor prioridad se muestran antes.

## Entrega

El runtime procesa líneas completas en el orden en que aparecen. Una línea sin
salto final se espera hasta que el productor termine de escribirla. Las líneas
inválidas generan un reporte de error, pero no detienen a la mascota.

Para un evento aceptado se escribe un acuse como:

```json
{
  "version": "companion-event-v1",
  "status": "accepted",
  "event_id": "evt-001",
  "event_type": "say"
}
```

El runtime conserva el offset de lectura para no procesar dos veces un evento
después de reiniciar.

## Reminders locales

Los reminders viven en `reminders.json` y usan el mismo pipeline de eventos:

```json
{
  "id": "rem_001",
  "due_at": "2026-09-09T19:30:00-06:00",
  "message": "Tomar agua",
  "companion_id": null,
  "ttl": 8,
  "status": "pending"
}
```

Los estados son `pending`, `fired`, `cancelled` y `snoozed`. Un reminder se
dispara cuando `now >= due_at`, no solo cuando la hora coincide exactamente.
Los reminders vencidos pendientes se disparan una vez al iniciar. Uno
cancelado nunca emite eventos.

La recurrencia puede ser `daily`, `weekly` o `countdown`. Los timers y
Pomodoros son productores que crean records normales; no son una autoridad
especial del runtime.

El texto del reminder es siempre datos. Nunca se interpreta como shell,
Python, JavaScript ni una acción ejecutable.

## Packs visuales

Un pack es una carpeta con `manifest.json` y archivos PNG/GIF relativos:

```json
{
  "id": "mi-mascota",
  "name": "Mi Mascota",
  "animations": {
    "idle": "idle.gif",
    "success": "success.gif"
  }
}
```

El loader rechaza manifests malformados, estados desconocidos, archivos
faltantes y rutas que escapen de la carpeta del pack. El renderer selecciona
`mood`, después `state`, después `idle`.

Un estado opcional faltante usa `idle`. Si no hay una imagen usable, la ventana
muestra el nombre y el estado como texto accesible en vez de fallar en silencio.

## Personalidad

La personalidad es una capa local de presentación. Puede cambiar el tono,
verbosidad y frases, pero no interpreta eventos ni añade autoridad. No hay
inferencia ni llamadas de red dentro de Companion.

## Hub

El Hub mantiene un catálogo local de companions y controla únicamente los
procesos que él mismo inició. `Start`, `Hide`, `Show` y `Stop` deben producir
un efecto comprobable o dejar el estado como `failed`; el estado visual nunca
debe ser una promesa desconectada del runtime real.
