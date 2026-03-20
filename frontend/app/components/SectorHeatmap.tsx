'use client'

import { useStore } from '@/lib/store'
import clsx from 'clsx'

// 섹터명을 짧게 표시
const SHORT: Record<string, string> = {
  '드론·방산 (Drone/Defense)': '방산',
  '에너지 (Energy)': '에너지',
  '철강 (Steel)': '철강',
  '반도체 (Semiconductor)': '반도체',
  '바이오·헬스케어 (Bio/Healthcare)': '바이오',
  '전기차 (EV)': '전기차',
  '빅테크 (Big Tech)': '빅테크',
  '금융 (Finance)': '금융',
  '원자재 (Materials)': '원자재',
}

function heatColor(count: number, max: number) {
  if (max === 0) return 'bg-gray-800'
  const ratio = count / max
  if (ratio >= 0.8) return 'bg-red-600'
  if (ratio >= 0.6) return 'bg-orange-500'
  if (ratio >= 0.4) return 'bg-yellow-500'
  if (ratio >= 0.2) return 'bg-green-600'
  return 'bg-gray-700'
}

export default function SectorHeatmap() {
  const trends = useStore((s) => s.sectorTrends)
  const setSelectedTicker = useStore((s) => s.setSelectedTicker)

  if (trends.length === 0) {
    return (
      <div className="rounded-lg bg-gray-900 p-4">
        <h2 className="text-sm font-semibold text-gray-300 mb-3">섹터 히트맵 (7일)</h2>
        <p className="text-xs text-gray-600">데이터 없음</p>
      </div>
    )
  }

  const max = Math.max(...trends.map((t) => t.anomaly_count))

  return (
    <div className="rounded-lg bg-gray-900 p-4">
      <h2 className="text-sm font-semibold text-gray-300 mb-3">섹터 히트맵 (7일)</h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {trends.map((t) => (
          <button
            key={t.sector}
            onClick={() => t.hot_tickers[0] && setSelectedTicker(t.hot_tickers[0])}
            className={clsx(
              'rounded p-2 text-left transition-opacity hover:opacity-80',
              heatColor(t.anomaly_count, max)
            )}
          >
            <div className="text-xs font-bold text-white truncate">
              {SHORT[t.sector] ?? t.sector}
            </div>
            <div className="text-[10px] text-white/70 mt-0.5">
              이상값 {t.anomaly_count}건
            </div>
            <div className="text-[10px] text-white/60">
              평균 {t.avg_return_pct > 0 ? '+' : ''}{t.avg_return_pct.toFixed(1)}%
            </div>
          </button>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-2 text-[10px] text-gray-500">
        <span>낮음</span>
        {['bg-gray-700','bg-green-600','bg-yellow-500','bg-orange-500','bg-red-600'].map((c) => (
          <span key={c} className={`h-2 w-4 rounded ${c}`} />
        ))}
        <span>높음</span>
      </div>
    </div>
  )
}
