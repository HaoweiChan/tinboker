#!/bin/sh
# Cut the full-page captures (393 css px wide @ dpr3) into the pieces index.html animates.
# Rects are css px from shots/<page>.json; re-check them after a UI change.
set -e
while read name src x y w h; do
  ffmpeg -loglevel error -y -i "shots/$src.png" -vf "crop=$((w*3)):$((h*3)):$((x*3)):$((y*3))" "assets/$name.png"
done <<'RECTS'
ep_summary episode_87a8b530_7b3af90bb6d19850 17 349 359 426
gy_head home 17 4600 359 101
gy_bullets home 17 4700 359 168
gy_tickers home 17 4868 359 259
market_week home 17 82 359 299
most_talked home 17 452 359 384
bubble topics 17 346 359 459
stock_head stock_2330 17 82 359 72
stock_chart stock_2330 17 171 359 338
consensus stock_2330 17 523 359 359
op_gooaye stock_2330 18 2580 357 156
RECTS
