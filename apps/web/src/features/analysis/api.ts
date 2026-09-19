import type { AnalysisResult } from './types'

const API_BASE = ''

function formatDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg)
        }
        return null
      })
      .filter(Boolean)
    if (parts.length) return parts.join('; ')
  }
  return fallback
}

export async function analyzeImage(file: File): Promise<AnalysisResult> {
  let res: Response
  try {
    const form = new FormData()
    form.append('file', file)
    res = await fetch(`${API_BASE}/api/v1/analyze`, {
      method: 'POST',
      body: form,
    })
  } catch {
    throw new Error('Network error — is the API running on :8000?')
  }

  if (!res.ok) {
    let detail = `Analysis failed (HTTP ${res.status})`
    try {
      const body = await res.json()
      detail = formatDetail(body.detail, detail)
      if (body.request_id) {
        detail = `${detail} (request ${body.request_id})`
      }
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new Error(detail)
  }
  return res.json()
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/health`)
    return res.ok
  } catch {
    return false
  }
}
