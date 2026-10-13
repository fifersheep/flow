#!/usr/bin/env bash
# Render a terminal capture (text with ANSI colours) to a PNG for the README.
#
#   scripts/demo/render.sh CAPTURE.ansi OUT.png
#
# freeze draws the capture as an SVG with the font embedded; headless Chrome
# rasterises it at 2x. (freeze's own PNG output drops an embedded font, and
# the box-drawing frame only lines up in a monospace face.)
#
# Needs: freeze (brew install charmbracelet/tap/freeze), Google Chrome, and
# FONT=path/to/JetBrainsMono-Regular.ttf (github.com/JetBrains/JetBrainsMono).
set -euo pipefail

src=${1:?usage: render.sh CAPTURE.ansi OUT.png}
out=${2:?usage: render.sh CAPTURE.ansi OUT.png}
font=${FONT:?set FONT to a JetBrains Mono .ttf}
chrome=${CHROME:-"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp "$src" "$work/capture.ansi"

(cd "$work" && freeze -x "cat capture.ansi" -o shot.svg \
  --window --background "#1e1e2e" --padding 20,24 --margin 0 --border.radius 10 \
  --font.file "$font" --font.family "JetBrains Mono" --font.size 14 --line-height 1.35 </dev/null >/dev/null)

read -r w h < <(sed -n 's/.*<svg width="\([0-9.]*\)" height="\([0-9.]*\)".*/\1 \2/p' "$work/shot.svg" | head -1)
w=$(printf '%.0f' "$w"); h=$(printf '%.0f' "$h")
cat > "$work/shot.html" <<EOF
<!doctype html><html><body style="margin:0;background:transparent">
<img src="shot.svg" width="$w" height="$h" style="display:block"></body></html>
EOF

# a profile of its own, or a running Chrome takes the call and nothing returns
"$chrome" --headless=new --user-data-dir="$work/profile" --no-first-run --disable-gpu \
  --hide-scrollbars --force-device-scale-factor=2 --virtual-time-budget=2000 \
  --default-background-color=00000000 --window-size="$w,$h" \
  --screenshot="$work/shot.png" "file://$work/shot.html" >/dev/null 2>&1
mv "$work/shot.png" "$out"
echo "$out"
