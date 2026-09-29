#!/bin/sh
# contact sheet of every PNG in a folder, labelled with its time: sheet.sh dir out.png cols
d=$1; out=$2; cols=${3:-4}
n=$(ls $d/*.png | wc -l); rows=$(( (n + cols - 1) / cols ))
ffmpeg -loglevel error -y -pattern_type glob -i "$d/*.png" -vf "scale=640:-1,drawtext=fontfile=/home/user/mindbaton/assets/fonts/GeistMono-Variable.woff2:text='%{metadata\:lavf.image2dec.source_basename}':x=8:y=8:fontsize=18:fontcolor=yellow:box=1:boxcolor=black@0.6,tile=${cols}x${rows}:padding=4:color=white" -frames:v 1 $out 2>&1 | head -3
