'use client'

import { useStore } from '@/lib/store'
import clsx from 'clsx'
import type { Anomaly } from '@/types'
import { getCompanyName, hasCompanyName } from '@/lib/tickerNames'

const EVENT_LABEL: Record<string, string> = {
  INDIVIDUAL: '개별',
  SECTOR: '섹터',
  MARKET: '시장',
}

const EVENT_COLOR: Record<string, string> = {
  INDIVIDUAL: 'bg-gray-700 text-gray-300',
  SECTOR: 'bg-indigo-900 text-indigo-300',
  MARKET: 'bg-purple-900 text-purple-300',
}

function AnomalyRow({ anomaly, onClick }: { anomaly: Anomaly; onClick: () => void }) {
  const isUp = anomaly.return_pct > 0
  return (
    <button
      onClick={onClick}
      className="w-full text-left px-3 py-2.5 hover:bg-gray-800 rounded transition-colors border border-transparent hover:border-gray-700"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono font-bold text-sm text-white shrink-0">
            {hasCompanyName(anomaly.ticker) ? getCompanyName(anomaly.ticker) : anomaly.ticker}
          </span>
          {hasCompanyName(anomaly.ticker) && (
            <span className="text-[10px] text-gray-500 font-mono shrink-0">{anomaly.ticker}</span>
          )}
          <span className={clsx('text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0', EVENT_COLOR[anomaly.event_type])}>
            {EVENT_LABEL[anomaly.event_type] ?? anomaly.event_type}
          </span>
          {anomaly.sector && (
            <span className="text-[10px] text-gray-500 truncate">{anomaly.sector.split('(')[0].trim()}</span>
          )}
        </div>
        <span className={clsx('font-bold text-sm shrink-0', isUp ? 'text-red-400' : 'text-blue-400')}>
          {isUp ? '+' : ''}{anomaly.return_pct.toFixed(2)}%
        </span>
      </div>
      <div className="mt-0.5 text-[10px] text-gray-600">
        {anomaly.anomaly_date}
        {anomaly.close_price && ` · $${anomaly.close_price.toLocaleString()}`}
      </div>
    </button>
  )
}

export default function AnomalyList() {
  const anomalies = useStore((s) => s.anomalies)
  const setSelectedTicker = useStore((s) => s.setSelectedTicker)
  const setSelectedAnomalyId = useStore((s) => s.setSelectedAnomalyId)

  function handleClick(a: Anomaly) {
    setSelectedTicker(a.ticker)
    if (a.analysis_id) setSelectedAnomalyId(a.analysis_id)
  }

  return (
    <div className="rounded-lg bg-gray-900 p-4 flex flex-col h-full">
      <h2 className="text-sm font-semibold text-gray-300 mb-2 shrink-0">
        이상값 목록
        <span className="ml-2 text-xs text-gray-600">({anomalies.length}건)</span>
      </h2>
      <div className="overflow-y-auto scrollbar-thin flex-1 space-y-0.5 pr-1">
        {anomalies.length === 0 ? (
          <p className="text-xs text-gray-600 py-4 text-center">이상값 없음</p>
        ) : (
          anomalies.map((a) => (
            <AnomalyRow key={`${a.id}-${a.ticker}`} anomaly={a} onClick={() => handleClick(a)} />
          ))
        )}
      </div>
    </div>
  )
}
