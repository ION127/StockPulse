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

        <main className="flex-1 p-4 grid gap-4" style={{ gridTemplateRows: 'auto 1fr auto' }}>
          {/* 상단 행: 섹터 히트맵 + 이상값 목록 + 관심종목/포트폴리오 */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" style={{ maxHeight: '320px' }}>
            <div className="lg:col-span-1 overflow-hidden">
              <SectorHeatmap />
            </div>
            <div className="lg:col-span-1 overflow-hidden">
              <AnomalyList />
            </div>
            <div className="lg:col-span-1 overflow-hidden">
              <PortfolioPanel />
            </div>
          </div>

          {/* 하단 행: 주가 차트 + AI 분석 패널 */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <StockChart />
            <div style={{ minHeight: '240px' }}>
              <AnalysisPanel />
            </div>
          </div>
        </main>
      </div>
    </WsProvider>
  )
}
