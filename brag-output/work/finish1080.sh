#!/bin/sh
# the 1080p cut, straight from its own render (p0–p3): poster as frame 0, the score at −14 LUFS
set -e
cd "$(dirname "$0")"
printf "file 'p0.mp4'\nfile 'p1.mp4'\nfile 'p2.mp4'\nfile 'p3.mp4'\n" > psegs.txt
ffmpeg -loglevel error -y -f concat -safe 0 -i psegs.txt -c copy video1080.mp4
ffmpeg -loglevel error -y -ss 109.0 -i video1080.mp4 -frames:v 1 -q:v 1 poster1080.jpg
ffmpeg -loglevel error -y -i video1080.mp4 -i poster1080.jpg -i score.wav \
  -filter_complex "[0:v][1:v]overlay=0:0:enable='eq(n,0)'[v];[2:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -c:a aac -b:a 256k -shortest -movflags +faststart ../brag-1080p.mp4
ffprobe -v error -show_entries stream=codec_name,width,height:format=duration,size -of compact ../brag-1080p.mp4
