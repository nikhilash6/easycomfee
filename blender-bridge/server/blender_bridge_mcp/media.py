"""Montagem de vídeo a partir dos PNGs renderizados (ffmpeg do sistema)."""

import pathlib
import shutil
import subprocess


def encode_mp4(frames_dir, fps, out_path, prefix="frame_"):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH (winget install ffmpeg)")
    out = pathlib.Path(out_path)
    cmd = [ffmpeg, "-y", "-v", "error", "-framerate", str(fps),
           "-i", str(pathlib.Path(frames_dir) / f"{prefix}%05d.png"),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "14",
           # x264 exige lados pares; o render já sai par, isto é só garantia.
           "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", str(out)]
    subprocess.run(cmd, check=True, capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return str(out)
