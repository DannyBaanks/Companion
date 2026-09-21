# Privacidad y seguridad

Companion es una mascota virtual local. Su diseño parte de una idea sencilla:
la criatura puede ser expresiva sin tener permiso para hacer cosas peligrosas
en tu máquina.

## Garantías

- No hay IA, nube, cuentas ni telemetría.
- No se ejecuta shell: reminders y mensajes son datos, nunca comandos.
- No se usa `shell=True` ni `os.system`.
- No hay red por defecto.
- El WebSocket es opcional y solo acepta localhost.
- Los packs no pueden ejecutar acciones; solo describen imágenes y estados.
- Las rutas de packs no pueden escapar de su propia carpeta.
- Las configuraciones se resuelven relativas a su archivo.
- Los estados y reminders se escriben de forma atómica.
- El JSON corrupto se conserva como `*.corrupt` antes de recuperarse.
- El Hub solo detiene procesos que él mismo inició.
- Forge no reporta una instalación como completada si el ejecutor real no está
  disponible.

## Qué significa “local”

La mascota puede recibir eventos de programas locales mediante JSONL, hooks,
OpenCode, OpenISy TUI o un WebSocket explícitamente activado. Eso no convierte
la mascota en un agente con autoridad: Companion presenta estados y mensajes,
pero no decide ni ejecuta acciones por su cuenta.

## Diagnóstico

```bash
companion --root .companion doctor
companion --root .companion doctor --json
```

Doctor informa `READY`, `NEEDS_ACTION`, `BLOCKED` o `UNKNOWN`. Un resultado
`UNKNOWN` significa que algo no pudo comprobarse; no se disfraza de éxito.

## Verificación de desarrollo

```bash
python3 -m pytest -q
```

La suite incluye pruebas de protocolo, persistencia, packs, reminders,
aislamiento local, Hub, Doctor, Forge y ausencia de shell/red remota.

Si encuentras un problema de seguridad, no lo publiques con credenciales,
tokens ni datos privados. Abre un reporte local para el mantenedor con pasos
de reproducción mínimos y el impacto observado.
