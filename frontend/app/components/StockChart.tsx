'use client'

import { useEffect, useState } from 'react'
import {
  ResponsiveContainer, ComposedChart, Line, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
} from 'recharts'
import { useStore } from '@/lib/store'
import { api } from '@/lib/api'
import { getCompanyName, hasCompanyName } from '@/lib/tickerNames'
import type { Anomaly, Candle } from '@/types'
import clsx from 'clsx'

type ChartType = 'line' | 'candle'
type Timeframe  = 'minute' | 'daily'

interface ChartPoint {
  timestamp:       string
  fullTs:          string
  close:           number
  open:            number
  high:            number
  low:             number
  shadow:          [number, number]   // [low, high] — recharts range bar
  isUp:            boolean
  isAnomaly:       boolean
  direction?:      string
  return_pct?:     number
  post_return_pct?: number   // 감지 시점 이후 현재까지 변화율
  held?:           boolean   // 급등/급락 방향이 현재까지 유지되는지
}

// ── 포맷 헬퍼 ────────────────────────────────────────────────────────────

function fmtTs(ts: string, isMinute: boolean): string {
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts
  const mm  = String(d.getMonth() + 1).padStart(2, '0')
  const dd  = String(d.getDate()).padStart(2, '0')
  const hh  = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return isMinute ? `${hh}:${min}` : `${mm}/${dd}`
}

/** 이상값의 날짜 추출 (bar_timestamp 또는 anomaly_date) */
function anomalyDate(a: Anomaly): string {
  return (a.bar_timestamp ?? a.anomaly_date ?? '').slice(0, 10)
}

/** bar_timestamp가 분 단위 실제 시각인지 (일봉 감지는 자정 00:00) */
function isMinuteLevelTs(bt: string | null | undefined): boolean {
  if (!bt) return false
  const time = bt.slice(11, 16)       // "HH:MM"
  return time !== '' && time !== '00:00'
}

/**
 * 이상값 마커 색상 결정
 * - 급등 + 상승 유지 → 빨강   (#ef4444)
 * - 급등 + 상승 소멸 → 주황   (#f97316)  ← 올랐다가 다시 하락
 * - 급락 + 하락 유지 → 파랑   (#3b82f6)
 * - 급락 + 하락 소멸 → 청록   (#06b6d4)  ← 내렸다가 반등
 * held = undefined (최신 캔들) 이면 방향 색상만 유지
 */
function anomalyColor(direction: string | undefined, held: boolean | undefined): string {
  if (direction === '급등') return held === false ? '#f97316' : '#ef4444'
  return held === false ? '#06b6d4' : '#3b82f6'
}

function downsample(data: ChartPoint[], maxPoints = 600): ChartPoint[] {
  if (data.length <= maxPoints) return data
  const step = Math.ceil(data.length / maxPoints)
  return data.filter((_, i) => i % step === 0 || data[i]?.isAnomaly)
}

// ── 선차트: 이상값 점 ─────────────────────────────────────────────────────

function AnomalyDot(props: any) {
  const { cx, cy, payload } = props
  if (!payload?.isAnomaly) return null
  const color = anomalyColor(payload.direction, payload.held)
  return (
    <circle
      key={`anomaly-${payload.fullTs}`}
      cx={cx} cy={cy} r={5}
      fill={color}
      stroke="#111827" strokeWidth={1.5}
    />
  )
}

// ── 봉차트: 단일 캔들스틱 shape ──────────────────────────────────────────

function CandlestickShape(props: any) {
  const { x, y, width, height, payload } = props
  if (!payload || height <= 0) return null

  const { open, close, high, low, isAnomaly, direction, held } = payload
  if (open == null || close == null || high == null || low == null) return null

  const range = high - low
  const isUp  = close >= open
  const color = isUp ? '#10b981' : '#ef4444'
  const cx    = x + width / 2

  let bodyTop: number
  let bodyH:   number

  if (range === 0) {
    bodyTop = y
    bodyH   = 1
  } else {
    const openY  = y + (high - open)  / range * height
    const closeY = y + (high - close) / range * height
    bodyTop = Math.min(openY, closeY)
    bodyH   = Math.max(Math.abs(openY - closeY), 1)
  }

  const bw = Math.max(width - 2, 3)

  return (
    <g>
      {/* 심지 */}
      <line x1={cx} y1={y} x2={cx} y2={y + height} stroke={color} strokeWidth={1} />
      {/* 몸통 */}
      <rect x={cx - bw / 2} y={bodyTop} width={bw} height={bodyH} fill={color} />
      {/* 이상값 마커 */}
      {isAnomaly && (
        <circle
          cx={cx}
          cy={bodyTop - 6}
          r={4}
          fill={anomalyColor(direction, held)}
          stroke="#111827"
          strokeWidth={1.5}
        />
      )}
    </g>
  )
}

// ── 툴팁 이상값 문자열 ─────────────────────────────────────────────────────

function fmtAnomalyLine(p: ChartPoint): string {
  const detSign = (p.return_pct ?? 0) >= 0 ? '+' : ''
  let s = `[이상값] ${p.direction} 감지: ${detSign}${p.return_pct?.toFixed(2) ?? '?'}%`

  if (p.post_return_pct != null) {
    const postSign = p.post_return_pct >= 0 ? '+' : ''
    const outcome  = p.held ? '방향 유지' : '방향 소멸'
    s += `  /  감지 후: ${postSign}${p.post_return_pct.toFixed(2)}% (${outcome})`
  }
  return s
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────

const DAILY_PERIODS = [
  { label: '5일',   value: 5  },
  { label: '1개월', value: 20 },
  { label: '3개월', value: 60 },
]

export default function StockChart() {
  const ticker     = useStore((s) => s.selectedTicker)
  const candles    = useStore((s) => s.candles)
  const setCandles = useStore((s) => s.setCandles)

  const [chartType, setChartType] = useState<ChartType>('line')
  const [timeframe, setTimeframe] = useState<Timeframe>('minute')
  const [period, setPeriod]       = useState<number>(1)
  const [anomalies, setAnomalies] = useState<Anomaly[]>([])
  const [loading, setLoading]     = useState(false)

  // 타임프레임 변경 시 기간 초기화
  useEffect(() => {
    setPeriod(timeframe === 'minute' ? 1 : 5)
  }, [timeframe])

  useEffect(() => {
    if (!ticker) return
    setLoading(true)
    const cacheKey = `${ticker}_${period}d`

    Promise.all([
      candles[cacheKey]
        ? Promise.resolve(candles[cacheKey])
        : api.getCandles(ticker, period),
      api.getTickerHistory(ticker, Math.max(30, period * 2)).catch(() => []),
    ])
      .then(([candleData, anomalyData]) => {
        setCandles(cacheKey, candleData)
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
  const isMinute  = timeframe === 'minute'
  const lastClose = rawCandles[rawCandles.length - 1]?.close ?? 0

  // 분봉 차트에서 일봉 이상값을 해당 날짜의 마지막 캔들(종가)에 표시하기 위해
  // 날짜별 마지막 캔들 타임스탬프를 미리 계산
  const lastTsOfDate = new Map<string, string>()
  for (const c of rawCandles) {
    lastTsOfDate.set(c.timestamp.slice(0, 10), c.timestamp)
  }

  const chartData: ChartPoint[] = downsample(
    rawCandles.map((c) => {
      const cDate = c.timestamp.slice(0, 10)
      const cNorm = c.timestamp.slice(0, 16).replace('T', ' ')

      const anomaly = anomalies.find((a) => {
        const aDate = anomalyDate(a)
        if (isMinute) {
          if (isMinuteLevelTs(a.bar_timestamp)) {
            // 분 단위 이상값: 정확한 분 비교
            return a.bar_timestamp!.slice(0, 16).replace('T', ' ') === cNorm
          } else {
            // 일봉 이상값: 해당 날짜의 마지막 캔들(종가봉)에 표시
            return aDate !== '' && aDate === cDate && lastTsOfDate.get(cDate) === c.timestamp
          }
        } else {
          // 일봉 차트: 날짜만 비교
          return aDate !== '' && aDate === cDate
        }
      })

      const open  = c.open  ?? c.close
      const high  = c.high  ?? c.close
      const low   = c.low   ?? c.close

      // 감지 이후 현재까지 변화율 (최신 캔들은 판단 보류)
      const isLastCandle = c.timestamp === rawCandles[rawCandles.length - 1]?.timestamp
      const post_return_pct =
        anomaly && !isLastCandle && c.close && lastClose
          ? (lastClose - c.close) / c.close * 100
          : undefined

      // 급등 → 상승 유지 여부 / 급락 → 하락 유지 여부
      const held =
        post_return_pct !== undefined
          ? anomaly!.direction === '급등'
            ? post_return_pct >= 0
            : post_return_pct <= 0
          : undefined

      return {
        timestamp:       fmtTs(c.timestamp, isMinute),
        fullTs:          c.timestamp,
        close:           c.close,
        open,
        high,
        low,
        shadow:          [low, high] as [number, number],
        isUp:            c.close >= open,
        isAnomaly:       !!anomaly,
        direction:       anomaly?.direction,
        return_pct:      anomaly?.return_pct,
        post_return_pct,
        held,
      }
    })
  )

  const companyName  = hasCompanyName(ticker) ? getCompanyName(ticker) : ticker
  const anomalyCount = chartData.filter((d) => d.isAnomaly).length

  return (
    <div className="rounded-lg bg-gray-900 p-4">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <h2 className="text-sm font-semibold text-gray-300 shrink-0">
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

        <div className="flex items-center gap-1.5 flex-wrap">
          {/* 선 / 봉 */}
          <div className="flex rounded overflow-hidden border border-gray-700">
            {(['line', 'candle'] as ChartType[]).map((t) => (
              <button
                key={t}
                onClick={() => setChartType(t)}
                className={clsx(
                  'px-2.5 py-1 text-[10px] font-medium transition-colors',
                  chartType === t ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
                )}
              >
                {t === 'line' ? '선' : '봉'}
              </button>
            ))}
          </div>

          {/* 분봉 / 일봉 */}
          <div className="flex rounded overflow-hidden border border-gray-700">
            {(['minute', 'daily'] as Timeframe[]).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={clsx(
                  'px-2.5 py-1 text-[10px] font-medium transition-colors',
                  timeframe === tf ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
                )}
              >
                {tf === 'minute' ? '분봉' : '일봉'}
              </button>
            ))}
          </div>

          {/* 기간 (일봉만) */}
          {timeframe === 'daily' && (
            <div className="flex rounded overflow-hidden border border-gray-700">
              {DAILY_PERIODS.map(({ label, value }) => (
                <button
                  key={value}
                  onClick={() => setPeriod(value)}
                  className={clsx(
                    'px-2.5 py-1 text-[10px] font-medium transition-colors',
                    period === value ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 차트 */}
      {loading ? (
        <div className="flex items-center justify-center h-48 text-xs text-gray-600">로딩 중...</div>
      ) : chartData.length === 0 ? (
        <div className="flex items-center justify-center h-48 text-xs text-gray-600">
          데이터 없음 (장 마감 또는 지원하지 않는 종목)
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart
            data={chartData}
            margin={{ top: 5, right: 10, left: -20, bottom: 5 }}
            barCategoryGap={chartType === 'candle' ? '20%' : '0%'}
          >
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
              contentStyle={{ background: '#111827', border: '1px solid #374151', fontSize: 11, color: '#e5e7eb' }}
              labelStyle={{ color: '#9ca3af' }}
              itemStyle={{ color: '#e5e7eb' }}
              formatter={(v: any, name: string, item: any) => {
                const p: ChartPoint = item?.payload
                if (name === 'close') {
                  if (p?.isAnomaly) {
                    return [`${Number(v).toLocaleString()}  ${fmtAnomalyLine(p)}`, '종가']
                  }
                  return [Number(v).toLocaleString(), '종가']
                }
                if (name === 'shadow') {
                  const ohlc = `고: ${p?.high?.toLocaleString()}  저: ${p?.low?.toLocaleString()}  시: ${p?.open?.toLocaleString()}  종: ${p?.close?.toLocaleString()}`
                  const anomalyNote = p?.isAnomaly ? `  |  ${fmtAnomalyLine(p)}` : ''
                  return [`${ohlc}${anomalyNote}`, '']
                }
                return [v, name]
              }}
              labelFormatter={(label) => label}
            />
            <ReferenceLine y={chartData[0]?.close} stroke="#374151" strokeDasharray="4 4" />

            {chartType === 'line' ? (
              <Line
                type="monotone"
                dataKey="close"
                stroke="#6366f1"
                strokeWidth={1.5}
                dot={<AnomalyDot />}
                activeDot={{ r: 3, fill: '#6366f1' }}
                isAnimationActive={false}
              />
            ) : (
              <Bar
                dataKey="shadow"
                shape={<CandlestickShape />}
                isAnimationActive={false}
                legendType="none"
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      )}

      {/* 범례 */}
      <div className="flex gap-3 mt-2 text-[10px] text-gray-500 flex-wrap">
        {chartType === 'line' ? (
          <>
            <span><span className="inline-block w-2 h-2 rounded-full bg-indigo-500 mr-1" />종가</span>
            <span><span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" />급등 유지</span>
            <span><span className="inline-block w-2 h-2 rounded-full bg-orange-500 mr-1" />급등 소멸</span>
            <span><span className="inline-block w-2 h-2 rounded-full bg-blue-500 mr-1" />급락 유지</span>
            <span><span className="inline-block w-2 h-2 rounded-full bg-cyan-500 mr-1" />급락 소멸</span>
          </>
        ) : (
          <>
            <span><span className="inline-block w-2 h-2 rounded bg-emerald-500 mr-1" />상승봉</span>
            <span><span className="inline-block w-2 h-2 rounded bg-red-500 mr-1" />하락봉</span>
            <span><span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" />급등 유지</span>
            <span><span className="inline-block w-2 h-2 rounded-full bg-orange-500 mr-1" />급등 소멸</span>
            <span><span className="inline-block w-2 h-2 rounded-full bg-blue-500 mr-1" />급락 유지</span>
            <span><span className="inline-block w-2 h-2 rounded-full bg-cyan-500 mr-1" />급락 소멸</span>
          </>
        )}
      </div>
    </div>
  )
}
