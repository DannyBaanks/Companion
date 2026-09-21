# Open Agent Companion

<p align="center">
  <strong>Una mascotita virtual para tu escritorio.</strong><br>
  Local, expresiva, personalizable y discretamente útil.
</p>

<p align="center">
  <img src="packs/malbolge-cat/idle.gif" alt="Malbolgato, mascota virtual de Companion" width="180">
</p>

<p align="center">
  <a href="LICENSE">Licencia MIT</a> ·
  <a href="GUIA.md">Guía en español</a> ·
  <a href="SECURITY.md">Privacidad y seguridad</a> ·
  <a href="SPEC.md">Protocolo técnico</a>
</p>

**Open Agent Companion 1.0.0.** Una mascota virtual local que vive en tu
escritorio, cambia de ánimo, muestra mensajitos, recuerda cosas y puede usar
distintos packs visuales.

No necesita cuenta, nube ni inteligencia artificial. Puedes usarla sola, como
recordatorio personal, o conectarla opcionalmente a una herramienta local que
ya uses.

## ¿Qué es?

Companion es una criatura pequeña de escritorio con una ventana animada y un
protocolo local sencillo. Recibe eventos como `thinking`, `working`, `success`
o `error` y los convierte en animaciones, mensajes y cambios de humor.

La idea es simple:

```text
un evento local → la mascotita reacciona → tú entiendes qué pasó
```

## ¿Qué puede hacer?

- Mostrar una mascota PNG o GIF con estados animados.
- Cambiar de posición, opacidad, tema y pack.
- Enseñar mensajes breves con prioridad y caducidad.
- Crear reminders, timers, recurrencia, snooze y Pomodoro.
- Tener varias mascotas independientes.
- Mostrar una personalidad local configurable.
- Abrir un Hub para iniciar, ocultar y detener tus mascotas.
- Registrar actividad y ofrecer diagnósticos locales.
- Recibir eventos de una CLI, script o integración opcional.

## ¿Qué no es?

- No es un chatbot.
- No contiene un modelo de IA.
- No sincroniza datos con la nube.
- No necesita cuentas.
- No ejecuta comandos escritos en reminders.
- No instala cosas silenciosamente.
- No rastrea tu actividad.

## Instalación rápida

Linux y macOS:

```bash
python3 -m pip install --editable .
companion --root .companion init
companion --root .companion gui --pack packs/malbolge-cat --name Malbolgato
```

Windows:

```powershell
py -m pip install --editable .
companion --root .companion init
companion --root .companion gui --pack .\packs\malbolge-cat --name Malbolgato
```

La ventana es arrastrable. Presiona `Esc` para cerrarla y haz clic derecho
para abrir los controles.

## Primer mensajito

Puedes hacer que la mascota diga algo desde cualquier terminal:

```bash
companion --root .companion say "Ya llegué :p" --ttl 8
companion --root .companion run --once
```

El mensaje se guarda localmente y desaparece cuando termina su TTL.

Para cambiar su estado:

```bash
companion --root .companion mood thinking
companion --root .companion run --once
```

Los estados disponibles son `idle`, `thinking`, `working`, `success`, `error`
y `waiting`.

## Packs y estética

Un pack es una carpeta con un `manifest.json` y una imagen por estado:

```json
{
  "id": "mi-gato",
  "name": "Mi Gato",
  "animations": {
    "idle": "idle.gif",
    "thinking": "thinking.gif",
    "working": "working.gif",
    "success": "success.gif",
    "error": "error.gif",
    "waiting": "waiting.gif"
  }
}
```

Valida el pack antes de usarlo:

```bash
companion pack validate ./packs/mi-gato
companion --root .companion gui --pack ./packs/mi-gato
```

Si falta un estado opcional, Companion usa `idle` o muestra un fallback de
texto. Un pack nunca puede ejecutar acciones arbitrarias: solo define cómo se
ve la mascota.

Packs incluidos:

- `packs/malbolge-cat`: gato pixel-art neón.
- `packs/tabby-shinji-cat`: gato tabby con estética anime.
- `examples/example-cat`: pack mínimo para experimentar.

## Personalidad

La personalidad es presentación, no inteligencia. Se puede guardar localmente
en `personality.json`:

```json
{
  "tone": "playful",
  "verbosity": "low",
  "greeting": "Holi :p",
  "success_message": "Listo, quedó precioso.",
  "error_prefix": "Ups:"
}
```

Los tonos disponibles son `friendly`, `formal`, `playful` y `minimal`.

## Reminders y timers

```bash
companion --root .companion remind add --in 10m --message "Tomar agua"
companion --root .companion remind list
companion --root .companion remind snooze rem_... --minutes 15
companion --root .companion timer --in 5m --message "Revisar el horno"
companion --root .companion pomodoro --work 25 --break 5 --message "Foco"
```

Los reminders son datos. La mascota nunca interpreta su texto como código ni
lo ejecuta como shell.

## Companion Hub

El Hub es la casita de tus mascotas:

```bash
companion --root .companion hub
```

Desde ahí puedes crear mascotas, iniciar una instancia real, ocultarla,
mostrarla o detenerla. El Hub conserva estados honestos: si un proceso no
arranca, aparece como fallido; no pinta `running` solo porque alguien hizo
clic.

Temas disponibles:

```bash
companion --root .companion hub --theme dark
companion --root .companion hub --theme light
companion --root .companion hub --theme soft-neon
```

## Integraciones opcionales

Companion puede recibir eventos de procesos locales mediante:

- hook JSONL genérico;
- WebSocket opcional limitado a localhost;
- adaptador de OpenCode;
- adaptador de OpenISy TUI.

Estas integraciones son accesorios. La mascota sigue funcionando sin agentes,
sin red y sin servicios externos.

## Diagnóstico

```bash
companion --root .companion doctor
companion --root .companion doctor --json
companion --root .companion path
companion --root .companion logs --tail 20
```

Doctor usa estados honestos: `READY`, `NEEDS_ACTION`, `BLOCKED` y `UNKNOWN`.
Si no puede comprobar algo, no lo presenta como perfecto.

## Arquitectura en una mirada

```text
CLI / script / integración local
              │
              ▼
        inbox.jsonl
              │
              ▼
        runtime local
              │
              ▼
       mascota animada
```

El protocolo es JSONL versionado, append-only y local. La documentación
técnica completa está en [SPEC.md](SPEC.md).

## Privacidad

Companion funciona localmente, sin cuentas y sin nube. No ejecuta shell, no
abre red por defecto y no convierte texto de reminders en acciones.

Consulta [SECURITY.md](SECURITY.md) para las garantías y los límites
verificados.

## Desarrollo

```bash
python3 -m pytest -q
```

La suite cubre runtime, protocolo, packs, reminders, GUI, Hub, Doctor,
personalidad, timeline y hardening.

El roadmap completo está en [ROADMAP.md](ROADMAP.md). Si quieres contribuir,
revisa [CONTRIBUTING.md](CONTRIBUTING.md).
