#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
export PYTHONPATH="$repo_root/src${PYTHONPATH:+:$PYTHONPATH}"

pack="examples/vector-neon-cat"
python -m companion.cli art validate "$pack/character.json"
python -m companion.cli art render "$pack/character.json" --output "$pack/preview.png"

for recipe in "$pack"/*.animation.json; do
    stem="${recipe##*/}"
    stem="${stem%.animation.json}"
    python -m companion.cli animate validate "$recipe"
    python -m companion.cli animate render "$recipe" \
        --output "$pack/$stem.gif" \
        --atlas "$pack/$stem-atlas.png"
done

python -m companion.cli pack validate "$pack"
