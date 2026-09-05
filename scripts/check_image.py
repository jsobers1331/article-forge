"""Deterministic quality gate for article image assets.

This checks what a script can prove: file format, dimensions, readable pixels,
descriptive alt text, and duplicate reuse. It deliberately does not pretend to
judge photographic taste, anatomy, or whether a scene makes a truthful claim;
those remain the visual QC steps in IMAGES.md.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from PIL import Image

MIN_WIDTH = 1200
MIN_HEIGHT = 800
VALID_FORMATS = {"WEBP", "AVIF"}
VALID_SUFFIXES = {".webp", ".avif"}
GENERIC_ALT = re.compile(
    r"^(?:image|photo|picture|hero|banner|asset|generated)(?:[-_ ]?\d+)?$", re.I
)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _average_hash(image):
    sample = image.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
    pixels = list(sample.tobytes())
    average = sum(pixels) / len(pixels)
    return tuple(pixel >= average for pixel in pixels)


def _hash_distance(left, right):
    return sum(a != b for a, b in zip(left, right))


def _candidate_files(paths, current):
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            candidates = path.rglob("*")
        else:
            candidates = [path]
        for candidate in candidates:
            if (
                candidate == current
                or candidate.is_symlink()
                or not candidate.is_file()
            ):
                continue
            if candidate.suffix.lower() in VALID_SUFFIXES:
                yield candidate


def check_image_asset(path, alt, against=None):
    """Return ``(status, detail, receipt)`` for one image.

    A perceptual-hash distance of five or less is treated as duplicate reuse.
    This is intentionally conservative for article hero assets: house style
    should be shared through palette and light, not by repeating a composition.
    """
    path = Path(path)
    against = against or []
    errors = []
    receipt = {"path": str(path), "alt": alt, "against": [str(p) for p in against]}

    if path.is_symlink():
        errors.append("output path must not be a symlink")
    if not path.is_file():
        errors.append("image file does not exist")
    if path.suffix.lower() not in VALID_SUFFIXES:
        errors.append("article images must use .webp or .avif")
    if not isinstance(alt, str) or not alt.strip():
        errors.append("descriptive alt text is required")
    elif len(alt.strip()) < 15:
        errors.append("alt text is too short to describe the scene")
    elif len(alt.strip()) > 160:
        errors.append("alt text must be 160 characters or fewer")
    elif GENERIC_ALT.fullmatch(alt.strip()):
        errors.append(
            "alt text must describe the visible scene, not a generic asset label"
        )

    if errors:
        return "FAIL", "; ".join(errors), receipt

    try:
        with Image.open(path) as image:
            image.load()
            image_format = image.format
            width, height = image.size
            image_hash = _average_hash(image)
    except Exception as exc:  # Pillow raises several format-specific errors.
        return "FAIL", f"image cannot be decoded: {exc}", receipt

    receipt.update(
        {
            "sha256": _sha256(path),
            "format": image_format,
            "width": width,
            "height": height,
            "bytes": path.stat().st_size,
        }
    )
    if image_format not in VALID_FORMATS:
        errors.append(f"decoded format {image_format!r} is not WebP or AVIF")
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        errors.append(f"image is {width}x{height}; minimum is {MIN_WIDTH}x{MIN_HEIGHT}")

    duplicate = None
    for candidate in _candidate_files(against, path):
        try:
            with Image.open(candidate) as prior:
                prior.load()
                distance = _hash_distance(image_hash, _average_hash(prior))
        except Exception:
            continue
        if _sha256(candidate) == receipt["sha256"] or distance <= 5:
            duplicate = {"path": str(candidate), "hash_distance": distance}
            break
    if duplicate:
        receipt["duplicate"] = duplicate
        errors.append(
            f"likely duplicate of {duplicate['path']} (perceptual hash distance {duplicate['hash_distance']})"
        )

    if errors:
        return "FAIL", "; ".join(errors), receipt
    return (
        "PASS",
        f"{width}x{height} {image_format} asset passed image and duplicate checks",
        receipt,
    )


def main():
    parser = argparse.ArgumentParser(description="Validate one article image asset")
    parser.add_argument("--image", required=True, help="Path to a .webp or .avif asset")
    parser.add_argument(
        "--alt", required=True, help="Descriptive alt text for the visible scene"
    )
    parser.add_argument(
        "--against",
        action="append",
        default=[],
        help="Prior image file or directory to scan for duplicate reuse; repeatable",
    )
    parser.add_argument("--receipt", help="Optional JSON receipt path")
    args = parser.parse_args()

    status, detail, receipt = check_image_asset(args.image, args.alt, args.against)
    marker = "✓" if status == "PASS" else "✗"
    print(f"{marker} [{status}] {detail}")
    if args.receipt:
        Path(args.receipt).write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Wrote receipt to {args.receipt}")
    if status != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
