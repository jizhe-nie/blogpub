"""Image handling: normalise, shrink, strip metadata (EXIF, incl. GPS location), and name files."""

from __future__ import annotations

import base64
import io
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image as PILImage
from PIL import ImageOps

from .providers import Image

SUPPORTED = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic", ".heif", ".bmp", ".tif", ".tiff"}


class ImageError(Exception):
    pass


@dataclass
class ProcessedImage:
    name: str          # final file name, e.g. 01-architecture.png
    original: str      # original file name
    path: Path         # where it was written
    size: int
    thumb: Image       # small copy for a vision model


def sanitize_stem(stem: str) -> str:
    ascii_stem = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-").lower()
    return ascii_stem or "image"


def _open(path: Path) -> PILImage.Image:
    suffix = path.suffix.lower()
    if suffix in {".heic", ".heif"}:
        try:
            import pillow_heif  # type: ignore
            pillow_heif.register_heif_opener()
        except ImportError:
            # macOS fallback: convert with the built-in `sips`
            if shutil.which("sips"):
                tmp = Path(tempfile.mkdtemp()) / (path.stem + ".png")
                subprocess.run(["sips", "-s", "format", "png", str(path), "--out", str(tmp)],
                               check=True, capture_output=True)
                return PILImage.open(tmp)
            raise ImageError(f"{path.name}: HEIC needs `pip install blogpub[heic]` (or macOS `sips`)")
    try:
        img = PILImage.open(path)
        img.load()
    except Exception as e:  # corrupt or unsupported
        raise ImageError(f"{path.name}: cannot read image ({e})")
    return img


def _has_alpha(img: PILImage.Image) -> bool:
    return img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)


def collect(paths: List[str]) -> List[Path]:
    """Expand directories, keep supported images only, sorted by name."""
    out: List[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if not p.exists():
            raise ImageError(f"Image path does not exist: {raw}")
        files = sorted(x for x in p.iterdir() if x.is_file()) if p.is_dir() else [p]
        for f in files:
            if f.suffix.lower() in SUPPORTED:
                out.append(f)
            elif not p.is_dir():
                raise ImageError(f"Unsupported image type: {f.name}")
    return out


def process(paths: List[Path], out_dir: Path, cfg: Dict[str, Any]) -> List[ProcessedImage]:
    max_width = int(cfg["images"]["max_width"])
    quality = int(cfg["images"]["quality"])
    send_side = int(cfg["images"]["send_max_side"])
    out_dir.mkdir(parents=True, exist_ok=True)
    result: List[ProcessedImage] = []
    used = set()
    for index, src in enumerate(paths, 1):
        img = ImageOps.exif_transpose(_open(src))  # honour rotation first, then drop all metadata
        if img.width > max_width:
            img = img.resize((max_width, round(img.height * max_width / img.width)), PILImage.LANCZOS)

        keep_png = src.suffix.lower() == ".png" or _has_alpha(img)
        ext = ".png" if keep_png else ".jpg"
        name = f"{index:02d}-{sanitize_stem(src.stem)}{ext}"
        while name in used:
            name = f"{index:02d}-{sanitize_stem(src.stem)}-x{ext}"
        used.add(name)

        dest = out_dir / name
        # Saving a fresh image without passing exif/icc/info drops GPS and every other metadata.
        if keep_png:
            img.convert("RGBA" if _has_alpha(img) else "RGB").save(dest, "PNG", optimize=True)
        else:
            img.convert("RGB").save(dest, "JPEG", quality=quality, optimize=True, progressive=True)

        thumb = img.convert("RGB")
        thumb.thumbnail((send_side, send_side))
        buf = io.BytesIO()
        thumb.save(buf, "JPEG", quality=80)
        result.append(ProcessedImage(
            name=name, original=src.name, path=dest, size=dest.stat().st_size,
            thumb=Image(name=name, media_type="image/jpeg", data_b64=base64.b64encode(buf.getvalue()).decode()),
        ))
    return result
