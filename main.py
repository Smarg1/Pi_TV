#!/usr/bin/env python3

import random
import signal
import subprocess
import sys
from pathlib import Path


VIDEO_DIR = Path("eps")

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".m4v",
    ".ts",
    ".mov",
    ".avi",
    ".webm",
}

MIN_REMAINING_SECONDS = 10

running = True


def handle_signal(signum, frame):
    global running
    running = False


def find_videos() -> list[Path]:
    if not VIDEO_DIR.is_dir():
        print(
            f"Video directory does not exist: {VIDEO_DIR}",
            file=sys.stderr,
        )
        return []

    return sorted(
        path
        for path in VIDEO_DIR.iterdir()
        if path.is_file()
        and path.suffix.lower() in VIDEO_EXTENSIONS
    )


def get_duration(video: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )

        return float(result.stdout.strip())

    except (
        subprocess.CalledProcessError,
        ValueError,
        FileNotFoundError,
    ) as exc:
        print(
            f"Could not determine duration of {video}: {exc}",
            file=sys.stderr,
        )
        return 0.0


def get_random_start(duration: float) -> float:
    if duration <= MIN_REMAINING_SECONDS:
        return 0.0

    return random.uniform(
        0,
        duration - MIN_REMAINING_SECONDS,
    )


def play_video(video: Path, start_time: float = 0.0) -> None:
    print(
        f"Playing: {video.name} "
        f"from {start_time:.1f}s"
    )

    command = [
        "mpv",
        "--fs",
        "--no-border",
        "--no-osd",
        "--osd-level=0",
        "--really-quiet",
        "--hwdec=auto",
        "--video-sync=display-resample",
        "--keep-open=no",
        f"--start={start_time}",
        str(video),
    ]

    try:
        subprocess.run(command, check=False)

    except FileNotFoundError:
        print(
            "mpv is not installed.",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    global running

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    videos = find_videos()

    if not videos:
        print(
            f"No videos found in {VIDEO_DIR}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Found {len(videos)} videos.")

    current_video = random.choice(videos)

    duration = get_duration(current_video)

    if duration <= 0:
        print(
            f"Unable to play {current_video}.",
            file=sys.stderr,
        )
        sys.exit(1)

    random_start = get_random_start(duration)

    play_video(
        current_video,
        random_start,
    )

    while running:

        available_videos = [
            video
            for video in videos
            if video != current_video
        ]

        if not available_videos:
            available_videos = videos

        current_video = random.choice(
            available_videos
        )

        play_video(
            current_video,
            0.0,
        )

    print("TV player stopped.")


if __name__ == "__main__":
    main()