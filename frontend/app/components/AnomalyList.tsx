'use client'

import { useState } from 'react'
import { useStore } from '@/lib/store'
import { useWatchlistStore } from '@/lib/watchlistStore'
import { useAuthStore } from '@/lib/authStore'
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
  const { isWatched, addToWatchlist, removeFromWatchlist } = useWatchlistStore()
  const watched = isWatched(anomaly.ticker)
  const { user } = useAuthStore()
  const setOpenAuthModal = useStore((s) => s.setOpenAuthModal)

  function handleStar(e: React.MouseEvent) {
    e.stopPropagation()
    if (!user) {
      setOpenAuthModal(true)
      return
    }
    watched ? removeFromWatchlist(anomaly.ticker) : addToWatchlist(anomaly.ticker)
  }

  return (
    <div className="flex items-center gap-1 hover:bg-gray-800 rounded transition-colors border border-transparent hover:border-gray-700">
      <button
        onClick={handleStar}
        className={clsx('shrink-0 px-1.5 py-2 text-sm transition-colors', watched ? 'text-yellow-400' : 'text-gray-700 hover:text-gray-400')}
        title={user ? (watched ? '관심 종목 제거' : '관심 종목 추가') : '로그인 후 이용 가능'}
      >
        ★
      </button>
      <button
        onClick={onClick}
        className="flex-1 text-left py-2.5 pr-3"
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
    </div>
  )
}

const PAGE_SIZE = 20

export default function AnomalyList() {
  const anomalies = useStore((s) => s.anomalies)
  const setSelectedTicker = useStore((s) => s.setSelectedTicker)
  const setSelectedAnomalyId = useStore((s) => s.setSelectedAnomalyId)
  const setSelectedAnomalyHasAnalysis = useStore((s) => s.setSelectedAnomalyHasAnalysis)
  const { watchlist, isWatched } = useWatchlistStore()
  const [myOnly, setMyOnly] = useState(false)
  const [page, setPage] = useState(0)

  const filtered = myOnly ? anomalies.filter((a) => isWatched(a.ticker)) : anomalies
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  // 필터 변경 시 첫 페이지로
  const handleMyOnly = () => { setMyOnly((v) => !v); setPage(0) }

  function handleClick(a: Anomaly) {
    setSelectedTicker(a.ticker)
    setSelectedAnomalyHasAnalysis(a.has_analysis)
    setSelectedAnomalyId(a.has_analysis ? a.id : null)
  }

  return (
    <div className="rounded-lg bg-gray-900 p-4 flex flex-col h-full">
      <div className="flex items-center justify-between mb-2 shrink-0">
        <h2 className="text-sm font-semibold text-gray-300">
          이상값 목록
          <span className="ml-2 text-xs text-gray-600">({filtered.length}건)</span>
        </h2>
        {watchlist.length > 0 && (
          <button
            onClick={handleMyOnly}
            className={clsx(
              'text-[10px] px-2 py-0.5 rounded transition-colors',
              myOnly ? 'bg-yellow-500 text-black font-bold' : 'bg-gray-700 text-gray-400 hover:text-white'
            )}
          >
            ★ 내 종목만
          </button>
        )}
      </div>
      <div className="overflow-y-auto scrollbar-thin flex-1 space-y-0.5 pr-1">
        {paginated.length === 0 ? (
          <p className="text-xs text-gray-600 py-4 text-center">
            {myOnly ? '관심 종목의 이상값 없음' : '이상값 없음'}
          </p>
        ) : (
          paginated.map((a) => (
            <AnomalyRow key={`${a.id}-${a.ticker}`} anomaly={a} onClick={() => handleClick(a)} />
          ))
        )}
      </div>
      {/* 페이지네이션 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-800 shrink-0">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
          >
            ← 이전
          </button>
          <span className="text-[10px] text-gray-600">
            {page + 1} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
          >
            다음 →
          </button>
        </div>
      )}
    </div>
  )
}
