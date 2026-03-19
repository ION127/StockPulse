'use client'

import { useEffect, useState } from 'react'
import {
  ResponsiveContainer, ComposedChart, Line,
  XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
} from 'recharts'
import { useStore } from '@/lib/store'
import { api } from '@/lib/api'
import { getCompanyName, hasCompanyName } from '@/lib/tickerNames'
import type { Anomaly, Candle } from '@/types'

type Period = 1 | 3 | 5

interface ChartPoint {
  timestamp: string       // 차트 X축 표시용 (HH:MM 또는 MM/DD)
  fullTs: string          // 매칭용 전체 timestamp
  close: number
  open?: number
  high?: number
  low?: number
  isAnomaly: boolean
  direction?: string
  return_pct?: number
}

// ISO timestamp → "HH:MM" 또는 "MM/DD HH:MM" 포맷
function fmtTs(ts: string, days: number): string {
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return days > 1 ? `${mm}/${dd} ${hh}:${min}` : `${hh}:${min}`
}

// anomaly bar_timestamp와 candle timestamp를 분 단위로 비교
function sameMinute(a: string, b: string): boolean {
  return a.slice(0, 16).replace('T', ' ') === b.slice(0, 16).replace('T', ' ')
}

// 데이터가 많으면 샘플링 (recharts 성능)
function downsample(data: ChartPoint[], maxPoints = 800): ChartPoint[] {
  if (data.length <= maxPoints) return data
  const step = Math.ceil(data.length / maxPoints)
  return data.filter((_, i) => i % step === 0 || data[i]?.isAnomaly)
}

function AnomalyDot(props: any) {
  const { cx, cy, payload } = props
  if (!payload?.isAnomaly) return null
  const isUp = payload.direction === '급등'
  return (
    <circle
      key={`anomaly-${payload.fullTs}`}
      cx={cx} cy={cy} r={5}
      fill={isUp ? '#ef4444' : '#3b82f6'}
      stroke="#111827"
      strokeWidth={1.5}
    />
  )
}

function NormalDot() {
  return null
}

export default function StockChart() {
  const ticker           = useStore((s) => s.selectedTicker)
  const candles          = useStore((s) => s.candles)
  const setCandles       = useStore((s) => s.setCandles)
  const [period, setPeriod] = useState<Period>(1)
  const [anomalies, setAnomalies] = useState<Anomaly[]>([])
  const [loading, setLoading]     = useState(false)

  useEffect(() => {
    if (!ticker) return
    setLoading(true)

    Promise.all([
      candles[`${ticker}_${period}d`]
        ? Promise.resolve(candles[`${ticker}_${period}d`])
        : api.getCandles(ticker, period),
      api.getTickerHistory(ticker, 30).catch(() => []),
    ])
      .then(([candleData, anomalyData]) => {
        setCandles(`${ticker}_${period}d`, candleData)
        setAnomalies(anomalyData as Anomaly[])
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [ticker, period]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!ticker) {
    return (
      <div className="rounded-lg bg-gray-900 p-4 flex items-center justify-center h-48">
        <p className="text-xs text-gray-600">종목을 선택하거나 검색하세요</p>
      </div>
    )
  }

  const rawCandles: Candle[] = candles[`${ticker}_${period}d`] ?? []

  // 분봉 데이터 + 이상값 마커 병합
  const chartData: ChartPoint[] = downsample(
    rawCandles.map((c) => {
      const anomaly = anomalies.find((a) => sameMinute(a.bar_timestamp ?? '', c.timestamp))
      return {
        timestamp: fmtTs(c.timestamp, period),
        fullTs:    c.timestamp,
        close:     c.close,
        open:      c.open,
        high:      c.high,
        low:       c.low,
        isAnomaly:  !!anomaly,
        direction:  anomaly?.direction,
        return_pct: anomaly?.return_pct,
      }
    })
  )

  const companyName = hasCompanyName(ticker) ? getCompanyName(ticker) : ticker
  const anomalyCount = chartData.filter((d) => d.isAnomaly).length

  return (
    <div className="rounded-lg bg-gray-900 p-4">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-300">
          {companyName}
          {hasCompanyName(ticker) && (
            <span className="ml-1.5 text-xs text-gray-500 font-mono font-normal">{ticker}</span>
          )}
          {anomalyCount > 0 && (
            <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-red-900 text-red-300">
              이상값 {anomalyCount}건
            </span>
          )}
        </h2>
        {/* 기간 선택 */}
        <div className="flex rounded overflow-hidden border border-gray-700">
          {([1, 3, 5] as Period[]).map((d) => (
            <button
              key={d}
              onClick={() => setPeriod(d)}
              className={`px-2.5 py-1 text-[10px] font-medium transition-colors ${
                period === d ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              {d}D
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48 text-xs text-gray-600">
          로딩 중...
        </div>
      ) : chartData.length === 0 ? (
        <div className="flex items-center justify-center h-48 text-xs text-gray-600">
          데이터 없음 (장 마감 시간이거나 지원하지 않는 종목)
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis
              dataKey="timestamp"
              tick={{ fontSize: 9, fill: '#6b7280' }}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 9, fill: '#6b7280' }}
              domain={['auto', 'auto']}
              tickFormatter={(v) => v.toLocaleString()}
            />
            <Tooltip
              contentStyle={{ background: '#111827', border: '1px solid #374151', fontSize: 11 }}
              formatter={(v: number, _: string, item: any) => {
                const p = item?.payload
                if (p?.isAnomaly) {
                  const sign = (p.return_pct ?? 0) > 0 ? '+' : ''
                  return [`${v.toLocaleString()} (${p.direction} ${sign}${p.return_pct?.toFixed(2)}%)`, '종가']
                }
                return [v.toLocaleString(), '종가']
              }}
              labelFormatter={(label) => label}
            />
            <ReferenceLine y={chartData[0]?.close} stroke="#374151" strokeDasharray="4 4" />
            <Line
              type="monotone"
              dataKey="close"
              stroke="#6366f1"
              strokeWidth={1.5}
              dot={<AnomalyDot />}
              activeDot={{ r: 3, fill: '#6366f1' }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      <div className="flex gap-4 mt-2 text-[10px] text-gray-500">
        <span><span className="inline-block w-2 h-2 rounded-full bg-indigo-500 mr-1" />종가</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" />급등 이상값</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-blue-500 mr-1" />급락 이상값</span>
      </div>
    </div>
  )
}
