# Companion Local Pet Art and Animation Engine

**Status:** Approved for implementation  
**Date:** 2026-09-27

## Goal

Allow any console-capable agent to turn a user's text description into a
structured pet illustration and animation, then render usable Companion
assets locally. The agent writes the recipes; Companion does not interpret
natural language or call a model provider.

The first vertical slice is one original mascot and one looped GIF. The
longer-term goal is a complete Companion pack whose detail can grow toward
Malbolgato's visual richness.

## Workflow

```text
companion art validate character.json
companion art render character.json --output preview.png
companion animate validate idle.animation.json
companion animate render idle.animation.json --output idle.gif --atlas idle-atlas.png
companion pack validate path/to/generated-pack
```

Commands return concise JSON on success and a nonzero status with a useful
error on invalid input. Validation does not write output files. All source
assets and output paths are explicit and local.

## Character document

`character.json` uses the versioned `companion-character-v1` format and
contains an id, canvas, palette, and ordered layers. Layers have stable ids,
pivots, visibility, and drawing nodes. Local `companion-parts-v1` files can
define reusable parts with named color slots; character layers can place and
mirror those parts. A semantic rig maps reusable animation roles such as
`$body` or `$tail` to character layer ids. V1 supports bounded vector nodes:
rectangles, ellipses, polygons, and paths composed of move, line, cubic-curve,
and close commands. A vector node may use palette colors or literal RGB hex.
Raster image nodes may reference PNG files relative to the recipe.

The default canvas is 192×208 with the floor anchor at y=203, matching the
Malbolgato atlas. A recipe may declare another size and anchor.

## Animation document

`animation.json` uses `companion-animation-v1`, references a character file,
and declares duration, loop behavior, frame duration, and tracks keyed by
layer id. Keyframes change x/y, rotation, x/y scale, opacity, and visibility.
Numeric properties interpolate linearly or with smoothstep; visibility is
stepped. An optional `flipX` reflects the whole character for mirrored
directions. Defaults are 120 ms per frame and a looping animation.

Rendering writes an animated GIF and optionally an RGBA PNG atlas, with eight
columns by default. The atlas preserves full alpha. GIF transparency is
binary, so the atlas is the lossless interchange artifact.

## Engine boundary and safety

- Agents translate free-form prompts into the two JSON documents and revise
  them using validation and inspection output.
- Companion validates closed document shapes and renders with Pillow locally.
- Recipes cannot contain Python, shell, raw SVG, URLs, or executable
  expressions. Asset references must resolve inside the recipe directory.
- No image-generation API, provider SDK, MCP requirement, ImageMagick, or
  FFmpeg is used.
- V1 caps canvas dimensions at 1024×1024, output at 300 frames, and total
  rendered pixels at 64 million per animation.

## Milestones

1. Add the versioned document validators and local vector/raster character
   renderer, plus CLI validation, rendering, and inspection. **Implemented.**
2. Add the deterministic layer timeline renderer, transparent GIF export, and
   RGBA PNG atlas export. **Implemented.**
3. Ship an original example cat recipe with a Companion-compatible manifest
   and idle, thinking, working, waiting, success, error, running, and drag
   animations. **Implemented as the first end-to-end slice.**
4. Add reusable anatomy libraries, semantic rigs, and recipe guidance until
   an agent can produce richer mascots at Malbolgato's visual quality from
   text. The feline kit, color-slot parts, and semantic animation roles are
   implemented; broader animal libraries and motion templates remain.

## Out of scope

No built-in natural-language parser, model selection or credentials, hosted
image generation, arbitrary code plugins, or desktop playback rewrite.
