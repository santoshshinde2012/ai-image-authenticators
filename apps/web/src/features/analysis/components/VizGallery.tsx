import type { SignalResult } from '../types'

export function VizGallery({
  vizSignals,
  activeViz,
  activeSignal,
  onSelect,
}: {
  vizSignals: SignalResult[]
  activeViz: string | null
  activeSignal?: SignalResult
  onSelect: (id: string) => void
}) {
  if (vizSignals.length === 0) return null
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/50">
      <div className="flex flex-wrap gap-2 border-b border-slate-800 p-3">
        {vizSignals.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => onSelect(s.id)}
            className={[
              'rounded-lg px-3 py-1.5 text-sm transition',
              activeViz === s.id ? 'bg-sky-500/20 text-sky-200' : 'bg-slate-900 text-slate-400 hover:text-slate-200',
            ].join(' ')}
          >
            {s.name}
          </button>
        ))}
      </div>
      <div className="p-4">
        {activeSignal?.viz_url ? (
          <img
            src={activeSignal.viz_url}
            alt={`${activeSignal.name} visualization`}
            className="mx-auto max-h-[420px] w-full rounded-lg object-contain bg-black"
          />
        ) : (
          <p className="text-sm text-slate-500">No visualization for this signal.</p>
        )}
        {activeSignal && (
          <ul className="mt-4 space-y-1">
            {activeSignal.findings.map((f) => (
              <li key={f} className="text-sm text-slate-400">
                • {f}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
