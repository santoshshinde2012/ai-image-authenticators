import type { SignalResult } from '../types'
import { ScoreBar } from './ScoreBar'

export function SignalCard({
  signal,
  active,
  onSelect,
}: {
  signal: SignalResult
  active: boolean
  onSelect: () => void
}) {
  const color =
    signal.score >= 0.75 ? '#f87171' : signal.score >= 0.55 ? '#fb923c' : signal.score >= 0.35 ? '#fbbf24' : '#34d399'
  return (
    <button
      type="button"
      onClick={onSelect}
      className={[
        'w-full rounded-xl border p-4 text-left transition',
        active ? 'border-sky-400/50 bg-slate-800/80' : 'border-slate-800 bg-slate-900/50 hover:border-slate-600',
      ].join(' ')}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <div>
          <div className="font-medium text-slate-100">{signal.name}</div>
          <div className="text-xs text-slate-500">
            weight {signal.weight.toFixed(2)} · conf {(signal.confidence * 100).toFixed(0)}%
          </div>
        </div>
        <div className="text-lg font-semibold tabular-nums" style={{ color }}>
          {(signal.score * 100).toFixed(0)}
        </div>
      </div>
      <ScoreBar score={signal.score} color={color} />
      <ul className="mt-3 space-y-1">
        {signal.findings.slice(0, 2).map((f) => (
          <li key={f} className="text-xs leading-relaxed text-slate-400">
            • {f}
          </li>
        ))}
      </ul>
    </button>
  )
}
