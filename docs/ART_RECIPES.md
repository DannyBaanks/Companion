# Recetas locales de arte y animación

Los agentes pueden crear mascotas sin integraciones propias: describen la
ilustración y el movimiento en dos documentos JSON, y Companion los valida y
renderiza localmente. Las recetas son datos declarativos; nunca se ejecutan
como código.

## Personaje

`companion-character-v1` requiere `id`, `name`, `canvas`, `palette` y `layers`.
El orden de `layers` es el orden de dibujo, de atrás hacia delante. Cada capa
tiene `id`, `pivot` (`[x, y]`) y una lista de `shapes`; `visible` es opcional.

Formas admitidas:

- `rect` y `ellipse`: `bounds: [x, y, width, height]`.
- `polygon`: `points: [[x, y], ...]`.
- `path`: `commands` con `M`, `L`, `C` y `Z`; una ruta permite varios
  subtrazos. `C` recibe los dos controles y el punto final de una curva cúbica.
- `image`: PNG local con `path` y `bounds`.

Las formas aceptan `fill`, `stroke`, `strokeWidth` y `opacity` cuando aplica.
Los colores son nombres de `palette` o `#RRGGBB`. Los trazos no pueden exceder
64 px; las rutas y capas tienen límites para mantener acotado el render.

El lienzo predeterminado se declara explícitamente como 192×208, con ancla de
suelo `[96, 203]`, compatible con Malbolgato.

Un personaje puede importar bibliotecas locales con `libraries`. El formato
`companion-parts-v1` define piezas en su propio lienzo y declara ranuras de
color. Una capa puede instanciar una pieza con `type: "part"`, `part`,
`bounds`, un mapa `colors` y, opcionalmente, `flipX` y `rotation` en grados.
Cada ranura debe mapearse a un nombre o color de la paleta del personaje. Las
piezas no pueden anidarse; esto mantiene la biblioteca sencilla y su render
predecible.

Una biblioteca tiene esta estructura:

```json
{
  "schema": "companion-parts-v1",
  "id": "mi-kit-de-piezas-v1",
  "parts": {
    "ojo": {
      "canvas": [24, 30],
      "colors": ["accent", "outline"],
      "shapes": [
        { "type": "ellipse", "bounds": [2, 2, 20, 26], "fill": "$accent", "stroke": "$outline", "strokeWidth": 2 }
      ]
    }
  }
}
```

Guarda el JSON junto al personaje, agrégalo a `libraries` con una ruta
relativa y coloca la pieza así: `{"type":"part","part":"ojo",
"bounds":[x,y,w,h],"colors":{"accent":"lime","outline":"ink"}}`.
Cada parte se rasteriza una vez por render y puede instanciarse varias veces
con otros tamaños, colores y reflejos.

## Rig semántico y movimientos reutilizables

Un personaje puede declarar `rig`, un mapa de roles semánticos a capas, por
ejemplo `{ "body": "torso", "tail": "tail-layer" }`. En las recetas de
animación, escribir `"layer": "$body"` anima el rol; `$tail` anima la cola.
Esto permite copiar una coreografía a otro personaje con capas internas
distintas y cambiar solo su mapa `rig`. Los ejemplos `*.animation.json` del
Gatito Neón ya usan estos roles.

El ejemplo incluye piezas de ojo, pata, interior de oreja y placa de pecho en
[`feline-v1.json`](../examples/vector-neon-cat/parts/feline-v1.json). El mismo
ojo o pata se instancia dos veces con reflejo horizontal, así que un agente
puede cambiar proporciones o colores editando una sola definición.

## Animación

`companion-animation-v1` requiere `id`, `character`, `durationMs`, `loop` y
`tracks`. `character` apunta a un archivo JSON hermano. `flipX` puede reflejar
el personaje completo para la dirección contraria. Cada track apunta a una
capa y declara keyframes crecientes en milisegundos. Los campos permitidos
son `x`, `y`, `rotation`, `scaleX`, `scaleY`, `opacity`, `visible` y `easing`;
los valores omitidos conservan su valor neutral. `easing` puede ser `linear` o
`smoothstep`.

La duración debe ser múltiplo del `frameDurationMs` (por defecto 120 ms) y de
los intervalos de 10 ms de GIF. La animación es cíclica por defecto. El atlas
usa ocho columnas salvo que `frameColumns` indique otra cantidad.

## Flujo de consola

```bash
python -m pip install -e '.[art]'
companion art validate character.json
companion art render character.json --output preview.png
companion art inspect preview.png
companion animate validate idle.animation.json
companion animate render idle.animation.json --output idle.gif --atlas idle-atlas.png
```

El agente escribe los documentos, usa los errores del validador para
corregirlos y vuelve a renderizar. Companion no contiene un parser de lenguaje
natural ni requiere conexión de red. El PNG RGBA conserva transparencia suave;
GIF solo puede conservar transparencia binaria.
