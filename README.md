# Pi TV

A lightweight, headless TV-style video player for Raspberry Pi.

The Raspberry Pi outputs video directly through HDMI using
mpv and DRM/KMS. No desktop environment is required.

## Video directory

Videos are stored in:

    /eps

Supported extensions:

- .mp4
- .mkv
- .m4v
- .ts
- .mov
- .avi
- .webm

## Behaviour

When the player starts:

1. It scans `/eps`.
2. A random video is selected.
3. A random position inside that video is selected.
4. mpv starts the video from that position.
5. The video plays until its end.
6. Another random video is selected.
7. Another random starting position is selected.
8. The process repeats.

The same video is avoided twice in a row when multiple videos
are available.

## Requirements

Install mpv and ffprobe:

    sudo apt update
    sudo apt install mpv ffmpeg

The Raspberry Pi should be running Raspberry Pi OS Lite.

No desktop environment is required.

## Running manually

    python3 main.py

## HDMI output

mpv uses the DRM/KMS display backend:

    --vo=gpu
    --gpu-context=drm

The video is displayed fullscreen without a desktop, window
border, player controls, OSD, or title bar.