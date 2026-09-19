"""Content Credentials / C2PA provenance detector (presence + assertion hints).

Industry alignment
------------------
Platforms such as X primarily label "Made with AI" from C2PA / Content Credentials
at upload (e.g. IPTC digitalSourceType trainedAlgorithmicMedia). They generally do
NOT verify provider SynthID watermarks.

Nuance (document, do not overclaim): independent tests (e.g. Roboin 2026) suggest
X may also apply undisclosed criteria beyond C2PA-only. Bakshi-style investigations
still find C2PA caBX + digitalSourceType as the inspectable upload-time signal.

This analyzer reports:
  - whether C2PA/JUMBF/caBX markers appear to be present in the file bytes
  - richer soft extraction of digitalSourceType, actions, claim generators, softBinding
  - explicit absence when stripped (common after social re-encode / screenshot)

Honesty limits (documented in findings + fusion limitations):
  - v1 is marker / string detection, NOT full cryptographic trust-chain validation
  - optional c2pa-python Reader is used when installed for richer JSON inspection
  - absence of C2PA is NOT proof of authenticity
  - we do not claim to be a platform upload pipeline or a SynthID decoder
  - industry 2026 dual-layer (C2PA + SynthID) is complementary; we only inspect C2PA
"""

from __future__ import annotations

import re
import struct
from typing import Any

import numpy as np
from PIL import Image

from ai_image_authenticator.application.analyzers.base import BaseAnalyzer
from ai_image_authenticator.domain.models import AnalyzerOutput

# digitalSourceType taxonomy from the C2PA Conformance Task Force signals rubric
# (asset-rubric-signals-local.yml, rubric v1.0, 2026-08-06). IPTC values such as
# algorithmicallyEnhanced (denoise/sharpen) or dataDrivenMedia (charts) are NOT generative.
GENAI_SOURCE_TYPES = (
    "trainedAlgorithmicMedia",
    "compositeWithTrainedAlgorithmicMedia",
    "compositeSynthetic",
    "trainedAlgorithmicData",  # URL form http://c2pa.org/digitalsourcetype/… since spec 2.2
)
POSSIBLY_GENAI_SOURCE_TYPES = ("digitalArt", "composite")
# Back-compat alias for callers that imported the old name
AI_SOURCE_TYPE_SUFFIXES = GENAI_SOURCE_TYPES

_KNOWN_TYPES = sorted(GENAI_SOURCE_TYPES + POSSIBLY_GENAI_SOURCE_TYPES, key=len, reverse=True)
SOURCE_TYPE_RE = re.compile(
    r"digitalsourcetype[/:#](?P<label>" + "|".join(re.escape(t) for t in _KNOWN_TYPES) + r")(?![A-Za-z])",
    re.IGNORECASE,
)
AI_SOURCE_TYPE_RE = SOURCE_TYPE_RE
# Any declared value (digitalCapture, algorithmicallyEnhanced, …), reported for transparency
DECLARED_SOURCE_TYPE_RE = re.compile(r"digitalsourcetype[/:#](?P<label>[A-Za-z]{3,60})", re.IGNORECASE)

CLAIM_HINT_RE = re.compile(
    r"(c2pa\.actions|c2pa\.created|claim\.generator|contentcredentials|"
    r"content.?credentials|softWareAgent|softwareAgent|c2pa\.ai-disclosure|"
    r"c2pa\.watermarked|softBinding|c2pa\.assertion)",
    re.IGNORECASE,
)

ACTION_LABEL_RE = re.compile(
    r"c2pa\.(?:created|converted|edited|watermarked(?:\.\w+)?|opened|placed|"
    r"removed|resized|published|transcoded|unknown)",
    re.IGNORECASE,
)

GENERATOR_RE = re.compile(
    r"(?:claim\.generator(?:\.info)?|softwareAgent|claim_generator)"
    r"[\"'\s:=]+([A-Za-z0-9 ._\-/]{3,80})",
    re.IGNORECASE,
)

SOFT_BINDING_RE = re.compile(
    r"(softBinding|soft-binding|c2pa\.watermarked|watermarked\.unbound)",
    re.IGNORECASE,
)


def _png_cabx_chunks(raw: bytes) -> list[bytes]:
    """PNG Content Credentials live in caBX chunks (after IHDR)."""
    if len(raw) < 8 or raw[:8] != b"\x89PNG\r\n\x1a\n":
        return []
    chunks: list[bytes] = []
    pos = 8
    while pos + 8 <= len(raw):
        length = struct.unpack(">I", raw[pos : pos + 4])[0]
        ctype = raw[pos + 4 : pos + 8]
        if length > 50_000_000:
            break
        if ctype == b"caBX":
            chunks.append(raw[pos + 8 : pos + 8 + length])
        if ctype == b"IEND":
            break
        pos += 12 + length  # len + type + data + crc
    return chunks


def _find_png_cabx(raw: bytes) -> tuple[bool, int]:
    """Returns (hit, total caBX payload size)."""
    chunks = _png_cabx_chunks(raw)
    return bool(chunks), sum(len(c) for c in chunks)


def _jpeg_app11_payloads(raw: bytes) -> list[bytes]:
    """JPEG C2PA manifests are carried in APP11 segments hosting JUMBF boxes."""
    if len(raw) < 4 or raw[:2] != b"\xff\xd8":
        return []
    payloads: list[bytes] = []
    pos = 2
    while pos + 4 <= len(raw):
        if raw[pos] != 0xFF:
            pos += 1
            continue
        marker = raw[pos + 1]
        if marker in (0xD9, 0xDA):  # EOI / SOS — image data follows
            break
        if 0xD0 <= marker <= 0xD7 or marker in {0x01, 0xD8}:
            pos += 2
            continue
        seg_len = struct.unpack(">H", raw[pos + 2 : pos + 4])[0]
        if seg_len < 2:
            break
        payload = raw[pos + 4 : pos + 2 + seg_len]
        low = payload.lower()
        if marker == 0xEB and (b"jumb" in low or b"c2pa" in low or b"jumd" in low):
            payloads.append(payload)
        pos += 2 + seg_len
    return payloads


def _find_jpeg_jumbf(raw: bytes) -> tuple[bool, int]:
    """Returns (hit, APP11/JUMBF segment count)."""
    payloads = _jpeg_app11_payloads(raw)
    return bool(payloads), len(payloads)


def _webp_c2pa_chunks(raw: bytes) -> list[bytes]:
    """WebP carries C2PA in a RIFF chunk with FourCC ``C2PA``."""
    if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WEBP":
        return []
    chunks: list[bytes] = []
    pos = 12
    while pos + 8 <= len(raw):
        fourcc = raw[pos : pos + 4]
        size = struct.unpack("<I", raw[pos + 4 : pos + 8])[0]
        if fourcc == b"C2PA":
            chunks.append(raw[pos + 8 : pos + 8 + size])
        pos += 8 + size + (size & 1)  # chunks are padded to even sizes
    return chunks


def _find_webp_c2pa(raw: bytes) -> bool:
    return bool(_webp_c2pa_chunks(raw))


def manifest_container_bytes(raw: bytes) -> bytes:
    """Bytes inside C2PA manifest containers only — never the rest of the file.

    A digitalSourceType string appended after IEND, or sitting in a text chunk, is not a
    manifest claim, so only these bytes can set the provenance floor.
    """
    return b"".join(_png_cabx_chunks(raw) + _jpeg_app11_payloads(raw) + _webp_c2pa_chunks(raw))


def _raw_marker_scan(raw: bytes) -> dict[str, bool]:
    low = raw[: min(len(raw), 2_000_000)].lower()
    return {
        "has_c2pa_ascii": b"c2pa" in low,
        "has_jumbf_ascii": b"jumb" in low or b"jumd" in low,
        "has_claim_signature": b"claim.signature" in low or b"c2pa.signature" in low,
        "has_content_credentials": b"contentcredentials" in low or b"content credentials" in low,
        "has_ai_disclosure_assertion": b"c2pa.ai-disclosure" in low or b"ai-disclosure" in low,
        "has_soft_binding_hint": bool(SOFT_BINDING_RE.search(low.decode("latin-1", errors="ignore"))),
    }


def _extract_source_types(data: bytes) -> tuple[list[str], list[str]]:
    """Return (generative types, possibly-generative types) named in ``data``."""
    # latin-1 keeps binary searchable as text without decode errors
    text = data[: min(len(data), 2_000_000)].decode("latin-1", errors="ignore")
    genai: list[str] = []
    possibly: list[str] = []
    for match in SOURCE_TYPE_RE.finditer(text):
        label = next(t for t in _KNOWN_TYPES if t.lower() == match.group("label").lower())
        bucket = genai if label in GENAI_SOURCE_TYPES else possibly
        if label not in bucket:
            bucket.append(label)
    return genai, possibly


def _extract_ai_source_types(raw: bytes) -> list[str]:
    return _extract_source_types(raw)[0]


def _declared_source_types(data: bytes) -> list[str]:
    text = data[: min(len(data), 2_000_000)].decode("latin-1", errors="ignore")
    seen: list[str] = []
    for match in DECLARED_SOURCE_TYPE_RE.finditer(text):
        if match.group("label") not in seen:
            seen.append(match.group("label"))
    return seen[:12]


def _extract_action_labels(raw: bytes) -> list[str]:
    text = raw[: min(len(raw), 2_000_000)].decode("latin-1", errors="ignore")
    hits: list[str] = []
    for match in ACTION_LABEL_RE.finditer(text):
        lab = match.group(0).lower()
        if lab not in hits:
            hits.append(lab)
    return hits[:24]


def _extract_generators(raw: bytes) -> list[str]:
    text = raw[: min(len(raw), 2_000_000)].decode("latin-1", errors="ignore")
    hits: list[str] = []
    for match in GENERATOR_RE.finditer(text):
        name = match.group(1).strip(" \t\"':,{}[]")
        if len(name) < 3:
            continue
        # Drop obvious JSON junk
        if name.lower() in {"data", "actions", "when", "label", "name"}:
            continue
        if name not in hits:
            hits.append(name[:80])
    return hits[:8]


def _mime_for(raw: bytes) -> str | None:
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[4:8] == b"ftyp" and raw[8:12] in (b"avif", b"avis"):
        return "image/avif"
    return None


def _reader_context() -> Any:
    """Offline reader settings: never follow a remote manifest URL embedded in an upload."""
    try:
        from c2pa import Context, Settings  # type: ignore[import-not-found]

        return Context(Settings.from_dict({"verify": {"remote_manifest_fetch": False}}))
    except Exception:
        return None


def _validation_failures(results: Any) -> list[str]:
    """Collect failure codes from ``Reader.get_validation_results()``."""
    codes: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "failure" and isinstance(value, list):
                    codes.extend(str(item.get("code")) for item in value if isinstance(item, dict))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(results)
    return list(dict.fromkeys(c for c in codes if c and c != "None"))[:12]


def c2pa_reader_available() -> bool:
    try:
        from c2pa import Reader  # type: ignore[import-not-found]  # noqa: F401
    except Exception:
        return False
    return True


def _try_c2pa_reader(raw: bytes, filename: str) -> dict[str, Any] | None:
    """Optional parse + validation via contentauth c2pa-python when installed."""
    try:
        from c2pa import Reader  # type: ignore[import-not-found]
    except Exception:
        return None

    import io
    import json

    result: dict[str, Any] = {"library": "c2pa", "parsed": False, "remote_manifest_fetch": False}
    mime = _mime_for(raw)
    if mime is None:
        result["error"] = "unsupported container for c2pa reader"
        return result
    try:
        reader = Reader.try_create(mime, io.BytesIO(raw), context=_reader_context())
    except Exception as exc:
        result["manifest_found"] = False
        result["error"] = str(exc)[:200]
        return result
    if reader is None:
        result["manifest_found"] = False
        return result

    result["parsed"] = True
    result["manifest_found"] = True
    try:
        result["validation_state"] = reader.get_validation_state()
        result["validation_failures"] = _validation_failures(reader.get_validation_results())
    except Exception as exc:
        result["validation_error"] = str(exc)[:200]
    try:
        payload = json.loads(reader.json())
        result["manifest_keys"] = list(payload.get("manifests", {}).keys())[:8]
        if payload.get("active_manifest"):
            result["active_manifest"] = str(payload["active_manifest"])[:120]
        blob = json.dumps(payload)
        genai, possibly = _extract_source_types(blob.encode("utf-8", errors="ignore"))
        labels: list[str] = []
        for m in re.finditer(r'"label"\s*:\s*"([^"]+)"', blob):
            lab = m.group(1)
            if (lab.startswith("c2pa.") or "ai-disclosure" in lab) and lab not in labels:
                labels.append(lab)
        actions = list(dict.fromkeys(m.group(0).lower() for m in ACTION_LABEL_RE.finditer(blob)))
        generators = [
            str(info["name"])[:80]
            for manifest in payload.get("manifests", {}).values()
            for info in (manifest.get("claim_generator_info") or [])
            if isinstance(info, dict) and info.get("name")
        ]
        result["ai_source_types"] = genai
        result["possibly_ai_source_types"] = possibly
        result["declared_source_types"] = _declared_source_types(blob.encode("utf-8", errors="ignore"))
        result["assertion_labels"] = labels[:24]
        result["action_labels"] = actions[:24]
        result["claim_generators"] = list(dict.fromkeys(generators))[:8]
        result["soft_binding_hint"] = bool(SOFT_BINDING_RE.search(blob))
    except Exception as exc:
        result["json_error"] = str(exc)[:200]
    return result


class ProvenanceC2PA(BaseAnalyzer):
    """Detect C2PA / Content Credentials manifests and their digitalSourceType claims."""

    id = "provenance"
    name = "Content Credentials (C2PA)"

    def __init__(self, use_c2pa_reader: bool | None = None) -> None:
        # None: validate with the optional c2pa-python reader whenever it is installed
        self._use_reader = use_c2pa_reader

    def analyze(self, image: Image.Image, rgb: np.ndarray, raw_bytes: bytes, filename: str) -> AnalyzerOutput:
        findings: list[str] = []
        details: dict[str, Any] = {
            "format": image.format,
            "path": "provenance_contract",
            "crypto_validated": False,
            "trusted": False,
            "limits": (
                "Only digitalSourceType claims inside a C2PA manifest container (PNG caBX, JPEG "
                "APP11/JUMBF, WebP C2PA chunk) count. With the optional c2pa-python reader the "
                "signature and hard binding are validated and remote manifest fetch is disabled; "
                "no trust list is configured, so 'Valid' is not 'Trusted'. Without the reader, "
                "claims are unverified. Not a SynthID decoder; not a platform upload pipeline."
            ),
        }

        png_cabx, cabx_bytes = _find_png_cabx(raw_bytes)
        jpeg_jumbf, jumbf_segs = _find_jpeg_jumbf(raw_bytes)
        webp_hit = _find_webp_c2pa(raw_bytes)
        container = manifest_container_bytes(raw_bytes)
        container_hit = bool(container)
        container_text = container.decode("latin-1", errors="ignore")

        markers = _raw_marker_scan(container) if container_hit else {}
        ai_types, possibly_types = _extract_source_types(container)
        all_genai, all_possibly = _extract_source_types(raw_bytes)
        unbound = [t for t in all_genai + all_possibly if t not in ai_types + possibly_types]
        declared = _declared_source_types(container)
        action_labels = _extract_action_labels(container)
        generators = _extract_generators(container)
        claim_hint = bool(CLAIM_HINT_RE.search(container_text))
        soft_binding = bool(markers.get("has_soft_binding_hint"))

        use_reader = True if self._use_reader is None else self._use_reader
        optional = _try_c2pa_reader(raw_bytes, filename) if use_reader else None
        # None: not checked. True: signature + hard binding valid. False: rejected / invalid.
        reader_valid: bool | None = None
        if optional:
            details["c2pa_library"] = optional
            if optional.get("manifest_found"):
                for src, dst in (
                    (optional.get("ai_source_types"), ai_types),
                    (optional.get("possibly_ai_source_types"), possibly_types),
                    (optional.get("declared_source_types"), declared),
                    (optional.get("action_labels"), action_labels),
                    (optional.get("claim_generators"), generators),
                ):
                    dst.extend(v for v in (src or []) if v not in dst)
                soft_binding = soft_binding or bool(optional.get("soft_binding_hint"))
                state = optional.get("validation_state")
                details["validation_state"] = state
                details["validation_failures"] = optional.get("validation_failures") or []
                reader_valid = state in ("Valid", "Trusted")
                details["crypto_validated"] = reader_valid
                details["trusted"] = state == "Trusted"
            elif container_hit:
                # The reference library found no parseable manifest in a claimed container
                reader_valid = False
                details["reader_rejected_container"] = True

        manifest_present = container_hit or bool(optional and optional.get("manifest_found"))
        unverified_types: list[str] = []
        if reader_valid is False and ai_types:
            unverified_types, ai_types = ai_types, []

        details.update(
            {
                "png_cabx_chunk": png_cabx,
                "png_cabx_bytes": cabx_bytes,
                "jpeg_jumbf_app11": jpeg_jumbf,
                "jpeg_jumbf_segments": jumbf_segs,
                "webp_c2pa_chunk": webp_hit,
                "raw_markers": markers,
                "manifest_present": manifest_present,
                "ai_digital_source_types": ai_types,
                "possibly_ai_source_types": possibly_types,
                "unverified_source_types": unverified_types,
                "unbound_source_type_strings": unbound,
                "declared_source_types": declared,
                "action_labels": action_labels[:24],
                "claim_generators": generators[:8],
                "claim_hint": claim_hint,
                "soft_binding_hint": soft_binding,
                "assertion_richness": len(ai_types) + len(action_labels) + len(generators),
            }
        )

        if ai_types:
            richness = len(ai_types) + min(3, len(action_labels)) + min(2, len(generators))
            score = min(0.98, 0.88 + 0.015 * richness)
            confidence = 0.92 if container_hit or (optional and optional.get("parsed")) else 0.8
            if details["crypto_validated"]:
                confidence = min(0.95, confidence + 0.03)
            findings.append(
                "C2PA manifest declares generative digitalSourceType: " + ", ".join(ai_types)
            )
            if generators:
                findings.append("Claim generator / softwareAgent: " + ", ".join(generators[:4]))
            if action_labels:
                findings.append("C2PA action/assertion labels: " + ", ".join(action_labels[:6]))
            if details["crypto_validated"]:
                findings.append(
                    "Manifest signature and hard binding validated (c2pa-python: "
                    f"{details['validation_state']}); signer trust "
                    + ("confirmed" if details["trusted"] else "not evaluated — no trust list configured")
                )
            else:
                findings.append(
                    "Manifest not cryptographically validated (install the c2pa extra to check "
                    "signature and hard binding)"
                )
            if soft_binding:
                findings.append(
                    "Soft-binding / watermarked assertion present (records that a watermark "
                    "may exist); this tool does not decode SynthID"
                )
        elif manifest_present:
            score = 0.42
            confidence = 0.72 if container_hit else 0.58
            where = []
            if png_cabx:
                where.append(f"PNG caBX ({cabx_bytes}B)")
            if jpeg_jumbf:
                where.append(f"JPEG APP11/JUMBF ×{jumbf_segs}")
            if webp_hit:
                where.append("WebP C2PA chunk")
            if markers.get("has_ai_disclosure_assertion"):
                where.append("ai-disclosure assertion")
            findings.append(
                "C2PA manifest present (" + ", ".join(where or ["c2pa reader"]) + ")"
                + (f"; declared digitalSourceType: {', '.join(declared)}" if declared else "")
            )
            if unverified_types:
                score = 0.5
                failures = details.get("validation_failures") or []
                findings.append(
                    "Manifest names a generative source type ("
                    + ", ".join(unverified_types)
                    + ") but failed validation"
                    + (f" ({', '.join(failures[:3])})" if failures else "")
                    + " — not trusted, no provenance floor"
                )
            if possibly_types:
                score = max(score, 0.55)
                findings.append(
                    "Possibly-generative source type (" + ", ".join(possibly_types)
                    + ") — C2PA rubric 'possibly GenAI' tier, not a generative claim"
                )
            if action_labels:
                findings.append("Actions: " + ", ".join(action_labels[:5]))
                score = min(0.55, score + 0.06)
            if soft_binding:
                findings.append(
                    "Soft-binding hint without generative source type — inspect assertions; "
                    "not SynthID verification"
                )
            findings.append(
                "Manifest presence ≠ authenticity proof; inspect assertions before trusting disclosure"
            )
        else:
            # Neutral-absent: do not punish; social re-encode / screenshot usually strips C2PA
            score = 0.45
            confidence = 0.4
            findings.append(
                "No C2PA/Content Credentials markers detected — common after platform re-encode, "
                "download, or screenshot; absence is not proof of authenticity"
            )
            findings.append(
                "Fall back to pixel_forensic + OCR paths; this tool is a local examiner, "
                "not X's upload-time provenance gate (and X may use undisclosed criteria beyond C2PA)"
            )
        if unbound:
            findings.append(
                "digitalSourceType text found outside any manifest container ("
                + ", ".join(unbound)
                + ") — not a C2PA claim, ignored"
            )

        return AnalyzerOutput(
            id=self.id,
            name=self.name,
            score=float(np.clip(score, 0, 1)),
            confidence=float(np.clip(confidence, 0, 1)),
            findings=findings,
            details=details,
        )
