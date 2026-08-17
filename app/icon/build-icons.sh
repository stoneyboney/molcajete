#!/bin/sh
# Rasterises the two SVGs in this directory into public/icons.
#
# Uses macOS's built-in qlmanage rather than sharp or svgexport: the icons
# change roughly never, and the PNGs are committed, so a clone builds without
# any of it. Run this only after editing an SVG.
set -eu

cd "$(dirname "$0")"
out=../public/icons
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$out"

render() { # svg, size, destination name
  qlmanage -t -s "$2" -o "$tmp" "$1" >/dev/null 2>&1
  mv "$tmp/$(basename "$1").png" "$out/$3"
  echo "  $out/$3  ${2}x${2}"
}

render molcajete.svg 512 icon-512.png
render molcajete.svg 192 icon-192.png
render molcajete.svg 180 apple-touch-icon-180.png
render molcajete-maskable.svg 512 icon-512-maskable.png
