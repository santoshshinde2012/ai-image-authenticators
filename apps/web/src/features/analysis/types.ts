export type Verdict = 'real' | 'inconclusive' | 'likely_ai' | 'ai_generated'

/** Matches API `evidence_paths` values from WeightedFusionPolicy. */
export type EvidencePath = 'provenance_contract' | 'pixel_forensic' | 'screenshot_path'

/** Stable analyzer ids used by fusion weights, API signals, and the UI. */
export type AnalyzerId =
  | 'metadata'
  | 'provenance'
  | 'labels'
  | 'ela'
  | 'fft'
  | 'dct'
  | 'noise'
  | 'srm'
  | 'bayar'
  | 'local_corr'
  | 'texture'
  | 'screenshot'

export interface SignalResult {
  id: AnalyzerId | string
  name: string
  score: number
  confidence: number
  weight: number
  findings: string[]
  viz_url?: string | null
  details?: Record<string, unknown>
}

export interface AnalysisResult {
  verdict: Verdict
  ai_probability: number
  confidence: number
  summary: string
  signals: SignalResult[]
  limitations: string[]
  filename: string
  dimensions: number[]
  screenshot_detected: boolean
  analysis_ms: number
  evidence_paths?: EvidencePath[] | string[]
  fusion_reasons?: string[]
  /** Research-challenge markers from fusion (laundering / dual-layer / shift). */
  challenge_flags?: string[]
  /** Static + dynamic failure-mode strings (calibrated honesty, not SOTA claims). */
  failure_modes?: string[]
}

export const VERDICT_META: Record<
  Verdict,
  { label: string; color: string; badge: string }
> = {
  real: {
    label: 'Likely Real',
    color: '#34d399',
    badge: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  },
  inconclusive: {
    label: 'Inconclusive',
    color: '#fbbf24',
    badge: 'bg-amber-500/15 text-amber-200 border-amber-500/30',
  },
  likely_ai: {
    label: 'Likely AI',
    color: '#fb923c',
    badge: 'bg-orange-500/15 text-orange-200 border-orange-500/30',
  },
  ai_generated: {
    label: 'AI Generated',
    color: '#f87171',
    badge: 'bg-rose-500/15 text-rose-200 border-rose-500/30',
  },
}

export const EVIDENCE_PATH_META: Record<EvidencePath, { label: string }> = {
  provenance_contract: { label: 'Provenance contract (C2PA / OCR)' },
  pixel_forensic: { label: 'Pixel forensic' },
  screenshot_path: { label: 'Screenshot path' },
}
