import type { Anomaly, Analysis, SectorTrend, JobResponse } from '@/types'

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`)
  return res.json()
}

export const api = {
  getAnomalies(params?: { days?: number; sector?: string; event_type?: string; limit?: number }) {
    const q = new URLSearchParams()
    if (params?.days) q.set('days', String(params.days))
    if (params?.sector) q.set('sector', params.sector)
    if (params?.event_type) q.set('event_type', params.event_type)
    if (params?.limit) q.set('limit', String(params.limit))
    return get<Anomaly[]>(`/api/v1/anomalies?${q}`)
  },

  getTickerHistory(ticker: string, days = 30) {
    return get<Anomaly[]>(`/api/v1/anomalies/${ticker}/history?days=${days}`)
  },

  getAnalysis(anomalyId: number) {
    return get<Analysis>(`/api/v1/anomalies/${anomalyId}/analysis`)
  },

  getSectorTrends(days = 7) {
    return get<SectorTrend[]>(`/api/v1/sectors/trending?days=${days}`)
  },

  triggerAnalysis() {
    return fetch(`${BASE}/api/v1/analyze/trigger`, { method: 'POST' }).then(r => r.json() as Promise<JobResponse>)
  },

  getJobStatus(jobId: string) {
    return get<JobResponse>(`/api/v1/analyze/jobs/${jobId}`)
  },
}
