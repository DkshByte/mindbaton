#!/bin/sh
# stitch the four segments, pick the poster, bake it into frame 0, add the score (−14 LUFS), make a 1080p copy
set -e
cd "$(dirname "$0")"
printf "file 'seg0.mp4'\nfile 'seg1.mp4'\nfile 'seg2.mp4'\nfile 'seg3.mp4'\n" > segs.txt
ffmpeg -loglevel error -y -f concat -safe 0 -i segs.txt -c copy video.mp4
ffmpeg -loglevel error -y -ss 109.0 -i video.mp4 -frames:v 1 -q:v 1 ../brag.jpg
ffmpeg -loglevel error -y -i video.mp4 -i ../brag.jpg -i score.wav \
  -filter_complex "[0:v][1:v]overlay=0:0:enable='eq(n,0)'[v];[2:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,apad[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p -tag:v avc1 -c:a aac -b:a 256k -shortest -movflags +faststart ../brag.mp4
ffmpeg -loglevel error -y -i ../brag.mp4 -vf scale=1920:1080:flags=lanczos -c:v libx264 -preset slow -crf 19 -pix_fmt yuv420p -c:a copy -movflags +faststart ../brag-1080p.mp4
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate:format=duration,size -of compact ../brag.mp4
