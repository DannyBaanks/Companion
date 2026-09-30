# Gatito Neón: ejemplo de mascota creada por un agente

Un agente convierte una descripción en `character.json` y recetas de
animación. Companion valida esos datos, rasteriza las capas localmente y
genera los assets; no entiende el prompt ni llama a un modelo.

Prueba el ejemplo desde la raíz de Companion:

```bash
python -m pip install -e '.[art]'
bash examples/vector-neon-cat/build.sh
```

## Prompt para un agente con consola

> Diseña una mascota original a partir de esta descripción: [DESCRIPCIÓN].
> Escribe `character.json` con el esquema `companion-character-v1` y recetas
> `*.animation.json` con `companion-animation-v1` para idle, thinking, working,
> waiting, success, error, running-right, running-left y drag. Separa las
> partes móviles en capas con pivotes. Reutiliza o agrega piezas a una
> biblioteca `companion-parts-v1` para ojos, patas, orejas, hocico y accesorios.
> Usa solo las formas de la guía. Ejecuta
> `bash examples/vector-neon-cat/build.sh` y corrige los errores de validación.
> Mantén la mascota original; no copies los assets de ejemplo. No uses APIs,
> generadores de imagen ni archivos con código ejecutable.

La cuadrícula de formas soportadas y las reglas de animación están descritas
en [la guía de recetas](../../docs/ART_RECIPES.md).

La biblioteca `parts/feline-v1.json` trae ojo, pata, interior de oreja y placa
de pecho. Cada parte acepta ranuras de color para adaptar la misma geometría a
otra paleta. El personaje también declara roles de rig (`body`, `head`,
`tail`, `front-paws` y ojos); las animaciones apuntan a esos roles con `$`, así
puedes reutilizar sus keyframes en otro personaje cambiando `character` y su
mapa `rig`.
