export function ScoreBar({ score, color }: { score: number; color: string }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
      <div
        className="h-full rounded-full transition-all duration-700"
        style={{ width: `${Math.round(score * 100)}%`, background: color }}
      />
    </div>
  )
}
