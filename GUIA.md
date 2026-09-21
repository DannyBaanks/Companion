# Guía de la mascota — Open Agent Companion 1.0.0

Esta guía está escrita para quien quiere tener una mascotita virtual en su
escritorio, no para quien quiere operar una plataforma. Puedes ignorar la
parte técnica si solo quieres invocarla, elegir un pack y dejarla vivir ahí.

## Lo que viniste a hacer

```powershell
companion --root .companion init
companion --root .companion --agent terra say "Milestone terminado" --ttl 8
companion --root .companion run --once
companion --root .companion status
```

## Regla de oro

**El texto es solo datos: el companion nunca ejecuta comandos, nunca sale a
la red por defecto y el WebSocket solo escucha en localhost si lo activas.**
Si algo te pide shell o red, no es el companion.

## Comandos, uno por uno, con salida real

(Las rutas `C:\...\guia-*` y horas son de la máquina donde se probó; la
forma del JSON es la que importa.)

```powershell
companion --version
```

```text
1.0.0
```

```powershell
companion --root .companion init
```

```text
initialized C:\Users\progr\AppData\Local\Temp\guia-dfmiqpbv
```

```powershell
companion --root .companion --agent terra say "Milestone terminado" --ttl 8
```

```text
queued say
```

```powershell
companion --root .companion run --once
```

```text
{"processed": 1}
```

```powershell
companion --root .companion status
```

```text
{"visible": true, "state": "idle", "mood": "idle", "position": "bottom-right", "message": {"text": "Milestone terminado", "ttl": 8.0, "priority": 0, "sequence": 1, "expires_at": 1789001218.8728166}}
```

```powershell
companion --root .companion remind add --in 10m --message "Revisar el horno"
```

```text
{"id": "rem_c17d3135aedf", "due_at": "2026-09-09T18:56:57.529048-06:00", "status": "pending"}
```

`--at` acepta `HH:MM` o ISO-8601. `--in` acepta `30s`, `10m`, `2h`, `1d`.
Recurrencia:

```powershell
companion --root .companion remind add --at "08:00" --message "Stand up" --recurrence daily
companion --root .companion remind add --at "09:00" --message "Reporte" --recurrence weekly --weekdays mon,fri
companion --root .companion timer --in 5m --message "Té listo"
```

```text
{"id": "rem_3f8865248d08", "due_at": "2026-09-09T18:51:58.141233-06:00", "status": "pending"}
```

```powershell
companion --root .companion remind list
```

```text
[{"id": "rem_c17d3135aedf", "due_at": "2026-09-09T18:56:57.529048-06:00", "message": "Revisar el horno", "companion_id": null, "mood": null, "ttl": 8, "created_at": "2026-09-09T18:46:57.529048-06:00", "status": "pending", "recurrence": null, "weekdays": null, "snoozed_until": null}]
```

```powershell
companion --root .companion remind snooze rem_c17d3135aedf --minutes 15
```

```text
{"id": "rem_c17d3135aedf", "status": "snoozed", "snoozed_until": "2026-09-09T19:02:05.757181-06:00"}
```

```powershell
companion --root .companion remind cancel rem_c17d3135aedf
```

```text
{"id": "rem_c17d3135aedf", "status": "cancelled"}
```

```powershell
companion --root .companion pomodoro --work 25 --break 5 --message "Foco"
```

```text
{"ids": ["rem_040a0286e992", "rem_b44003b02e97"], "due": ["2026-09-09T19:11:58.414376-06:00", "2026-09-09T19:16:58.414376-06:00"]}
```

Pomodoro solo crea dos recordatorios por el mismo pipeline; no es función
del runtime.

```powershell
companion --root .companion notify "Hola"
```

```text
{"shown": false}
```

`shown: false` significa que no hay backend instalado (`pip install
"open-agent-companion[notify]"`); el pipeline no se bloquea.

```powershell
companion --root .companion pack validate examples/example-cat
```

```text
{"id": "example-cat", "name": "Example Cat", "states": ["idle", "success"]}
```

```powershell
companion --root .companion path
```

```text
{"root": "C:\\Users\\progr\\AppData\\Local\\Temp\\guia-dfmiqpbv", "default_data_dir": "C:\\Users\\progr\\AppData\\Local\\ISyCoCompanion", "platform": "windows", "config": null, "companion_id": null}
```

```powershell
companion --root .companion doctor
```

```text
doctor: OK
root=C:\Users\progr\AppData\Local\Temp\guia-dfmiqpbv platform=win32 python=3.12.4
```

Con `--json` imprime el reporte completo. Sale con código 1 si hay
problemas.

```powershell
companion --root .companion logs --tail 3
```

```text
(sin salida si aún no hay warnings/errors; los eventos info quedan en logs.jsonl)
```

Hook genérico (cualquier proceso local puede publicar JSONL canónico):

```powershell
py -c "import json; print(json.dumps({'version':'companion-event-v1','id':'h1','agent':'hook','created_at':'2026-09-09T00:00:00Z','type':'say','text':'Hola hook'}))" | companion --root .companion hook
```

```text
{"line": 1, "status": "queued", "event_id": "h1"}
```

Múltiples companions (mismo inbox, estado independiente):

```powershell
companion --root .companion --companion-id alpha say "Hola alpha"
companion --root .companion gui --companion-id alpha
```

```text
queued say
```

Ventana gráfica:

```powershell
companion --root .companion gui --pack examples/example-cat
```

`NO PROBADO` en sesión automatizada sin interacción (clic derecho abre el
editor de recordatorios; `Esc` cierra). CLI, persistencia y pipeline sí
tienen pruebas y demo (`py examples/demo_e2e.py`).

## Cómo leer la salida

| Salida | Significado | Qué hacer |
|---|---|---|
| `queued say` | Evento en inbox | `run --once` para procesar |
| `{"processed": N}` | Eventos consumidos | Revisar `status` u `outbox.jsonl` |
| `"status": "pending"` | Recordatorio guardado | Esperar su hora o `remind fire` |
| `"status": "snoozed"` | Dormido hasta `snoozed_until` | Esperar o `cancel` |
| `"status": "cancelled"` | Nunca disparará | Crear otro si lo necesitas |
| `"status": "fired"` | Ya emitió su `say` | Ver `status` del companion |
| `doctor: OK` | Todo sano | Seguir trabajando |
| `doctor: ISSUES` + lista | Hay que reparar | Leer cada `- ...`, revisar `*.corrupt` |
| `{"shown": false}` | Sin backend de notificación | Instalar extra `notify` o ignorar |
| `{"line": N, "status": "error", ...}` | Línea JSONL inválida | Corregir el JSON enviado |

## Trampas

1. `run` sin `--once` no termina: queda encuestando cada 0.1 s. Para scripts
   usa siempre `run --once`.
2. Una línea JSONL sin salto final se espera, no se procesa a medias. Si tu
   productor no escribe `\n`, el runtime parece "colgado".
3. `remind add` exige exactamente uno de `--at` / `--in`. Con los dos o sin
   ninguno sale código 2.
4. En PowerShell, `echo '{...}' | companion hook` manda comillas simples
   literales y falla. Genera el JSON con `py -c "import json; ..."`.
5. `--root` por defecto es `./.companion`, pero `$COMPANION_ROOT` lo
   reemplaza. Si tus eventos "desaparecen", revisa `companion path`.
6. Un `state.json` corrupto no te deja tirado: se respalda a
   `state.json.corrupt` y se sigue con defaults; `doctor` lo reporta.
7. El `message` de `status` puede ser el recordatorio y no tu último `say`
   si ambos dispararon en el mismo `run --once` (cola por prioridad).

## Pack del Malbolgato y solicitudes de render

Valida el pack incluido y el contrato de personalización:

    companion --root .companion pack validate packs/malbolge-cat
    companion --root .companion render-request validate examples/render_request.json

La solicitud requiere name y style. También acepta palette, los estados
conocidos (idle, thinking, working, success, error, waiting) y
output.cell_size como un par de enteros positivos. Los campos adicionales se
conservan para que cada renderer pueda extenderla; Companion no hace llamadas
de red ni intenta generar imágenes.

## Controles de la ventana

Inicia el Malbolgato con:

    companion --root .companion gui --pack packs/malbolge-cat

También puedes guardar la selección del pack y las opciones de ventana en
`companion.toml` y arrancarlo así:

    companion --root .companion gui --config .\companion.toml

La ruta `pack` dentro de ese archivo se resuelve relativa a la carpeta donde
está `companion.toml`, no relativa a la carpeta desde la que ejecutas el
comando. Por ejemplo, si el archivo está en la raíz del proyecto,
`pack = "packs/malbolge-cat"` apunta a `packs/malbolge-cat` aunque abras la
terminal desde otra carpeta.

Arrastra con el botón izquierdo para moverla, presiona Esc para cerrar y usa
clic derecho sobre el gato para abrir los controles compactos. Desde ahí puedes
cambiar estado, posición, opacidad, visibilidad de mensajes y recargar el pack.
La recarga no modifica los archivos del pack.

Si falta un estado opcional, el renderer usa idle. Si la ventana sigue en idle,
revisa que --pack apunte a la carpeta que contiene manifest.json y vuelve a
validar el pack. Los errores de ruta, manifest o asset se muestran antes de
abrir la ventana.

## La casita: Companion Hub

Si tienes más de una mascotita, abre su casita local:

    companion --root .companion hub --theme soft-neon

Desde el Hub puedes crear una mascota y usar `Start`, `Hide`, `Show` y `Stop`.
Esos botones sí controlan la instancia real: `Start` lanza la ventana,
`Hide` y `Show` publican eventos al runtime, y `Stop` detiene el proceso que
el Hub inició.

Si una instancia no arranca, aparecerá como `failed` y podrás usar `Retry`.
El Hub no pinta una mascota como `running` solamente porque se pulsó un botón.

Los temas disponibles son `dark`, `light` y `soft-neon`. En Linux, una sesión
gráfica sin compositor puede mostrar transparencias de forma distinta; el
runtime y el fallback de texto siguen funcionando.
