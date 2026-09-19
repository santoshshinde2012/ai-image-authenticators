"""Metadata / EXIF / PNG text chunk forensics."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
from PIL import Image

from ai_image_authenticator.application.analyzers.base import BaseAnalyzer
from ai_image_authenticator.domain.models import AnalyzerOutput

# Generator fingerprints trusted anywhere in the metadata text (word-bounded).
AI_SOFTWARE_PATTERNS = [
    (r"midjourney", "Midjourney"),
    (r"dall[\s.\-·]?e", "DALL·E"),
    (r"stable[\s.\-]?diffusion", "Stable Diffusion"),
    (r"automatic1111|a1111|comfyui", "Stable Diffusion UI"),
    (r"adobe\s*firefly", "Adobe Firefly"),
    (r"leonardo\.?ai", "Leonardo AI"),
    (r"ideogram", "Ideogram"),
    (r"flux\.?1|black forest labs", "FLUX"),
    (r"novelai", "NovelAI"),
    (r"invokeai", "InvokeAI"),
    (r"google\s*(?:gemini|imagen)|imagen\s*[234]", "Google Imagen/Gemini"),
    (r"made with ai|generated (?:with|by) ai|ai[\s\-]generated", "Generic AI label"),
    (r"civitai", "Civitai"),
]

# Ordinary words or company names: only trusted in a software / creator-tool field, so a
# caption like "Shot at Firefly Grove, Gemini Observatory" is not a generator fingerprint.
SOFTWARE_FIELD_PATTERNS = [
    (r"firefly", "Adobe Firefly"),
    (r"chatgpt|openai", "OpenAI / ChatGPT"),
    (r"gemini|imagen", "Google Imagen/Gemini"),
]

_CREATOR_TOOL_RE = re.compile(r"CreatorTool[\"'>=\s]+([^<\"']{2,120})", re.IGNORECASE)

CAMERA_MAKES = {
    "canon", "nikon", "sony", "fujifilm", "fuji", "olympus", "panasonic",
    "leica", "hasselblad", "pentax", "ricoh", "kodak", "gopro", "dji",
    "apple", "samsung", "google", "huawei", "xiaomi", "oneplus",
}


class MetadataForensics(BaseAnalyzer):
    id = "metadata"
    name = "Metadata Forensics"

    def analyze(self, image: Image.Image, rgb: np.ndarray, raw_bytes: bytes, filename: str) -> AnalyzerOutput:
        findings: list[str] = []
        # The loader hands analyzers an RGB copy; report the mode the file was stored in
        details: dict[str, Any] = {"format": image.format, "mode": getattr(image, "source_mode", image.mode)}
        score = 0.35
        confidence = 0.45
        ai_hits: list[str] = []
        has_camera = False
        has_exif = False
        software_tags: list[str] = []

        # EXIF via Pillow
        exif = {}
        exif_text: list[str] = []
        try:
            raw_exif = image.getexif()
            if raw_exif:
                has_exif = True
                for k, v in raw_exif.items():
                    try:
                        exif[str(k)] = str(v)[:500]
                    except Exception:
                        pass
                # Exif sub-IFD carries UserComment / ImageDescription-style free text
                for ifd in (raw_exif, raw_exif.get_ifd(0x8769)):
                    exif_text.extend(v for v in ifd.values() if isinstance(v, str))
                # Common tags
                make = str(raw_exif.get(271, "") or "")
                model = str(raw_exif.get(272, "") or "")
                software = str(raw_exif.get(305, "") or "")
                details["Make"] = make
                details["Model"] = model
                details["Software"] = software
                if make:
                    software_tags.append(make)
                if software:
                    software_tags.append(software)
                if make and any(m in make.lower() for m in CAMERA_MAKES):
                    has_camera = True
                    findings.append(f"Camera EXIF present: {make} {model}".strip())
        except Exception as e:
            details["exif_error"] = str(e)

        # PNG text chunks, JPEG comments and XMP (Pillow exposes them in ``info``). Only
        # metadata is scanned: regexing compressed pixel bytes matches noise by chance.
        metadata_text: list[str] = list(exif_text)
        for key, val in (image.info or {}).items():
            if isinstance(val, (str, bytes)):
                text = val.decode("utf-8", errors="ignore") if isinstance(val, bytes) else val
                if len(text) < 2000:
                    details[f"info_{key}"] = text[:500]
                metadata_text.append(text)
                if key.lower() == "software":
                    software_tags.append(text)
                software_tags.extend(m.strip() for m in _CREATOR_TOOL_RE.findall(text))

        searchable = " ".join(metadata_text + software_tags).lower()
        software_field = " ".join(software_tags).lower()
        for patterns, haystack in ((AI_SOFTWARE_PATTERNS, searchable), (SOFTWARE_FIELD_PATTERNS, software_field)):
            for pattern, label in patterns:
                if re.search(rf"\b(?:{pattern})\b", haystack, re.IGNORECASE) and label not in ai_hits:
                    ai_hits.append(label)

        # C2PA / Content Credentials: handled by ProvenanceC2PA (id=provenance), not here.
        details["path"] = "metadata_forensics"

        if ai_hits:
            score = min(0.98, 0.75 + 0.05 * len(ai_hits))
            confidence = 0.9
            findings.append("AI generator fingerprints: " + ", ".join(ai_hits))
        elif has_camera and has_exif:
            score = 0.12
            confidence = 0.7
            findings.append("Authentic camera EXIF reduces AI likelihood (can still be spoofed)")
        elif has_exif and not has_camera:
            score = 0.4
            confidence = 0.5
            findings.append("EXIF present but no known camera make/model")
        else:
            # Stripped metadata — common for web/social and AI exports
            score = 0.55
            confidence = 0.55
            findings.append("Little/no camera EXIF — common for AI exports and social downloads")
            if (image.format or "").upper() == "PNG":
                findings.append("PNG without rich metadata is consistent with generator/screenshot pipelines")
                score = 0.58

        if image.format and image.format.upper() in {"WEBP", "PNG"} and not has_exif:
            findings.append(f"{image.format} container often strips camera provenance")

        if not findings:
            findings.append("No strong metadata signals")

        return AnalyzerOutput(
            id=self.id,
            name=self.name,
            score=float(np.clip(score, 0, 1)),
            confidence=float(np.clip(confidence, 0, 1)),
            findings=findings,
            details={
                **details,
                "ai_hits": ai_hits,
                "has_exif": has_exif,
                "has_camera": has_camera,
            },
        )
