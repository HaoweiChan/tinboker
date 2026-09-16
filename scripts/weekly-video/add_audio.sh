#!/bin/bash
# Mux audio onto the weekly video.
#   ./add_audio.sh out/tinboker-weekly-2026-W36.mp4 path/to/track.mp3   → uses your track
#   ./add_audio.sh out/tinboker-weekly-2026-W36.mp4                     → synthesises a bed
set -euo pipefail
VID="$1"; TRACK="${2:-}"
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VID")
OUT="${VID%.mp4}-audio.mp4"

if [ -z "$TRACK" ]; then
  python3 "$(dirname "$0")/synth.py" >/dev/null   # writes bgm.wav next to this script
  TRACK="${BGM_WAV:-$(dirname "$0")/bgm.wav}"
fi

ffmpeg -y -v error -i "$VID" -i "$TRACK" -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k \
  -af "afade=t=out:st=$(echo "$DUR-1.5"|bc):d=1.5,loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.79:level=disabled" \
  -shortest -movflags +faststart "$OUT"

ffmpeg -hide_banner -i "$OUT" -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"
echo "done: $OUT"
