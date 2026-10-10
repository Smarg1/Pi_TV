
#!/usr/bin/env python3
"""Continuously play random videos from ./eps.

Playback priority: mpv, FFplay, VLC.
The first video starts at a random position; later videos start at 0:00.
"""

import logging
import random
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import FrameType

VIDEO_DIR: Path = Path(__file__).resolve().parent / "eps"
VIDEO_EXTENSIONS: set[str] = {
    ".mp4", ".mkv", ".m4v", ".mov", ".avi", ".webm", ".ts",
}

MIN_REMAINING_SECONDS: int = 10
RETRY_DELAY_SECONDS: int = 3
MAX_FAILURES: int = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    stream=sys.stdout,
)
log: logging.Logger = logging.getLogger("pi-tv")
running: bool = True


def stop(signum: int, frame: FrameType | None) -> None:
    """Request a clean shutdown."""
    global running
    running = False
    log.info("Shutdown requested.")


def find_videos() -> list[Path]:
    """Find supported video files in the eps directory."""
    if not VIDEO_DIR.is_dir():
        raise RuntimeError(f"Video directory not found: {VIDEO_DIR}")

    return sorted(
        p for p in VIDEO_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    )


def duration_of(video: Path) -> float:
    """Get duration using ffprobe, or return zero if unavailable."""
    ffprobe: str | None = shutil.which("ffprobe")
    if not ffprobe:
        log.warning("ffprobe not found; random startup position disabled.")
        return 0.0

    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        return max(0.0, float(result.stdout.strip()))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        log.warning("Could not read duration of %s: %s", video.name, exc)
        return 0.0


def startup_position(video: Path) -> float:
    """Choose a random position, leaving at least ten seconds if possible."""
    duration: float = duration_of(video)
    if duration <= MIN_REMAINING_SECONDS:
        return 0.0
    return random.uniform(0.0, duration - MIN_REMAINING_SECONDS)


def available_players(video: Path, start: float) -> list[tuple[str, list[str]]]:
    """Build commands in playback-priority order using player defaults."""
    players: list[tuple[str, list[str]]] = []

    if exe := shutil.which("mpv"):
        command: list[str] = [exe, "--fullscreen"]
        if start > 0:
            command.append(f"--start={start:.3f}")
        players.append(("mpv", command + [str(video)]))

    if exe := shutil.which("ffplay"):
        players.append((
            "FFplay",
            [
                exe, "-fs", "-autoexit", "-ss", f"{start:.3f}",
                "-i", str(video),
            ],
        ))

    if exe := shutil.which("cvlc") or shutil.which("vlc"):
        command = [exe, "--fullscreen", "--play-and-exit"]
        if start > 0:
            command += ["--start-time", str(int(start))]
        players.append(("VLC", command + [str(video)]))

    return players


def play(video: Path, start: float) -> bool:
    """Try each available player until one completes playback normally."""
    log.info("Playing %s from %.1f seconds", video.name, start)

    for name, command in available_players(video, start):
        if not running:
            return False

        log.info("Starting %s", name)
        try:
            process: subprocess.Popen[bytes] = subprocess.Popen(command)
            while running:
                try:
                    code: int = process.wait(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    continue
            else:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                return False

        except OSError as exc:
            log.error("Could not start %s: %s", name, exc)
            continue

        if code == 0:
            return True

        log.error("%s exited with code %d; trying the next player.", name, code)

    log.error("All available players failed for %s.", video.name)
    return False


def main() -> int:
    global running

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        videos: list[Path] = find_videos()
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1

    if not videos:
        log.error("No supported videos found in %s", VIDEO_DIR)
        return 1

    if not any(shutil.which(p) for p in ("mpv", "ffplay", "cvlc", "vlc")):
        log.error("Install at least one player: mpv, FFplay, or VLC.")
        return 1

    log.info("Found %d videos.", len(videos))

    current: Path = random.choice(videos)
    start: float = startup_position(current)
    failures: int = 0

    while running:
        if play(current, start):
            failures = 0
        elif not running:
            break
        else:
            failures += 1
            if failures >= MAX_FAILURES:
                log.warning("Repeated failures; waiting %d seconds.", RETRY_DELAY_SECONDS)
                for _ in range(RETRY_DELAY_SECONDS * 2):
                    if not running:
                        break
                    time.sleep(0.5)
                failures = 0

        alternatives: list[Path] = [v for v in videos if v != current]
        current = random.choice(alternatives or videos)
        start = 0.0

    log.info("Player stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
