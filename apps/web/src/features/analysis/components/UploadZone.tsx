import { useCallback, useState } from 'react'

export function UploadZone({
  onFile,
  disabled,
}: {
  onFile: (f: File) => void
  disabled?: boolean
}) {
  const [drag, setDrag] = useState(false)

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDrag(false)
      if (disabled) return
      const f = e.dataTransfer.files?.[0]
      if (f) onFile(f)
    },
    [disabled, onFile],
  )

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setDrag(true)
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={onDrop}
      aria-disabled={disabled}
      className={[
        'group relative flex cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed px-6 py-14 transition',
        drag
          ? 'border-sky-400/70 bg-sky-500/10'
          : 'border-slate-700/80 bg-slate-900/40 hover:border-slate-500 hover:bg-slate-900/70',
        disabled ? 'pointer-events-none opacity-60' : '',
      ].join(' ')}
    >
      <input
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif,image/*"
        className="hidden"
        disabled={disabled}
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onFile(f)
          e.target.value = ''
        }}
      />
      <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-xl bg-slate-800 text-2xl text-sky-300 shadow-lg shadow-sky-900/20">
        ⌕
      </div>
      <div className="text-lg font-medium text-slate-100">
        {disabled ? 'Analyzing…' : 'Drop an image to authenticate'}
      </div>
      <p className="mt-2 max-w-md text-center text-sm text-slate-400">
        PNG, JPEG, WebP, GIF. Runs a local multi-signal forensic ensemble — no cloud upload.
      </p>
      <span className="mt-5 rounded-full border border-slate-600 bg-slate-800/80 px-4 py-1.5 text-sm text-slate-200">
        {disabled ? 'Please wait' : 'Choose file'}
      </span>
    </label>
  )
}
