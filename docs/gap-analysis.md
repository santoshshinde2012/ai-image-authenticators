# Gap analysis (2026-09-18)

A code audit plus a standards/literature review of what this examiner gets wrong and what it is
missing. Audited at commit `d837787` (weights **v1.3**, 55 tests); fixes landed in `dcfa889` (103 tests).

Every claim is tagged:

- `[measured]` — reproduced by running this repository's code on this machine.
- `[primary]` — verified by fetching the primary source (spec, registry, paper, regulation).
- `[reported]` — from the research pass, **not** independently verified here. Treat as a lead.

Ordered by how wrong the output is. Each fixed item is marked **Fixed** with the commit and the
regression test that pins it (`apps/api/tests/test_audit_regressions.py`, `test_image_loader.py`).

## Status (2026-09-18)

| Item | Status |
|---|---|
| P0-1 OCR floor on ordinary text | **Fixed** in `dcfa889` |
| P0-2 unsigned bytes force a verdict; wrong source-type taxonomy | **Fixed** in `dcfa889` |
| P0-3 DCT periodicity is a resize artifact | **Fixed** in `dcfa889` (the metric itself stays weak — see below) |
| P0-4 decode: animated, 16-bit, alpha, orientation, AVIF, tiny images | **Fixed** in `dcfa889` (HEIC still unsupported) |
| P1-5 no pixel-count cap | **Fixed** in `dcfa889` |
| P1-6 remote manifest fetch | **Fixed** in `dcfa889` (disabled per reader instance) |
| P2-7 C2PA validation | **Partly fixed**: signature + hard binding validated when the extra is installed; no trust list yet |
| P2-8 CPU-decodable watermarks (SDXL, TrustMark) | Open |
| P2-9 calibrated bands / measured FPR | Open |
| P2-10 absent classical signals | Open |
| P3-11, P3-12 claims | Corrected in the README, docs and article |
| Miscalibrated thresholds (table below) | Open — needs P2-9's evaluation data first |

The three benchmark fixtures kept their published probabilities through all of the fixes
(0.8889 / 0.8467 / 0.9200); only the probe drift figures in `fusion_reasons` changed, because they are
now computed over matching analyzer sets.

---

## P0 — Bugs that produce confidently wrong verdicts

### 1. The OCR disclosure floor fires on ordinary text

`labels.py` matches bare brand tokens with no word boundaries and no badge geometry, and
`fusion_policy.py:80-87` turns any hit into `ai_probability = max(p, 0.82…0.92)` plus
`confidence ≥ 0.88`. The pixel witnesses cannot override it.

`[measured]` Strings that match today:

| Text in the image | Matched "disclosure" |
|---|---|
| `Kendall Edwards, staff photographer` | DALL·E |
| `Randall E. Smith` | DALL·E |
| `visto dalle finestre` (ordinary Italian) | DALL·E |
| `cleared to land on runway 27L` | Runway |
| `A firefly lit up the summer night` | Adobe Firefly |
| `Gemini is the third astrological sign` | Gemini |
| `Read more about Content Credentials` | Content Credentials |

Causes: `dall[\s.\-]?e` has no `\b` anchors; `r"runway\s*(ml|gen)?"` and `r"adobe\s*firefly|firefly"`
make the qualifier optional; `\bgrok\b` / `\bgemini\b` / `\bimagen\b` are ordinary words. Matching
`content credentials` is backwards — that badge marks **authentic** C2PA captures.

`[reported]` OCR over 10 preprocessing variants of a *textless* photograph produced ~11 k characters
of noise that contained a DALL·E match, giving `ai_generated` p=0.92 on a real photo.

**Fixed** in `dcfa889`. Disclosure phrasing ("made with AI", "AI-generated", …) still counts anywhere.
Generator names count only inside disclosure phrasing ("made with Midjourney") or, for distinctive
names, when OCR finds them in a badge-region crop. Ordinary words (runway, firefly, gemini, grok, imagen)
never count alone, every pattern is word-bounded, "Content Credentials" is reported as a provenance
marker, and repeated OCR lines of the same pixels no longer inflate confidence. `metadata.py` had the
same bug over 200 KB of raw bytes; it now reads EXIF/XMP/text chunks only and trusts ordinary-word names
only in a Software or CreatorTool field. Still open: Tesseract word-confidence gating and badge geometry.

`[primary]` Two regulators have published *geometric* badge rules worth targeting instead of free-text
matching: the EU Code of Practice specifies the acronym `AI` (with `AI GENERATED` / `AI MODIFIED`) in
the **top-right corner**; China's GB 45438-2025 §5.2 requires an AI token plus a generation token, on
an **edge or corner**, at **≥ 5% of the shortest side** in glyph height. A 5% size floor alone would
reject every false positive above.

### 2. Unsigned bytes force a verdict, and the source-type list is wrong in both directions

`provenance.py` regex-scans the file for `digitalsourcetype/<value>`; `fusion_policy.py:62` then sets
`ai_probability = max(p, 0.82)`. No hard-binding check, no certificate validation, no trust list.

`[measured]` Appending one ASCII string to a plain PNG — no manifest, no JUMBF, no signature:

| Appended to the file | Verdict |
|---|---|
| `…/digitalsourcetype/trainedAlgorithmicMedia` | `ai_generated` p=0.82 |
| `…/digitalsourcetype/algorithmicallyEnhanced` | `ai_generated` p=0.82 |
| `…/digitalsourcetype/dataDrivenMedia` | `ai_generated` p=0.82 |
| `…/digitalsourcetype/trainedAlgorithmicData` | **not recognized** |

Two separate problems:

- **False positives.** Per IPTC, `algorithmicallyEnhanced` is algorithmically-*altered* media and
  `dataDrivenMedia` is a data visualisation. `[primary]` The EU Art. 50 guidelines expressly exempt
  noise reduction, minor crops, colour adjustment and red-eye removal from marking duties, so an
  honest `algorithmicallyEnhanced` credential is evidence of the kind of editing the law does *not*
  treat as generative. We force it to 0.82.
- **False negative.** `trainedAlgorithmicData` is in C2PA's official rubric and missing from
  `AI_SOURCE_TYPE_SUFFIXES`. `[primary]` Since spec 2.2 these values are URL-form
  (`http://c2pa.org/digitalsourcetype/...`).

`[primary]` C2PA publishes the authoritative mapping as machine-readable YAML with a `$genai_dst_types`
/ `$possibly_genai_dst_types` split (rubric v1.0, 2026-08-06):
<https://github.com/c2pa-org/conformance-public/blob/main/asset-rubrics/asset-rubric-signals-local.yml>

**Fixed** in `dcfa889`. Only claims inside a manifest container (PNG `caBX`, JPEG APP11/JUMBF, WebP
`C2PA` chunk) can set the floor; strings elsewhere are reported as `unbound_source_type_strings` and
ignored. The taxonomy now follows the rubric (generative, possibly-generative, everything else merely
declared). With the `c2pa` extra, a manifest the reader rejects or marks `Invalid` never sets the floor.
`[measured]` A genuinely signed test manifest validates as `Valid`; the same manifest spliced onto
different pixels comes back `Invalid` and is denied the floor.

### 3. `dct.ac_periodicity` measures resampling, not quantization

`dct.py:70-74` resizes to 768 px **before** the 8×8 block DCT, which throws the DCT grid off the JPEG
lattice for any larger JPEG.

`[measured]` Same content, JPEG q80:

| Content | 700 px | 1400 px |
|---|---|---|
| uniform noise | −0.016 | **+0.943** |
| gradient + grain | +0.002 | **+0.821** |
| fine texture | −0.012 | **+0.922** |
| smooth gradient | +0.026 | +0.026 |

Above 0.35 it reports "possible double quantization / recompress" and adds **+0.35** to the laundering
score — 78% of the 0.45 trigger, after which spectral weights are scaled by as little as ×0.35. The
affected class is ordinary grainy camera JPEGs over 768 px. `[measured]` It does not detect what it
claims: single Q75 = −0.0146 vs double Q75→Q90 = −0.0115. Real double-quantization forensics must read
stored coefficients (`jpegio`/libjpeg), not re-DCT decoded pixels.

The repo's three fixtures are unaffected (all ≤ 0.011), which is why this never showed up.

**Fixed** in `dcfa889`: JPEG inputs are decoded from the stored bytes and cropped on the 8×8 grid
instead of resampled. `[measured]` The grainy 1400 px JPEG now reads −0.005 (was +0.821). The finding
text no longer claims double quantization, because the metric still cannot detect it; real
double-quantization forensics (reading stored coefficients) remains open.

### 4. Decode: five input classes are silently wrong

`image_loader.py` is `Image.open` → `load()` → `convert("RGB")`, with no frame, orientation, bit-depth
or alpha handling. `[measured]`:

| Input | Behaviour |
|---|---|
| animated GIF / WebP | `n_frames=3`, only frame 0 analyzed; verdict `ai_generated` p=0.827 from a flat frame |
| 16-bit PNG | clips instead of scaling: 50% gray (33012/65535) decodes to 254.4/255, near-white |
| alpha PNG | alpha dropped, not composited over a background |
| EXIF Orientation=6 | ignored, so the image is analyzed sideways and the OCR badge crops target the wrong corners |
| HEIC / AVIF | rejected at upload (no magic bytes), though Pillow can decode AVIF — these are the common phone formats |

Small-image paths degrade silently rather than guarding: below 16 px `noise.py:44` builds an empty
`var_map`, so `mean_var=0.0` scores 0.70–0.84 "sensor noise largely absent" from a measurement that
never ran.

**Fixed** in `dcfa889`: 16-bit is scaled, alpha composited over white, EXIF orientation applied (the
analyzers still see the original container's format and EXIF), animated inputs analyzed on frame 0 with
a note, AVIF accepted, and images under 32 px rejected with HTTP 422. Every decode choice is appended to
`failure_modes`. HEIC remains unsupported (it needs a new dependency).

---

## P1 — Robustness and safety

### 5. No pixel-count cap: 80 KB in, 3 GB out

`[measured]` A flat 5000×5000 PNG is **80 KB** on disk, passes the 25 MB upload cap, and drives
**3.0 GB RSS over 5 s** — 37,000× amplification. There is no pixel limit anywhere; Pillow's default
`MAX_IMAGE_PIXELS` (89 MP) is the only backstop and an attacker can sit just under it.

Multipliers: `ela.py:41` is the one pixel analyzer with no `max_side` cap and allocates roughly
20 B/px twice; `screenshot.py` runs Canny/Sobel at native size; `probes.py` re-encodes the full
array twice more and re-runs the bank on each. Also `uploads.py` does `await file.read()` **before**
the size check, so `max_bytes` never bounds memory.

**Fixed** in `dcfa889`: `AIAUTH_MAX_IMAGE_PIXELS` (default 50 MP) is checked from the header before
decoding (HTTP 413), ELA is capped at 2048 px, and the upload read stops one byte past the byte cap.
`[measured]` The 25 MP case dropped from 3.0 GB to 1.5 GB peak RSS; the worst accepted input (48 MP)
peaks at 2.4 GB.

### 6. `remote_manifest_fetch` defaults to true in c2pa-rs

`[reported]` `Verify::default()` in `c2pa-rs` sets `remote_manifest_fetch: true`. If the optional
`c2pa` extra is installed, constructing a `Reader` on an attacker-supplied image could trigger an
outbound request to a URL embedded in that image — an SSRF-shaped surface in a tool that advertises
offline, in-process analysis. `c2pa-python` exposes `load_settings()`, so pinning
`{"verify": {"remote_manifest_fetch": false, "verify_trust": true}}` is a few lines.

**Fixed** in `dcfa889`, against the locked `c2pa-python` 0.37.10: every reader gets a per-instance
`Context(Settings.from_dict({"verify": {"remote_manifest_fetch": False}}))` (the non-deprecated API).

---

## P2 — Missing capability, in value order

### 7. No C2PA validation, though the pieces are free and offline

`[primary]` Spec 2.4 separates **Well-formed / Valid / Trusted** (§14.3) and requires validating the
asset's hard binding (§15.12; mismatch → `assertion.dataHash.mismatch`). We do none of it, so a
tampered image with an intact manifest reads as "provenance present".

`[primary]` The trust list is small and pinnable for offline use: `C2PA-TRUST-LIST.json` is **67 KB**
with 17 trusted CAs, `NextUpdate` 2027-08-05, plus a 51 KB TSA list.
<https://github.com/c2pa-org/conformance-public/tree/main/trust-list>

`[primary]` I parsed the Conforming Products List (213 entries): Google, Xiaomi and vivo appear in both
the products and trust lists; Qualcomm in products only; **Sony, Canon, Nikon, Leica, Samsung and
Fujifilm are in neither.** Camera-maker certificates sit outside the official trust list, so a
conformant validator may not trust them — useful context for how rare a *trusted* manifest is.

`[primary]` `provenance.py:263` called `str(reader.get_validation_state)` without `()`, stringifying a
bound method; `get_validation_results()` was never used; `crypto_validated` was only ever set `False`.
The reader was also invoked as `Reader.try_create(stream)`, passing the stream as the format argument.

**Partly fixed** in `dcfa889`: the reader is called correctly, its state and failure codes are
reported, and `crypto_validated` means signature plus hard binding checked. Still open: vendoring the
trust list so a manifest can be reported `Trusted` rather than only `Valid`.

### 8. A real watermark can be decoded today, on CPU, without keys

The README lists watermark decoding as out of scope. That is right for SynthID and wrong in general.

`[primary]` The SDXL pipeline in `diffusers` embeds a **fixed, public 48-bit** watermark via the MIT
`invisible-watermark` library, and the constant is in the source
(`pipelines/stable_diffusion_xl/watermark.py`). `WatermarkDecoder('bits', 48).decode(bgr, 'dwtDct')`
recovers it on CPU. A 48-bit exact match has a 2⁻⁴⁸ collision probability, which would be the bank's
only near-zero-false-positive **positive** signal.

`[primary]` Adobe **TrustMark** is MIT with weights, a 20–35 MB decoder that runs on CPU, and its
identifiers are registered C2PA soft-binding algorithms.

Honest limits, from the library's own README: not robust to resize or aspect-changed crop, and weak on
screenshots — so absence means nothing, and it will usually not survive the screenshot path.

Related: the current `soft_binding` hint greps file bytes for the literal string `synthid`. SynthID is
a pixel-domain watermark that writes no such string, so that check can only fire on incidental text.

### 9. The bands are uncalibrated and `ai_generated` may be unreachable from pixels

`[reported]` A 72-image probe (39 Wikimedia Featured Pictures, 33 Community-Forensics AI images) gave
**ROC AUC 0.827** but **TPR at the 0.75 band = 0/33**, FPR 5.1%, and 61.5% of pristine photographs
failed to be called `real`. The only two images that reached `ai_generated` were **real photographs**,
both via the OCR misfire in P0-1.

That probe is not independently verified here, but it is consistent with everything above, and with
`[measured]` behaviour on trivial inputs: a plain gradient PNG scores `ai_generated` p=0.8826 and a
flat 25 MP gray PNG scores p=0.8389. Featureless and smooth content reads as AI.

Free, ungated evaluation sets to fix this with `[reported]`, all CPU-feasible:

| Set | Size | Note |
|---|---|---|
| SynthWildX | 500 real + 1,500 synthetic, from X | closest to this tool's use case |
| NTIRE 2026 Validation-Hard | 2.5 K balanced, 7 generators, 19 transformations | labels released |
| Synthbuster | 9 K, 9 diffusion models | pair with RAISE-1k for reals |
| Community Forensics-Small | ~300 K, 4,803 generators | CC-BY-NC-SA |

Publishing our own measured AUC and FPR is **not** a leaderboard claim; the honesty rule forbids
quoting others' benchmark scores, not measuring ourselves.

### 10. Absent classical signals

Never computed, all cheap, all positive evidence for "this is a camera photo" — the side the bank is
weakest on: JPEG quantization tables (`dct.py` mentions double quantization but never reads
`image.quantization`), EXIF thumbnail vs image mismatch, MakerNote presence, ICC profile identity, and
CFA/demosaicing periodicity.

---

## P3 — Claims to correct

### 11. The X premise: stripping is proven, the labelling mechanism is not

The README says platform labels "often reflect C2PA / Content Credentials at upload", cited to a Medium
post and roboin.io.

`[primary]` *GPT-Image-2 in the Wild* (arXiv:2604.25370, Zewde et al., 28 Apr 2026), 10,217 confirmed
images from Twitter: **"C2PA content credentials are systematically stripped by Twitter's CDN on
upload, rendering cryptographic provenance verification infeasible for social-media-sourced AI
images."** The authors therefore verified the badge through browser automation instead of the bytes.

**Correction to an earlier version of this document:** it inferred that a badge found in the DOM
"cannot be reading a manifest that no longer exists". That does not follow. A label decided at upload,
while the manifest still existed, would be rendered from server state after the CDN strips the bytes —
which is exactly this repo's premise. The paper proves the stripping; it says nothing either way about
how X decides the label.

`[primary]` X, xAI and Twitter appear in neither the C2PA Conforming Products List nor the Trust List.

The *second* half of the premise — that platforms strip metadata — is solid and better sourced than we
have it: NIST AI 100-4 on metadata stripping, CAI's durable-credentials post on screenshots, and
Cloudflare discarding Content Credentials by default.

Recommended (done in the article and README): keep the framing, state plainly that X has not
documented its mechanism, and add arXiv:2604.25370 as the evidence for stripping.

### 12. Smaller corrections

- `[primary]` TRIDENT fuses **six** detectors across semantic (CLIP, SigLIP), structural (EVA-02) and
  spectral (SRM, Bayar) branches with a degradation curriculum. We ship the two cheapest spectral ones
  and cite it as "TRIDENT spirit" — worth saying which two.
- `[primary]` "Dual-layer is industry practice" is an EU-side claim. China's GB 45438 §6.2 *permits*
  watermarks (准许) while mandating metadata; the EU Code requires both. Soften in
  `docs/research-challenges.md`.
- `[primary]` The SynthID reference URL now redirects to `deepmind.google/models/synthid/`.
- `[primary]` `docs/references.md` "spec 2.4" is still current (April 2026).
- The EU Code of Practice states that **"forensic detection mechanisms were not deemed mature enough"**
  for Art. 50(2) — a regulator's own words, and a better `failure_modes` line than ours.

---

## Dead code and never-firing thresholds

`[measured]` unless noted. None of these change a verdict today; several mean a documented signal is
not actually contributing.

| Item | Status |
|---|---|
| `fft.hf_power_ratio < 0.08` | ~0 for every image (max 1.8e-5) — always fires |
| `fft.axis_boost > 1.32` | **5,905,469** on a plain gradient; **0.90** on a genuinely 2× upsampled image — inverted |
| `noise.flat_frac > 0.33` | unreachable: it is the fraction below *half* the 20th percentile, so ≤ 0.20 |
| `srm.cross_filter_energy_cv < 0.12` | fires only for a literally constant image |
| `texture.glcm_homogeneity > 0.72` | GLCM uses 4 gray levels; 0.75–0.9998 observed — always fires |
| `challenge_flags.py` 0.22 inconclusive pull | **Fixed** (removed; the conflict now only lowers confidence, as it always did in effect) |
| `probes.py` clean vs probe sets | **Fixed**: both sides use the ids the probe actually ran; smooth-sample drift now +0.013 |
| `probes.py` Q=85 lean-flip check | **Fixed**: flips are detected independently of the delta |
| `srm.py:80` reuses `bayar.prediction_residual` | bayar counted twice (0.11 + 0.07) in a weight table that sums to 1.0 |
| `.convert("RGB")` drops `Image.format` | **Fixed**: probe re-encodes are marked `JPEG` |
| `fusion_calibrate.py:19` `reasons` param | **Fixed** (removed) |
| `ChallengeAssessment.laundering_score` / `spectral_weight_scale` | **Fixed**: one shared `spectral_weight_scale()` feeds both the weights and the audit text |
| `Artifact.filename` | written, never read (harmless) |
| `Settings.environment` | **Fixed**: `prod` now hides decoder error text in API responses |

The remaining open rows are calibration questions rather than coding errors: there is no correct
threshold for `axis_boost` or GLCM homogeneity without labelled data, so they wait for P2-9 instead of
being re-guessed.

Test-suite gaps that let these survive — no fixture ever set `is_screenshot=True`, the
OCR-confidence-scaled floor had no test, and several assertions could not fail (`assert ... or True`) —
are **fixed**: the suite went from 55 to 103 tests and CI now installs the `c2pa` extra.

---

## Correctly out of scope

`[primary]` Confirmed not worth pursuing: SynthID decoding (verification is trusted-tester only, and it
is not a registered C2PA soft-binding algorithm); Tree-Ring / RingID / Gaussian Shading / PRC, which all
need model weights **and** a secret key by construction; tuning weights against GenImage, whose SD-family
splits make detectors look near-perfect; and reverse-engineering X's labelling gate, which strips the
metadata and publishes no mechanism.

`[primary]` **No labeling or provenance duty binds a detector** in any jurisdiction checked (EU, China,
India, South Korea, US federal + CA/TX/CO/WA/NY/MN/FL, Japan, Canada, Brazil, UK). Every duty runs to
generators, deployers, platforms, capture-device makers or advertisers. A full-text search of the US
Code of Federal Regulations returns zero sections for "synthetic media", "content provenance",
"deepfake", "AI-generated" or "C2PA".

**The one real exposure is advertising substantiation, and it is about accuracy claims.**
`[primary]` The FTC has already acted against an AI-*detection* vendor: *In re Workado*, Docket C-4822
(final order 2025-08-21). Workado advertised "over 98 percent accuracy"; the FTC alleged under s.5(a)
that the claim "was not substantiated at the time the representation was made", that the model was
tuned on academic text while users submitted marketing copy, and that measured accuracy on non-academic
text was "around 53 percent". The order covers "products that detect or purport to detect content,
including text, images". It requires competent and reliable evidence for each effectiveness claim, and
retention of protocols, datasets, train/test-overlap analysis and **confusion matrices**.

Read against this repo: the existing refusal to quote leaderboard scores is exactly right, and P2-9
should follow the same rule — if we publish a measured AUC or FPR, keep the harness, the split and the
confusion matrix alongside it, and scope the claim to what was tested. The highest-risk framing would be
treating absent provenance as proof of synthesis, which the fusion policy already avoids.

Two other edges: `[primary]` EU Annex III 6(c) makes evidence-reliability systems used on behalf of law
enforcement high-risk from 2027-12-02, so do not market this for evidence assessment; and China's Deep
Synthesis Provisions Art. 18 forbids tools that remove or conceal labels — a read-only inspector is
fine, a "clean export" feature would not be.

### What the live regimes actually expect to find

Useful because it defines what is worth surfacing, not because it binds us. `[primary]` India's IT
Rules amendment (G.S.R. 120(E), in force 2026-02-20) requires synthetic content to carry a visible label
**and** "permanent metadata or other appropriate technical provenance mechanisms, to the extent
technically feasible, including a unique identifier" naming the originating service, and forbids
removing it. The draft's ten-percent-of-display-area rule was **dropped** (the phrase appears nowhere in
the notified text). `[primary]` South Korea's AI Framework Act Art. 31 (in force 2026-01-22) permits a
purely machine-readable label paired with a one-time human notice. Neither names C2PA or any other
standard.

So: report what was found, never "compliant with X". And note that a missing label is frequently lawful
— India's own definition excludes routine editing, compression, translation and accessibility work, and
Korea disapplies labeling where AI use is obvious from the product name.

---

## Suggested order (remaining)

1. P2-9 — measure against SynthWildX and publish FPR with the harness, split and confusion matrix
   alongside it (the Workado constraint above). This unblocks every calibration row in the table.
2. P2-7 — vendor the C2PA trust list so `Trusted` becomes reportable.
3. P2-8 — the SDXL and TrustMark decoders, as a near-zero-false-positive positive signal.
4. P2-10 — quantization tables, MakerNote, ICC and thumbnail checks: cheap evidence for real photos.
