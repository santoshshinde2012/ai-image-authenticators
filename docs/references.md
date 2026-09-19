# References (verified URLs only)

Authoritative bibliography for this repository. Every URL below resolved when last checked
(2026-09-18); a few publishers (Medium, OpenAI) answer automated requests with 403, which is
bot protection rather than a dead link. **Never invent** paper titles, arXiv IDs, authors, venues,
or public leaderboard numbers. Each row maps the cite → the module that uses it.

## C2PA / Content Credentials

| Source | URL | Used by |
|---|---|---|
| C2PA Technical Specification 2.4 | https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html | `application/analyzers/provenance.py` |
| C2PA Implementation Guidance 2.4 | https://spec.c2pa.org/specifications/specifications/2.4/guidance/Guidance.html | `provenance.py`, docs |
| C2PA white paper (2026-07-30): *Use of Content Credentials to Identify Synthetic and Non-Synthetic Content* | https://c2pa.org/wp-content/uploads/sites/33/2026/07/Use-of-Content-Credentials-to-Identify-Synthetic-and-Non-Synthetic-Content.pdf | `provenance.py` (`digitalSourceType` / synthetic labeling) |
| C2PA Resources | https://c2pa.org/resources/ | docs |
| Content Credentials site | https://contentcredentials.org/ | docs / product framing |
| `c2pa-python` (optional Reader) | https://github.com/contentauth/c2pa-python | `provenance.py` (optional `validation_state`) |
| C2PA Conformance — signals rubric (`asset-rubric-signals-local.yml`, rubric v1.0, 2026-08-06) | https://github.com/c2pa-org/conformance-public/blob/main/asset-rubrics/asset-rubric-signals-local.yml | `provenance.py` (generative / possibly-generative `digitalSourceType` sets) |
| C2PA Trust List and Conforming Products List | https://github.com/c2pa-org/conformance-public | [gap-analysis.md](./gap-analysis.md) (trust evaluation, which vendors sign) |

## X "Made with AI" investigations

| Source | URL | Used by |
|---|---|---|
| Utkarsha Bakshi — *I Investigated How X Detects AI Generated Images. It's Not SynthID.* (Medium / Agile Insider) | https://medium.com/agileinsider/i-investigated-how-x-detects-ai-generated-images-its-not-synthid-acb2a4bfab44 | `provenance.py`, `labels.py`, fusion limitations, article |
| Roboin — *Why is "Made with AI" automatically added to my X posts? Can I remove it? Testing the conditions* (2026-03-24) | https://roboin.io/article/en/2026/03/24/why-x-tags-posts-as-made-with-ai-and-how-to-remove-it-testing-the-conditions/ | fusion limitations (**do not overclaim C2PA-only**) |
| Zewde et al. — *GPT-Image-2 in the Wild* (arXiv:2604.25370): C2PA "systematically stripped by Twitter's CDN on upload" across 10,217 images | https://arxiv.org/abs/2604.25370 | article §I, [gap-analysis.md](./gap-analysis.md) |

## Dual-layer industry notes (C2PA + SynthID-class)

Complementary layers: signed manifests (C2PA) + durable invisible watermarks (SynthID-class).
**This repo inspects C2PA / OCR / classical forensics only — it does not decode SynthID.**

| Source | URL | Used by |
|---|---|---|
| OpenAI — *Advancing content provenance for a safer, more transparent AI ecosystem* | https://openai.com/index/advancing-content-provenance/ | docs / limitations |
| OpenAI Help — Provenance signals (Content Credentials, SynthID) | https://help.openai.com/en/articles/8912793-provenance-signals-content-credentials-synthid-in-openai-generated-content | docs / limitations |
| Google DeepMind — SynthID | https://deepmind.google/models/synthid/ | docs (watermark layer we do **not** verify) |
| Google — Pixel / Android trusted images with C2PA Content Credentials | https://blog.google/security/pixel-android-trusted-images-c2pa-content-credentials/ | docs (capture-time credentials) |

## Classical forensics

| Source | URL | Used by |
|---|---|---|
| Durall et al., CVPR 2020 — *Watch Your Up-Convolution: CNN Based Generative Deep Neural Networks Are Failing to Reproduce Spectral Distributions* (CVF Open Access) | https://openaccess.thecvf.com/content_CVPR_2020/html/Durall_Watch_Your_Up-Convolution_CNN_Based_Generative_Deep_Neural_Networks_Are_CVPR_2020_paper.html | `application/analyzers/fft.py` |
| Fridrich & Kodovský — Rich Models for Steganalysis of Digital Images (IEEE; SRM lineage) | https://ieeexplore.ieee.org/document/6165621 | `application/analyzers/srm.py` |
| Bayar & Stamm — constrained convolutional predictor lineage (IEEE) | https://ieeexplore.ieee.org/document/7544586 | `application/analyzers/bayar.py` |
| ELA / JPEG recompression forensics (classical method family) | implemented directly from standard ELA/JPEG practice | `ela.py`, `dct.py` |

## Ensembles & surveys (fusion *inspiration* — not claimed scores)

| Source | URL | Used by |
|---|---|---|
| HEDGE — *Heterogeneous Ensemble for Detection of AI-GEnerated Images in the Wild* (arXiv:2604.03555) | https://arxiv.org/abs/2604.03555 | `application/services/fusion_policy.py` (heterogeneous ensemble / gating *spirit*) |
| TRIDENT — *Robust Deepfake Detection via Tri-Modal Forensic Ensembles* (CVPRW 2026 / NTIRE Open Access) | https://openaccess.thecvf.com/content/CVPR2026W/NTIRE/html/Sharma_TRIDENT_Robust_Deepfake_Detection_via_Tri-Modal_Forensic_Ensembles_CVPRW_2026_paper.html | fusion + multi-modal forensic framing |
| Survey (arXiv:2502.19716) | https://arxiv.org/abs/2502.19716 | docs (landscape) |
| Survey (arXiv:2504.02898) | https://arxiv.org/abs/2504.02898 | docs (landscape) |
| Multi-view related (arXiv:2609.11188) | https://arxiv.org/abs/2609.11188 | docs (multi-signal motivation; `local_corr`) |
| Open-source detector OOD benchmark (arXiv:2602.07814) | https://arxiv.org/abs/2602.07814 | `docs/research-challenges.md` (generator/domain shift) |
| Generator-shift robustness (arXiv:2608.11643) | https://arxiv.org/abs/2608.11643 | `docs/research-challenges.md` (domain shift) |
| BIAS-ID transformation bias (arXiv:2605.31153) | https://arxiv.org/abs/2605.31153 | `docs/research-challenges.md` (dataset/transform bias) |

## Engineering inspiration (clearly labeled — not vendored)

| Source | URL | Used by |
|---|---|---|
| ForenAgent — *Code-in-the-Loop Forensics: Agentic Tool Use for Image Forgery Detection* (arXiv:2512.16300) + toolkit | https://arxiv.org/abs/2512.16300 · https://github.com/zfr00/ForenAgent | classical tool-bank inspiration (SRM/FFT/Bayar/local-corr style); **we do not ship their agent loop** |
| `aidetect` / lynote-ai `ai-image-detector` CLI | https://github.com/lynote-ai/ai-image-detector | classical spectrum / CLI UX inspiration; **ML backends optional / not required for v1** |

## Consumer protection

| Source | URL | Used by |
|---|---|---|
| FTC — *In re Workado, LLC*, Docket C-4822 (AI-detector accuracy claims; order covers text **and images**) | https://www.ftc.gov/legal-library/browse/cases-proceedings/2323092-content-scale-ai | [gap-analysis.md](./gap-analysis.md) (why this repo publishes no unsubstantiated accuracy numbers) |

## Challenges map

| Source | URL | Used by |
|---|---|---|
| This repo — challenges → resolutions | [research-challenges.md](./research-challenges.md) | `challenge_flags.py`, `fusion_calibrate.py`, API `challenge_flags` |

## Honesty constraints

- No GenImage / NTIRE public leaderboard numbers are claimed for **this** repository.
- No fabricated "admin analytics" or unpublished X detector source.
- X labeling: inspectable path is C2PA-oriented at upload; Roboin shows **undisclosed criteria may also apply**.
