#!/usr/bin/env python3

from __future__ import annotations

import logging
import os
import platform
import random
import shutil
import signal
import subprocess
import sys
import time

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
VIDEO_DIR = BASE_DIR / "eps"

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".m4v",
    ".mov",
    ".avi",
    ".webm",
    ".ts",
}

MIN_REMAINING_SECONDS = 10.0
PROBE_TIMEOUT_SECONDS = 15
RETRY_DELAY_SECONDS = 3
MAX_CONSECUTIVE_FAILURES = 5

IS_WINDOWS = platform.system() == "Windows"
running = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("pi-tv")


def handle_signal(signum: int, frame: object) -> None:
    global running
    running = False
    log.info("Shutdown requested.")


def find_videos() -> list[Path]:
    if not VIDEO_DIR.is_dir():
        raise RuntimeError(
            f"Video directory does not exist: {VIDEO_DIR}"
        )

    return sorted(
        path
        for path in VIDEO_DIR.iterdir()
        if path.is_file()
        and path.suffix.lower() in VIDEO_EXTENSIONS
    )


def get_duration(video: Path) -> float:
    ffprobe = shutil.which("ffprobe")

    if not ffprobe:
        log.warning("ffprobe unavailable; starting at 0:00.")
        return 0.0

    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=True,
        )

        duration = float(result.stdout.strip())

        if duration > 0:
            return duration

    except (
        subprocess.SubprocessError,
        ValueError,
        OSError,
    ) as exc:
        log.warning("Could not probe %s: %s", video.name, exc)

    return 0.0


def get_random_start(duration: float) -> float:
    if duration <= MIN_REMAINING_SECONDS:
        return 0.0

    return random.uniform(
        0.0,
        duration - MIN_REMAINING_SECONDS,
    )


def video_output_args(engine: str) -> list[str]:
    """Select video output appropriate to the current platform."""
    if engine != "mpv":
        return []

    if IS_WINDOWS:
        return ["--vo=direct3d"]

    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"):
        return ["--vo=auto"]

    return ["--vo=drm", "--gpu-context=drm"]


def player_commands(
    video: Path,
    start_time: float,
) -> list[tuple[str, list[str]]]:
    """Return available players in fallback order."""
    commands: list[tuple[str, list[str]]] = []

    mpv = shutil.which("mpv")
    ffplay = shutil.which("ffplay")
    vlc = shutil.which("cvlc") or shutil.which("vlc")

    if mpv:
        commands.append((
            "mpv",
            [
                mpv,
                "--no-config",
                *video_output_args("mpv"),
                "--hwdec=auto",
                "--fullscreen",
                "--no-border",
                "--keep-open=no",
                f"--start={start_time:.3f}",
                str(video),
            ],
        ))

    if ffplay:
        commands.append((
            "FFmpeg/ffplay",
            [
                ffplay,
                "-hide_banner",
                "-loglevel", "warning",
                "-nostats",
                "-fs",
                "-autoexit",
                "-hwaccel", "auto",
                "-ss", f"{start_time:.3f}",
                "-i", str(video),
            ],
        ))

    if vlc:
        commands.append((
            "VLC",
            [
                vlc,
                "--fullscreen",
                "--no-video-title-show",
                "--play-and-exit",
                "--start-time", str(int(start_time)),
                str(video),
            ],
        ))

    return commands


def run_player(command: list[str]) -> int | None:
    """Run a player until it exits or the app is stopped."""
    try:
        process = subprocess.Popen(command)

    except OSError as exc:
        log.error("Could not start %s: %s", command[0], exc)
        return 127

    while running:
        try:
            return process.wait(timeout=0.5)

        except subprocess.TimeoutExpired:
            continue

    process.terminate()

    try:
        process.wait(timeout=3)

    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()

    return None


def play_video(video: Path, start_time: float) -> bool:
    """Try mpv, ffplay, then VLC."""
    log.info(
        "Playing %s from %.1f seconds",
        video.name,
        start_time,
    )

    commands = player_commands(video, start_time)

    if not commands:
        log.error(
            "No supported player found. Install mpv, FFmpeg, or VLC."
        )
        return False

    for engine, command in commands:
        if not running:
            return False

        log.info("Starting %s", engine)
        result = run_player(command)

        if result is None:
            return False

        if result == 0:
            log.info("%s exited normally.", engine)
            return True

        log.error(
            "%s exited with code %d; trying the next player.",
            engine,
            result,
        )

    log.error("All available players failed for %s.", video.name)
    return False


def main() -> int:
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        videos = find_videos()
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1

    if not videos:
        log.error("No videos found in %s", VIDEO_DIR)
        return 1

    log.info("Found %d videos.", len(videos))
    log.info("Platform: %s", platform.system())

    available = [
        name
        for name, executable in (
            ("mpv", "mpv"),
            ("FFmpeg/ffplay", "ffplay"),
        )
        if shutil.which(executable)
    ]

    if shutil.which("cvlc") or shutil.which("vlc"):
        available.append("VLC")

    if not available:
        log.error("No supported video player is installed.")
        return 1

    log.info("Available players: %s", ", ".join(available))

    current_video = random.choice(videos)
    duration = get_duration(current_video)
    start_time = get_random_start(duration)

    consecutive_failures = 0

    while running:
        succeeded = play_video(current_video, start_time)

        if not running:
            break

        if succeeded:
            consecutive_failures = 0
        else:
            consecutive_failures += 1

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                log.error(
                    "Repeated playback failures; retrying after a delay."
                )
                for _ in range(RETRY_DELAY_SECONDS * 2):
                    if not running:
                        break
                    time.sleep(0.5)
                consecutive_failures = 0

        alternatives = [
            video for video in videos
            if video != current_video
        ]
        current_video = random.choice(alternatives or videos)

        start_time = 0.0

    log.info("TV player stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())