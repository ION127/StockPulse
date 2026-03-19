'use client'

import { useEffect, useState } from 'react'
import {
  ResponsiveContainer, ComposedChart, Line, Scatter,
  XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
} from 'recharts'
import { useStore } from '@/lib/store'
import { api } from '@/lib/api'
import type { Anomaly } from '@/types'
import { getCompanyName, hasCompanyName } from '@/lib/tickerNames'

interface ChartPoint {
  date: string
  return_pct: number
  isAnomaly: boolean
  direction: string
}

export default function StockChart() {
  const ticker = useStore((s) => s.selectedTicker)
  const [data, setData] = useState<ChartPoint[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!ticker) { setData([]); return }
    setLoading(true)
    api.getTickerHistory(ticker, 30)
      .then((history: Anomaly[]) => {
        const points = history.map((h) => ({
          date: h.anomaly_date,
          return_pct: h.return_pct,
          isAnomaly: true,
          direction: h.direction,
        }))
        setData(points)
      })
      .catch(() => setData([]))
      .finally(() => setLoading(false))
  }, [ticker])

  if (!ticker) {
    return (
      <div className="rounded-lg bg-gray-900 p-4 flex items-center justify-center h-48">
        <p className="text-xs text-gray-600">종목을 선택하세요</p>
      </div>
    )
  }

  return (
    <div className="rounded-lg bg-gray-900 p-4">
      <h2 className="text-sm font-semibold text-gray-300 mb-3">
        {hasCompanyName(ticker) ? (
          <>
            {getCompanyName(ticker)}
            <span className="ml-1.5 text-xs text-gray-500 font-mono font-normal">{ticker}</span>
          </>
        ) : ticker}
        {' '}— 이상값 이력 (30일)
      </h2>
      {loading ? (
        <div className="flex items-center justify-center h-40 text-xs text-gray-600">로딩 중...</div>
      ) : data.length === 0 ? (
        <div className="flex items-center justify-center h-40 text-xs text-gray-600">데이터 없음</div>
      ) : (
        <ResponsiveContainer width="100%" height={180}>
          <ComposedChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} />
            <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} unit="%" />
            <Tooltip
              contentStyle={{ background: '#111827', border: '1px solid #374151', fontSize: 12 }}
              formatter={(v: number) => [`${v > 0 ? '+' : ''}${v.toFixed(2)}%`, '변화율']}
            />
            <ReferenceLine y={0} stroke="#374151" />
            <Line
              type="monotone" dataKey="return_pct" stroke="#6366f1"
              dot={(props) => {
                const { cx, cy, payload } = props
                const isUp = payload.direction === '급등'
                return (
                  <circle
                    key={`dot-${payload.date}`}
                    cx={cx} cy={cy} r={4}
                    fill={isUp ? '#ef4444' : '#3b82f6'}
                    stroke="none"
                  />
                )
              }}
              strokeWidth={1.5}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
      <div className="flex gap-4 mt-2 text-[10px] text-gray-500">
        <span><span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" />급등</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-blue-500 mr-1" />급락</span>
      </div>
    </div>
  )
}
