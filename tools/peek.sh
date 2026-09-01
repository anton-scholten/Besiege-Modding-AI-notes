#!/usr/bin/env bash
#
# Runs tools/peek.cs against Besiege's assemblies, using Besiege's own embedded
# Mono and its own C# compiler. Nothing to install: if the game is on the disk,
# this works.
#
#   ./tools/peek.sh sig FileBrowserSlot
#   ./tools/peek.sh check my-claims.txt
#   ./tools/peek.sh types Selector -- UIFactory     # also load UI Factory's DLLs
#
# By default it reads Assembly-CSharp.dll and Assembly-CSharp-firstpass.dll. Put
# `-- UIFactory` at the end to add UI Factory's, or `-- <path.dll>` for any other.
# Set BESIEGE_DIR if the game is not found automatically.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="${TMPDIR:-/tmp}/besiege-notes-tools"

find_besiege() {
    if [[ -n "${BESIEGE_DIR:-}" ]]; then echo "$BESIEGE_DIR"; return; fi
    local candidates=("$HOME/.steam/steam/steamapps/common/Besiege"
                      "$HOME/.local/share/Steam/steamapps/common/Besiege")
    local vdf
    for vdf in "$HOME/.steam/steam/steamapps/libraryfolders.vdf" \
               "$HOME/.local/share/Steam/steamapps/libraryfolders.vdf"; do
        [[ -f "$vdf" ]] || continue
        while read -r lib; do candidates+=("$lib/steamapps/common/Besiege"); done \
            < <(grep -oE '"path"[[:space:]]+"[^"]+"' "$vdf" | sed -E 's/.*"([^"]+)"$/\1/')
    done
    local dir
    for dir in "${candidates[@]}"; do
        [[ -f "$dir/Besiege_Data/Managed/mcs.dll" ]] && { echo "$dir"; return; }
    done
    return 1
}

BESIEGE="$(find_besiege)" || { echo "Set BESIEGE_DIR to your Besiege install." >&2; exit 1; }
DATA="$BESIEGE/Besiege_Data"
export LIBMONO="$DATA/Mono/x86_64/libmono.so" MANAGED="$DATA/Managed" MONOETC="$DATA/Mono/etc"

mkdir -p "$BUILD"
for tool in besiegecc monohost; do
    if [[ ! -x "$BUILD/$tool" || "$HERE/$tool.c" -nt "$BUILD/$tool" ]]; then
        gcc -O1 -o "$BUILD/$tool" "$HERE/$tool.c" -ldl
    fi
done
if [[ ! -f "$BUILD/peek.exe" || "$HERE/peek.cs" -nt "$BUILD/peek.exe" ]]; then
    "$BUILD/besiegecc" -target:exe -out:"$BUILD/peek.exe" -lib:"$MANAGED" \
        -r:Mono.Cecil.dll -r:System.dll -r:System.Core.dll "$HERE/peek.cs" >/dev/null
fi

# Split the arguments at "--": everything after it names extra assemblies.
ARGS=(); EXTRA=(); seen=0
for a in "$@"; do
    if [[ "$a" == "--" ]]; then seen=1; continue; fi
    if [[ $seen -eq 1 ]]; then EXTRA+=("$a"); else ARGS+=("$a"); fi
done

# DynamicText.dll is in the default set because the mapper's text lives there,
# and leaving it out made the shipped claims file report misses that were not.
ASMS=("$MANAGED/Assembly-CSharp.dll" "$MANAGED/Assembly-CSharp-firstpass.dll"
      "$MANAGED/DynamicText.dll")
for e in "${EXTRA[@]:-}"; do
    [[ -z "$e" ]] && continue
    if [[ "$e" == "UIFactory" ]]; then
        uif="$(find "$BESIEGE/../../workshop/content/346010/2913469777" \
                    "$BESIEGE/Besiege_Data/Mods/UIFactory" \
                    -name 'Besiege.UI.dll' -print -quit 2>/dev/null || true)"
        [[ -n "$uif" ]] || { echo "UI Factory not found." >&2; exit 1; }
        ASMS+=("$uif" "$(dirname "$uif")/Besiege.UI.Bridge.dll")
    else
        ASMS+=("$e")
    fi
done

TARGET_ASM="$BUILD/peek.exe" exec "$BUILD/monohost" "${ARGS[@]}" "${ASMS[@]}"
