import { EVIDENCE_PATH_META, VERDICT_META, type AnalysisResult, type EvidencePath } from '../types'

function Gauge({ probability, color }: { probability: number; color: string }) {
  const pct = Math.round(probability * 100)
  return (
    <div className="relative mx-auto h-40 w-40">
      <div
        className="gauge-ring absolute inset-0 rounded-full"
        style={
          {
            '--gauge-pct': pct,
            '--gauge-color': color,
          } as React.CSSProperties
        }
      />
      <div className="absolute inset-[10px] flex flex-col items-center justify-center rounded-full bg-[#0b101a] shadow-inner">
        <div className="text-4xl font-semibold tabular-nums" style={{ color }}>
          {pct}
        </div>
        <div className="text-xs uppercase tracking-widest text-slate-400">AI cue score /100</div>
      </div>
    </div>
  )
}

export function VerdictPanel({ result }: { result: AnalysisResult }) {
  const meta = VERDICT_META[result.verdict]
  return (
    <div className="rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900/90 to-slate-950/90 p-6 shadow-xl shadow-black/20">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-[220px] flex-1">
          <span className={`inline-flex rounded-full border px-3 py-1 text-sm font-medium ${meta.badge}`}>
            {meta.label}
          </span>
          {result.screenshot_detected && (
            <span className="ml-2 inline-flex rounded-full border border-violet-500/30 bg-violet-500/10 px-3 py-1 text-xs text-violet-200">
              Screenshot-like
            </span>
          )}
          <p className="mt-4 text-sm leading-relaxed text-slate-300">
            {result.summary.replace(/ensemble AI probability (\d+)%/i, (_, score: string) => `ensemble AI cue score ${score}/100`)}
          </p>
          <div className="mt-4 flex flex-wrap gap-4 text-xs text-slate-500">
            <span>{result.filename}</span>
            <span>
              {result.dimensions[0]}×{result.dimensions[1]}
            </span>
            <span>{result.analysis_ms} ms</span>
            <span>signal confidence {(result.confidence * 100).toFixed(0)}%</span>
          </div>
          {result.evidence_paths && result.evidence_paths.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {result.evidence_paths.map((path) => (
                <span
                  key={path}
                  className="inline-flex rounded-full border border-slate-700 bg-slate-800/60 px-2.5 py-0.5 text-[11px] text-slate-300"
                >
                  {EVIDENCE_PATH_META[path as EvidencePath]?.label ?? path}
                </span>
              ))}
            </div>
          )}
          {result.challenge_flags && result.challenge_flags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {result.challenge_flags.map((flag) => (
                <span
                  key={flag}
                  className="inline-flex rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 text-[11px] text-amber-100"
                  title="Research challenge flag from fusion calibration"
                >
                  {flag}
                </span>
              ))}
            </div>
          )}
          {result.failure_modes && result.failure_modes.length > 0 && (
            <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Failure modes
              </div>
              <ul className="mt-1.5 space-y-1 text-[11px] leading-snug text-slate-400">
                {result.failure_modes.slice(0, 6).map((mode) => (
                  <li key={mode} className="flex gap-2">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-600" />
                    <span>{mode}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <Gauge probability={result.ai_probability} color={meta.color} />
      </div>
    </div>
  )
}
