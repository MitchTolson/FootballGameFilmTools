"""Frame grabs from game clips, for reviewing film without watching every clip.

    python -m filmtools.frames grid  <game_dir> <out_dir> <prefix> <clip#...>   # 3x3 frames across each clip
    python -m filmtools.frames sheet <game_dir> <out_dir> <prefix> <clip#...>   # pre-snap + post-snap pairs, 3 plays per image
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys

import numpy as np


def _bin(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    hits = glob.glob(os.path.expandvars(
        rf"%LOCALAPPDATA%/Microsoft/WinGet/Packages/Gyan.FFmpeg*/ffmpeg-*/bin/{name}.exe"))
    if not hits:
        raise FileNotFoundError(f"{name} not found - install with: winget install Gyan.FFmpeg")
    return hits[0]


FFMPEG, FFPROBE = _bin("ffmpeg"), _bin("ffprobe")


def clip_path(game_dir: str, n: int) -> str:
    return os.path.join(game_dir, f"Wide - Clip {int(n):03d}.mp4")


def duration(clip: str) -> float:
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", clip],
                         capture_output=True, text=True).stdout
    return float(out or 0)


def frame(clip: str, t: float, path: str, width: int = 960) -> None:
    subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{max(0.0, t):.2f}", "-i", clip, "-frames:v", "1",
                    "-vf", f"scale={width}:-2", path], check=True)


def motion(clip: str, fps: int = 10) -> np.ndarray:
    w, h = 160, 90
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", clip, "-vf", f"fps={fps},scale={w}:{h},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    f = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)[:, int(h * 0.25):, :]
    return np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))


def find_snap(clip: str, fps: int = 10) -> float:
    """Estimate the snap: end of the longest quiet stretch (players set, camera still)."""
    d = motion(clip, fps)
    if len(d) < 15:
        return 0.3
    sm = np.convolve(d, np.ones(3) / 3, mode="same")
    lo, hi = np.percentile(sm, 15), np.percentile(sm, 95)
    thr = lo + max(1.0, 0.12 * (hi - lo))
    best, start = (0, 0), None
    for i, q in enumerate(list(sm <= thr) + [False]):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if i - start >= best[1] - best[0]:
                best = (start, i)
            start = None
    return best[1] / fps if best[1] - best[0] >= 8 else 0.3


def grid(game_dir: str, out_dir: str, prefix: str, nums: list[int]) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    outs = []
    for n in nums:
        clip = clip_path(game_dir, n)
        dur = duration(clip)
        step = min(dur - 0.2, 10.5) / 8
        dst = os.path.join(out_dir, f"{prefix}_{int(n):03d}.png")
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", clip, "-vf",
                        f"fps=1/{step:.3f},scale=640:-1,tile=3x3", "-frames:v", "1", dst], check=True)
        outs.append(dst)
    return outs


def sheet(game_dir: str, out_dir: str, prefix: str, nums: list[int], per_image: int = 3,
          offsets=(-0.5, 1.5)) -> list[str]:
    """Labelled rows of [pre-snap | post-snap] frames, `per_image` plays per output image."""
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(out_dir, exist_ok=True)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    tiles = []
    for n in nums:
        clip = clip_path(game_dir, n)
        t0 = find_snap(clip)
        ims = []
        for k, off in enumerate(offsets):
            p = os.path.join(out_dir, f"_tmp{k}.png")
            frame(clip, t0 + off, p, 800)
            ims.append(Image.open(p).convert("RGB"))
        w, h = ims[0].size
        t = Image.new("RGB", (w * len(ims), h), "black")
        for k, im in enumerate(ims):
            t.paste(im, (k * w, 0))
        ImageDraw.Draw(t).rectangle((0, 0, 170, 40), fill="black")
        ImageDraw.Draw(t).text((8, 4), f"{prefix}-{n}", fill="yellow", font=font)
        tiles.append(t)
    outs = []
    for i in range(0, len(tiles), per_image):
        chunk = tiles[i:i + per_image]
        W, H = chunk[0].size
        img = Image.new("RGB", (W, H * len(chunk)), "black")
        for j, t in enumerate(chunk):
            img.paste(t, (0, j * H))
        dst = os.path.join(out_dir, f"{prefix}_sheet{i // per_image:02d}.png")
        img.save(dst)
        outs.append(dst)
    for k in range(len(offsets)):
        tmp = os.path.join(out_dir, f"_tmp{k}.png")
        if os.path.exists(tmp):
            os.remove(tmp)
    return outs


if __name__ == "__main__":
    cmd, game_dir, out_dir, prefix, *nums = sys.argv[1:]
    fn = {"grid": grid, "sheet": sheet}[cmd]
    for o in fn(game_dir, out_dir, prefix, [int(n) for n in nums]):
        print(o)
