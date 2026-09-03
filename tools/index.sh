#!/bin/sh
# Regenerate notes/INDEX.md from notes' own headings.
# Run after editing any note. Line numbers are what make targeted reads
# (sed -n 'A,Bp') possible, and they rot on every edit.
set -e
cd "$(dirname "$0")/.."

out=notes/INDEX.md
tmp=$(mktemp)

cat > "$tmp" <<'HEAD'
# Section index

Every `##` heading in every note, with line number. Read one section, not whole
note:

```sh
sed -n '186,265p' notes/01-loader-and-blacklist.md    # "The blacklist is a namespace..."
grep -n '^## ' notes/04-ui-factory.md                 # sections of one note
grep -rn 'DisplayInMapper' notes/                     # which notes name a symbol
```

Regenerate after editing a note: `./tools/index.sh`. Symbol map hand-kept, lives at
bottom.

HEAD

for f in notes/[0-9]*.md; do
    printf '## %s\n\n' "$(basename "$f")" >> "$tmp"
    grep -n '^## ' "$f" | sed 's/^\([0-9]*\):## /- `\1` /' >> "$tmp"
    printf '\n' >> "$tmp"
done

# Keep hand-kept symbol map across regenerations.
if [ -f "$out" ] && grep -q '^# Symbol map' "$out"; then
    sed -n '/^# Symbol map/,$p' "$out" >> "$tmp"
fi

mv "$tmp" "$out"
echo "wrote $out"
