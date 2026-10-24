#!/bin/sh
# Offline only. inputs.json covers tools, runtime, wheels, sources and licenses.
set -eu
test "$#" = 2 || { printf '%s\n' 'usage: build.sh INPUTS OUTPUT_DIRECTORY' >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
inputs=$(realpath "$1")
output=$(realpath -m "$2")
test ! -e "$output" || { printf '%s\n' 'output already exists' >&2; exit 1; }
python3 "$here/prepare.py" --inputs "$inputs" --output "$output/stage"
(cd "$output/stage" && "$inputs/fnpack" build)
mv "$output/stage/fnos_music_hub.fpk" "$output/fnos-music-hub-0.1.0-preview.1-amd64.fpk"
python3 "$here/verify.py" "$output/fnos-music-hub-0.1.0-preview.1-amd64.fpk" --report "$output/build-report.json"
(cd "$output" && sha256sum ./*.fpk ./*-sources.tar.gz > SHA256SUMS)
