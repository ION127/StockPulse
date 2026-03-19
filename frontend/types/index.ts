export interface Anomaly {
  id: number
  ticker: string
  anomaly_date: string
  bar_timestamp: string | null
  return_pct: number
  zscore: number | null
  close_price: number | null
  volume: number | null
  direction: string
  event_type: 'INDIVIDUAL' | 'SECTOR' | 'MARKET'
  sector: string | null
  sector_peer_count: number | null
  moving_sector_count: number | null
  detected_at: string
  has_analysis: boolean
}

export interface Analysis {
  id: number
  anomaly_id: number
  analysis_ko: string | null
  analysis_en: string | null
  news_en: NewsArticle[]
  news_kr: NewsArticle[]
  created_at: string
}

export interface NewsArticle {
  title: string
  url: string
  source: string
  published_at: string
}

export interface SectorTrend {
  sector: string
  anomaly_count: number
  avg_return_pct: number
  up_count: number
  down_count: number
  hot_tickers: string[]
}

export interface WsAnomalyMessage {
  type: 'anomaly'
  ticker: string
  return_pct: number
  direction: string
  sector: string
  event_type: string
}

export interface Candle {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface JobResponse {
  job_id: string
  status: 'queued' | 'running' | 'done' | 'failed'
  started_at: string | null
  completed_at: string | null
  anomaly_count: number | null
  message: string | null
}
