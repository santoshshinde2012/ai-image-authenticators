"""Image loading adapter (Pillow + numpy).

Normalizes every upload to an 8-bit RGB array before any analyzer sees it, so that
16-bit, transparent, rotated and animated inputs are analyzed as a viewer would show
them instead of being silently clipped, flattened or read sideways.
"""

from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image

from ai_image_authenticator.domain.models import LoadedImage

# Below this, several analyzers measure nothing (empty block grids, NaN correlations)
MIN_SIDE = 32

_ORIENTATION_TRANSPOSE = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}


class ImageTooLarge(ValueError):
    """Decoded pixel count exceeds the configured cap (decompression-bomb guard)."""


class ImageTooSmall(ValueError):
    """Image is too small for the forensic analyzers to measure anything."""


def _to_8bit(im: Image.Image, notes: list[str]) -> Image.Image:
    """Scale high-bit-depth modes to 8-bit; ``convert("RGB")`` would clip them."""
    if im.mode.startswith("I;16") or im.mode == "I":
        arr = np.asarray(im, dtype=np.float64)
        scale = 257.0 if (im.mode.startswith("I;16") or arr.max() > 255) else 1.0
        if scale != 1.0:
            notes.append("16-bit image scaled to 8-bit for analysis")
        return Image.fromarray(np.clip(np.rint(arr / scale), 0, 255).astype(np.uint8), "L")
    if im.mode == "F":
        arr = np.asarray(im, dtype=np.float64)
        return Image.fromarray(np.clip(np.rint(arr), 0, 255).astype(np.uint8), "L")
    return im


def _flatten_alpha(im: Image.Image, notes: list[str]) -> Image.Image:
    """Composite transparency over white instead of exposing hidden RGB values."""
    has_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
    if not has_alpha:
        return im
    rgba = im.convert("RGBA")
    if rgba.getextrema()[3][0] == 255:
        return rgba  # alpha channel present but fully opaque
    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    background.alpha_composite(rgba)
    notes.append("transparent regions composited over white before analysis")
    return background


def load_image_bytes(
    data: bytes,
    filename: str = "upload.png",
    max_pixels: int | None = None,
) -> LoadedImage:
    source = Image.open(BytesIO(data))
    width, height = source.size
    # Check dimensions from the header, before decoding allocates anything
    if max_pixels and width * height > max_pixels:
        raise ImageTooLarge(
            f"Image is {width}x{height} ({width * height / 1e6:.1f} MP); "
            f"the limit is {max_pixels / 1e6:.1f} MP"
        )
    if min(width, height) < MIN_SIDE:
        raise ImageTooSmall(
            f"Image is {width}x{height}; at least {MIN_SIDE}x{MIN_SIDE} px is needed for analysis"
        )

    notes: list[str] = []
    frame_count = int(getattr(source, "n_frames", 1) or 1)
    if frame_count > 1:
        notes.append(f"animated image with {frame_count} frames: only the first frame was analyzed")
    source.load()

    im = _flatten_alpha(_to_8bit(source, notes), notes)
    orientation = source.getexif().get(0x0112, 1)
    transpose = _ORIENTATION_TRANSPOSE.get(orientation)
    if transpose is not None:
        im = im.transpose(transpose)
        notes.append(f"EXIF orientation {orientation} applied before analysis")

    image = im.convert("RGB")
    # Analyzers still read the container: format, EXIF/XMP/text chunks and original mode
    image.format = source.format
    image.info = dict(source.info)
    image.source_mode = source.mode
    rgb = np.asarray(image, dtype=np.uint8)
    h, w = rgb.shape[:2]
    return LoadedImage(
        image=image,
        rgb=rgb,
        raw_bytes=data,
        filename=filename,
        width=w,
        height=h,
        frame_count=frame_count,
        decode_notes=notes,
    )
