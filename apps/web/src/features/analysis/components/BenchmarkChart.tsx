import { useEffect, useRef } from 'react'
import {
  CategoryScale,
  Chart,
  LinearScale,
  PointElement,
  ScatterController,
  Tooltip,
  type Plugin,
} from 'chart.js'
import benchmark from '../benchmark_summary.json'

Chart.register(ScatterController, PointElement, CategoryScale, LinearScale, Tooltip)

const samples = benchmark.results
  .map((result) => ({
    name: result.filename,
    label: result.filename.replace(/\.[^.]+$/, '').replaceAll('-', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()),
    score: result.ai_probability * 100,
    confidence: result.confidence * 100,
    runtime: result.analysis_ms,
  }))
  .sort((a, b) => b.score - a.score)

const runDate = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
}).format(new Date(benchmark.ran_at_utc))

const dotDetails: Plugin<'scatter'> = {
  id: 'benchmarkDotDetails',
  beforeDatasetsDraw(chart) {
    const { ctx, chartArea } = chart
    ctx.save()
    ctx.strokeStyle = '#263647'
    ctx.lineWidth = 1
    chart.getDatasetMeta(0).data.forEach((point) => {
      ctx.beginPath()
      ctx.moveTo(chartArea.left, point.y)
      ctx.lineTo(chartArea.right, point.y)
      ctx.stroke()
      ctx.beginPath()
      ctx.arc(point.x, point.y, 18, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(111, 221, 220, 0.13)'
      ctx.fill()
    })
    ctx.restore()
  },
  afterDatasetsDraw(chart) {
    const { ctx } = chart
    ctx.save()
    ctx.font = '700 15px system-ui, sans-serif'
    ctx.fillStyle = '#e5f7f7'
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    chart.getDatasetMeta(0).data.forEach((point, index) => {
      ctx.fillText(samples[index].score.toFixed(2), point.x - 24, point.y)
    })
    ctx.restore()
  },
}

function createChart(canvas: HTMLCanvasElement, responsive: boolean) {
  return new Chart(canvas, {
    type: 'scatter',
    data: {
      datasets: [{
        label: 'AI cue score',
        data: samples.map((sample) => ({ x: sample.score, y: sample.label })),
        pointRadius: 8,
        pointHoverRadius: 10,
        pointHitRadius: 14,
        pointBackgroundColor: '#8be0dc',
        pointHoverBackgroundColor: '#b0f2eb',
        pointBorderColor: '#123341',
        pointBorderWidth: 2,
      }],
    },
    plugins: [dotDetails],
    options: {
      responsive,
      maintainAspectRatio: false,
      animation: false,
      layout: { padding: { top: 12, right: 16, bottom: 2 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#e8f4f7',
          titleColor: '#0f2531',
          bodyColor: '#244250',
          borderColor: '#a8c6d1',
          borderWidth: 1,
          padding: 12,
          displayColors: false,
          callbacks: {
            title: (items) => samples[items[0].dataIndex].name,
            label: (item) => `AI cue score: ${samples[item.dataIndex].score.toFixed(2)} / 100`,
            afterLabel: (item) => `Internal confidence: ${samples[item.dataIndex].confidence.toFixed(2)}% · Runtime: ${samples[item.dataIndex].runtime} ms`,
          },
        },
      },
      scales: {
        x: {
          min: 0,
          max: 100,
          border: { display: false },
          grid: { color: '#304152', drawTicks: false },
          ticks: { color: '#91a8b8', stepSize: 25, padding: 10, font: { size: 11 } },
        },
        y: {
          type: 'category',
          labels: samples.map((sample) => sample.label),
          border: { display: false },
          grid: { display: false },
          ticks: { color: '#dce8ed', padding: 14, autoSkip: false, font: { size: 12, weight: 500 } },
        },
      },
    },
  })
}

function downloadChart() {
  const chartCanvas = document.createElement('canvas')
  chartCanvas.width = 1000
  chartCanvas.height = 310
  const chart = createChart(chartCanvas, false)

  const exportCanvas = document.createElement('canvas')
  exportCanvas.width = 1100
  exportCanvas.height = 610
  const ctx = exportCanvas.getContext('2d')
  if (!ctx) {
    chart.destroy()
    return
  }

  ctx.fillStyle = '#0b1220'
  ctx.fillRect(0, 0, 1100, 610)
  ctx.fillStyle = '#8be0dc'
  ctx.fillRect(48, 48, 8, 24)
  ctx.fillStyle = '#f0f7fa'
  ctx.font = '700 30px system-ui, sans-serif'
  ctx.fillText('Local fixture benchmark', 72, 71)
  ctx.fillStyle = '#aec1cc'
  ctx.font = '16px system-ui, sans-serif'
  ctx.fillText('Overall heuristic AI cue score · 0–100 · higher means more AI cues', 48, 106)
  ctx.font = '14px system-ui, sans-serif'
  ctx.fillText(`n=${samples.length} local fixtures · ${runDate} UTC · ${benchmark.analyzer_count} checks · weights v${benchmark.weights_version}`, 48, 134)
  ctx.fillStyle = '#122232'
  ctx.fillRect(48, 158, 1004, 322)
  ctx.drawImage(chartCanvas, 50, 164)
  ctx.fillStyle = '#304152'
  ctx.fillRect(48, 500, 1004, 1)
  ctx.fillStyle = '#dce8ed'
  ctx.font = '15px system-ui, sans-serif'
  ctx.fillText('Local regression fixtures only; no real-image controls or balanced evaluation.', 48, 532)
  ctx.fillStyle = '#aec1cc'
  ctx.fillText('Scores are heuristic outputs, not probabilities, accuracy, or public benchmark results.', 48, 558)
  ctx.fillStyle = '#7f98a8'
  ctx.font = '13px system-ui, sans-serif'
  ctx.fillText(`Source: scripts/run_local_benchmark.py · commit ${benchmark.git_sha.slice(0, 12)}`, 48, 586)

  const link = document.createElement('a')
  link.href = exportCanvas.toDataURL('image/png')
  link.download = `local-fixture-scores-${benchmark.ran_at_utc.slice(0, 10)}.png`
  document.body.append(link)
  link.click()
  link.remove()
  chart.destroy()
}

export function BenchmarkChart() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!canvasRef.current) return
    const chart = createChart(canvasRef.current, true)
    return () => chart.destroy()
  }, [])

  return (
    <section id="benchmark" aria-labelledby="benchmark-title" className="mt-8 scroll-mt-6 rounded-2xl border border-slate-800 bg-slate-900/50 p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-sky-300">Measured locally</p>
          <h2 id="benchmark-title" className="mt-1 text-xl font-semibold text-slate-100">Fixture benchmark</h2>
          <p className="mt-1 text-sm text-slate-400">Overall heuristic AI cue score · 0–100 · higher means more AI cues</p>
        </div>
        <button
          type="button"
          onClick={downloadChart}
          className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-sm font-medium text-slate-100 transition hover:border-sky-400 hover:bg-slate-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
        >
          Download PNG
        </button>
      </div>

      <p className="mt-4 text-xs text-slate-400">
        n={samples.length} local fixtures · {runDate} UTC · {benchmark.analyzer_count} checks · weights v{benchmark.weights_version}
      </p>

      <figure aria-labelledby="benchmark-title" aria-describedby="benchmark-note" className="mt-5">
        <div className="relative h-[270px] rounded-xl border border-slate-800 bg-slate-950/50 px-2 py-4 sm:h-[290px] sm:px-5">
          <canvas
            ref={canvasRef}
            role="img"
            aria-label={`Local fixture AI cue scores from 0 to 100: ${samples.map((sample) => `${sample.name} ${sample.score.toFixed(2)}`).join('; ')}`}
          />
        </div>
        <figcaption id="benchmark-note" className="mt-4 text-xs leading-relaxed text-slate-400">
          {samples.length} local regression fixtures, with no real-image controls. These scores are heuristic outputs, not probabilities, accuracy, or public benchmark results.
        </figcaption>
      </figure>

      <details className="mt-4 border-t border-slate-800 pt-4 text-sm text-slate-300">
        <summary className="cursor-pointer font-medium text-sky-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400">
          Exact values and method
        </summary>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[34rem] border-collapse text-left text-xs sm:text-sm">
            <caption className="sr-only">Recorded values from the local fixture check</caption>
            <thead className="border-b border-slate-700 text-slate-400">
              <tr>
                <th scope="col" className="pb-2 pr-4 font-medium">Fixture</th>
                <th scope="col" className="pb-2 pr-4 text-right font-medium">AI cue score</th>
                <th scope="col" className="pb-2 pr-4 text-right font-medium">Internal confidence</th>
                <th scope="col" className="pb-2 text-right font-medium">Runtime</th>
              </tr>
            </thead>
            <tbody>
              {samples.map((sample) => (
                <tr key={sample.name} className="border-b border-slate-800 last:border-b-0">
                  <th scope="row" className="py-2 pr-4 font-normal text-slate-200">{sample.name}</th>
                  <td className="py-2 pr-4 text-right tabular-nums">{sample.score.toFixed(2)} / 100</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{sample.confidence.toFixed(2)}%</td>
                  <td className="py-2 text-right tabular-nums">{sample.runtime} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-slate-400">
          Internal confidence is an ensemble diagnostic, not measured reliability. Runtime varies with hardware and image size. Values were recorded by scripts/run_local_benchmark.py at commit {benchmark.git_sha.slice(0, 12)}.{benchmark.low_code_sample_found ? ' One optional fixture was sourced from a sibling directory.' : ''}
        </p>
      </details>
    </section>
  )
}
