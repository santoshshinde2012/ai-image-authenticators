import { useEffect, useMemo, useRef, useState } from 'react'
import { analyzeImage, checkHealth } from '../features/analysis/api'
import { SignalCard, UploadZone, VerdictPanel, VizGallery } from '../features/analysis/components'
import type { AnalysisResult } from '../features/analysis/types'

export default function App() {
  const [apiOk, setApiOk] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [activeViz, setActiveViz] = useState<string | null>(null)
  const inFlight = useRef(false)

  useEffect(() => {
    checkHealth().then(setApiOk)
  }, [])

  const vizSignals = useMemo(() => result?.signals.filter((s) => s.viz_url) ?? [], [result])
  const activeSignal = result?.signals.find((s) => s.id === activeViz)

  const onFile = async (file: File) => {
    if (inFlight.current || loading) return
    inFlight.current = true
    setError(null)
    setResult(null)
    setActiveViz(null)
    const url = URL.createObjectURL(file)
    setPreview(url)
    setLoading(true)
    try {
      const res = await analyzeImage(file)
      setResult(res)
      const firstViz = res.signals.find((s) => s.viz_url)
      setActiveViz(firstViz?.id ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed')
    } finally {
      setLoading(false)
      inFlight.current = false
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-slate-700/80 bg-slate-900/70 px-3 py-1 text-xs text-slate-300">
            <span className={apiOk ? 'text-emerald-400' : apiOk === false ? 'text-rose-400' : 'text-slate-500'}>●</span>
            {apiOk === null ? 'Checking API…' : apiOk ? 'API online' : 'API offline — start backend on :8000'}
          </div>
          <h1 className="font-display text-3xl font-semibold text-white sm:text-4xl">AI Image Authenticator</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-400 sm:text-base">
            Explainable forensic ensemble — metadata, Content Credentials (C2PA), visible AI labels (OCR), ELA,
            FFT, DCT, noise, texture, and screenshot heuristics.
          </p>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-12">
        <section className="space-y-6 lg:col-span-5">
          <UploadZone onFile={onFile} disabled={loading} />

          {preview && (
            <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-950/60">
              <div className="border-b border-slate-800 px-4 py-2 text-xs uppercase tracking-wider text-slate-500">
                Source preview
              </div>
              <img src={preview} alt="Upload preview" className="max-h-80 w-full object-contain bg-black/40" />
            </div>
          )}

          {loading && (
            <div className="rounded-2xl border border-sky-500/20 bg-sky-500/5 px-5 py-4 text-sm text-sky-100" role="status">
              <div className="mb-2 flex items-center gap-2 font-medium">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-sky-400" />
                Running forensic ensemble…
              </div>
              <p className="text-sky-200/70">Metadata → Provenance (C2PA) → Labels → ELA → FFT → DCT → Noise → Texture → Screenshot</p>
            </div>
          )}

          {error && (
            <div
              className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-5 py-4 text-sm text-rose-100"
              role="alert"
            >
              <div className="mb-1 font-medium text-rose-50">Analysis failed</div>
              <p className="text-rose-100/90">{error}</p>
              <p className="mt-2 text-xs text-rose-200/60">
                Try a JPEG/PNG/WebP/GIF under the size limit, or check that the API is healthy.
              </p>
            </div>
          )}

          {apiOk === false && !error && (
            <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-5 py-4 text-sm text-amber-100">
              Backend unreachable. Start the API (`uv run uvicorn …`) or use Docker Compose, then refresh.
            </div>
          )}
        </section>

        <section className="space-y-6 lg:col-span-7">
          {!result && !loading && (
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-8 text-slate-400">
              <h2 className="mb-2 text-lg font-medium text-slate-200">Results dashboard</h2>
              <p className="text-sm leading-relaxed">
                Upload an image to see a calibrated verdict, per-signal scores, and forensic visualizations (ELA map,
                FFT spectrum, noise residual).
              </p>
              <ul className="mt-4 list-disc space-y-1 pl-5 text-sm">
                <li>Nine-signal classical ensemble (offline, no model download required)</li>
                <li>C2PA / Content Credentials when manifests remain; OCR for visible Made-with-AI badges</li>
                <li>Screenshot detection softens overconfident “real camera” claims</li>
              </ul>
            </div>
          )}

          {result && (
            <>
              <VerdictPanel result={result} />
              <div className="grid gap-3 sm:grid-cols-2">
                {result.signals.map((s) => (
                  <SignalCard
                    key={s.id}
                    signal={s}
                    active={activeViz === s.id}
                    onSelect={() => setActiveViz(s.id)}
                  />
                ))}
              </div>
              <VizGallery
                vizSignals={vizSignals}
                activeViz={activeViz}
                activeSignal={activeSignal}
                onSelect={setActiveViz}
              />
              <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-5">
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-amber-200/90">
                  Limitations & disclaimer
                </h3>
                <ul className="space-y-1.5">
                  {result.limitations.map((l) => (
                    <li key={l} className="text-sm text-amber-100/70">
                      • {l}
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </section>
      </div>

      <footer className="mt-12 border-t border-slate-800/80 pt-6 text-center text-xs text-slate-600">
        Local forensic tool · classical ensemble v1 · SOLID layout · optional ML models documented as Phase 2
      </footer>
    </div>
  )
}
