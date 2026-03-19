import { create } from 'zustand'
import type { Anomaly, SectorTrend, Analysis, Candle } from '@/types'

interface StoreState {
  // 이상값 목록
  anomalies: Anomaly[]
  setAnomalies: (a: Anomaly[]) => void
  prependAnomaly: (a: Anomaly) => void

  // 선택된 종목
  selectedTicker: string | null
  setSelectedTicker: (t: string | null) => void

  // 선택된 이상값 ID (분석 조회용)
  selectedAnomalyId: number | null
  setSelectedAnomalyId: (id: number | null) => void

  // 분석 결과 캐시 {anomalyId: Analysis}
  analyses: Record<number, Analysis>
  setAnalysis: (id: number, a: Analysis) => void

  // 섹터 트렌드
  sectorTrends: SectorTrend[]
  setSectorTrends: (s: SectorTrend[]) => void

  // 분봉 데이터 캐시 {ticker: Candle[]}
  candles: Record<string, Candle[]>
  setCandles: (ticker: string, data: Candle[]) => void

  // WebSocket 연결 상태
  wsConnected: boolean
  setWsConnected: (v: boolean) => void

  // 분석 언어 탭
  analysisLang: 'ko' | 'en'
  setAnalysisLang: (l: 'ko' | 'en') => void

  // 분석 실행 중인 Job ID
  runningJobId: string | null
  setRunningJobId: (id: string | null) => void
}

export const useStore = create<StoreState>((set) => ({
  anomalies: [],
  setAnomalies: (anomalies) => set({ anomalies }),
  prependAnomaly: (a) =>
    set((s) => ({ anomalies: [a, ...s.anomalies].slice(0, 100) })),

  selectedTicker: null,
  setSelectedTicker: (selectedTicker) => set({ selectedTicker }),

  selectedAnomalyId: null,
  setSelectedAnomalyId: (selectedAnomalyId) => set({ selectedAnomalyId }),

  analyses: {},
  setAnalysis: (id, a) => set((s) => ({ analyses: { ...s.analyses, [id]: a } })),

  sectorTrends: [],
  setSectorTrends: (sectorTrends) => set({ sectorTrends }),

  candles: {},
  setCandles: (ticker, data) => set((s) => ({ candles: { ...s.candles, [ticker]: data } })),

  wsConnected: false,
  setWsConnected: (wsConnected) => set({ wsConnected }),

  analysisLang: 'ko',
  setAnalysisLang: (analysisLang) => set({ analysisLang }),

  runningJobId: null,
  setRunningJobId: (runningJobId) => set({ runningJobId }),
}))
