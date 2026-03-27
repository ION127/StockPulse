import type { Anomaly, Analysis, SectorTrend, JobResponse, Candle, Prediction, ModelPerformance } from '@/types'

// SSR(서버): k8s 내부 DNS로 직접 접근
// CSR(브라우저): 상대 경로 → Ingress가 /api 를 api-service:8000으로 라우팅
const BASE = typeof window === 'undefined'
  ? 'http://api-service:8000'
  : ''

function getToken(): string | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem('stockpulse-auth')
    return raw ? JSON.parse(raw)?.state?.accessToken ?? null : null
  } catch {
    return null
  }
}

function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem('stockpulse-auth')
    return raw ? JSON.parse(raw)?.state?.refreshToken ?? null : null
  } catch {
    return null
  }
}

/** Access Token 만료 시 Refresh Token으로 재발급. 성공 시 true 반환. */
async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return false
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!res.ok) return false
    const { access_token, refresh_token } = await res.json()
    // 동적 임포트로 순환참조 방지
    const { useAuthStore } = await import('./authStore')
    useAuthStore.getState().setTokens(access_token, refresh_token)
    return true
  } catch {
    return false
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`)
  return res.json()
}

async function authFetch<T>(path: string, options: RequestInit = {}, _retry = true): Promise<T> {
  const token = getToken()
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })

  // Access Token 만료(401) → Refresh Token으로 재발급 후 1회 재시도
  if (res.status === 401 && _retry) {
    const refreshed = await tryRefreshToken()
    if (refreshed) return authFetch<T>(path, options, false)
    // 갱신 실패 → 로그아웃 처리
    const { useAuthStore } = await import('./authStore')
    useAuthStore.getState().logout()
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? `API error ${res.status}`)
  }
  if (res.status === 204) return undefined as T
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
    return get<Anomaly[]>(`/api/v1/anomalies/${encodeURIComponent(ticker)}/history?days=${days}`)
  },

  getAnalysis(anomalyId: number) {
    return get<Analysis>(`/api/v1/anomalies/${anomalyId}/analysis`)
  },

  getSectorTrends(days = 7) {
    return get<SectorTrend[]>(`/api/v1/sectors/trending?days=${days}`)
  },

  getCandles(ticker: string, days = 1) {
    return get<Candle[]>(`/api/v1/stocks/${encodeURIComponent(ticker)}/candles?days=${days}`)
  },

  triggerAnalysis() {
    return fetch(`${BASE}/api/v1/analyze/trigger`, { method: 'POST' }).then(r => r.json() as Promise<JobResponse>)
  },

  reanalyzeAnomalies(days = 7) {
    return fetch(`${BASE}/api/v1/analyze/reanalyze?days=${days}`, { method: 'POST' }).then(r => r.json() as Promise<JobResponse>)
  },

  getJobStatus(jobId: string) {
    return get<JobResponse>(`/api/v1/analyze/jobs/${jobId}`)
  },

  // ── 인증 ────────────────────────────────────────────────────────────
  register(email: string, password: string) {
    return authFetch<{ id: number; email: string; tier: string }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },

  login(email: string, password: string) {
    return authFetch<{ access_token: string; refresh_token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },

  getMe() {
    return authFetch<{ id: number; email: string; tier: string }>('/auth/me')
  },

  // ── 관심 종목 ────────────────────────────────────────────────────────
  getWatchlist() {
    return authFetch<{ id: number; ticker: string; added_at: string }[]>('/api/v1/users/watchlist')
  },

  addWatchlist(ticker: string) {
    return authFetch<{ id: number; ticker: string }>('/api/v1/users/watchlist', {
      method: 'POST',
      body: JSON.stringify({ ticker }),
    })
  },

  removeWatchlist(ticker: string) {
    return authFetch<void>(`/api/v1/users/watchlist/${ticker}`, { method: 'DELETE' })
  },

  // ── 포트폴리오 ───────────────────────────────────────────────────────
  getPortfolio() {
    return authFetch<{ id: number; ticker: string; quantity: number; avg_price: number }[]>('/api/v1/users/portfolio')
  },

  upsertPortfolio(ticker: string, quantity: number, avg_price: number) {
    return authFetch<{ id: number; ticker: string }>('/api/v1/users/portfolio', {
      method: 'POST',
      body: JSON.stringify({ ticker, quantity, avg_price }),
    })
  },

  removePortfolio(ticker: string) {
    return authFetch<void>(`/api/v1/users/portfolio/${ticker}`, { method: 'DELETE' })
  },

  // ── ML 예측 ──────────────────────────────────────────────────────────
  getPredictions(params?: { ticker?: string; days?: number }) {
    const q = new URLSearchParams()
    if (params?.ticker) q.set('ticker', params.ticker)
    if (params?.days) q.set('days', String(params.days))
    return get<Prediction[]>(`/api/v1/predictions?${q}`)
  },

  getLatestPrediction(ticker: string) {
    return get<Prediction>(`/api/v1/predictions/${encodeURIComponent(ticker)}/latest`)
  },

  getModelPerformance(ticker: string, days = 30) {
    return get<ModelPerformance[]>(`/api/v1/predictions/${encodeURIComponent(ticker)}/performance?days=${days}`)
  },

  triggerTrain(ticker: string) {
    return fetch(`${BASE}/api/v1/predictions/${encodeURIComponent(ticker)}/train`, { method: 'POST' })
      .then(r => r.json() as Promise<{ message: string; ticker: string }>)
  },
}
