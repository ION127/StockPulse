'use client'

import { useEffect } from 'react'
import { useStore } from '@/lib/store'
import type { Anomaly, SectorTrend } from '@/types'

import WsProvider from './components/WsProvider'
import Header from './components/Header'
import SectorHeatmap from './components/SectorHeatmap'
import AnomalyList from './components/AnomalyList'
import StockChart from './components/StockChart'
import AnalysisPanel from './components/AnalysisPanel'
import PortfolioPanel from './components/PortfolioPanel'
import PredictionPanel from './components/PredictionPanel'

interface Props {
  initialAnomalies: Anomaly[]
  initialSectorTrends: SectorTrend[]
  lastUpdated: string
}

function Initializer({ anomalies, trends }: { anomalies: Anomaly[]; trends: SectorTrend[] }) {
  const setAnomalies = useStore((s) => s.setAnomalies)
  const setSectorTrends = useStore((s) => s.setSectorTrends)

  useEffect(() => {
    setAnomalies(anomalies)
    setSectorTrends(trends)
  }, [anomalies, trends, setAnomalies, setSectorTrends])

  return null
}

export default function DashboardClient({ initialAnomalies, initialSectorTrends, lastUpdated }: Props) {
  return (
    <WsProvider>
      <Initializer anomalies={initialAnomalies} trends={initialSectorTrends} />
      <div className="min-h-screen flex flex-col bg-gray-950">
        <Header lastUpdated={lastUpdated} />

        <main className="flex-1 p-3 md:p-4 flex flex-col gap-4">
          {/* 상단 행: 섹터 히트맵 + 이상값 목록 + 관심종목/포트폴리오 */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* 섹터 히트맵: 자연 높이 */}
            <SectorHeatmap />
            {/* 이상값 목록: 내부 h-full을 위해 명시적 높이 지정 */}
            <div className="h-72 lg:h-80">
              <AnomalyList />
            </div>
            {/* 관심 종목 / 포트폴리오: 내부 h-full을 위해 명시적 높이 지정 */}
            <div className="h-72 lg:h-80">
              <PortfolioPanel />
            </div>
          </div>

          {/* 하단 행: 주가 차트 + AI 분석 + ML 예측 */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="md:col-span-1">
              <StockChart />
            </div>
            <div className="min-h-[240px]">
              <AnalysisPanel />
            </div>
            <div className="min-h-[240px]">
              <PredictionPanel />
            </div>
          </div>
        </main>
      </div>
    </WsProvider>
  )
}
