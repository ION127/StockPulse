'use client'

import { useState, useEffect, useCallback } from 'react'
import { useWatchlistStore } from '@/lib/watchlistStore'
import { useStore } from '@/lib/store'
import { useAuthStore } from '@/lib/authStore'
import { api } from '@/lib/api'
import { getCompanyName, hasCompanyName } from '@/lib/tickerNames'
import clsx from 'clsx'

type Tab = 'watchlist' | 'portfolio'

// ── 관심 종목 탭 ────────────────────────────────────────────────────────────

function WatchlistTab() {
  const { watchlist, removeFromWatchlist } = useWatchlistStore()
  const setSelectedTicker = useStore((s) => s.setSelectedTicker)
  const setSelectedAnomalyId = useStore((s) => s.setSelectedAnomalyId)
  const setSelectedAnomalyHasAnalysis = useStore((s) => s.setSelectedAnomalyHasAnalysis)
  const anomalies = useStore((s) => s.anomalies)

  if (watchlist.length === 0) {
    return (
      <p className="text-xs text-gray-600 py-6 text-center">
        검색바 또는 이상값 목록의 ★로 종목을 추가하세요
      </p>
    )
  }

  return (
    <div className="space-y-0.5">
      {watchlist.map((ticker) => {
        const recent = anomalies.find((a) => a.ticker === ticker)
        return (
          <div
            key={ticker}
            className="flex items-center justify-between px-3 py-2 rounded hover:bg-gray-800 cursor-pointer group"
            onClick={() => {
              setSelectedTicker(ticker)
              setSelectedAnomalyHasAnalysis(null)
              setSelectedAnomalyId(null)
            }}
          >
            <div className="min-w-0">
              <div className="text-sm text-white font-medium truncate">
                {hasCompanyName(ticker) ? getCompanyName(ticker) : ticker}
              </div>
              <div className="text-[10px] text-gray-500">
                {ticker}
                {recent && (
                  <span className={clsx('ml-2', recent.return_pct > 0 ? 'text-red-400' : 'text-blue-400')}>
                    {recent.return_pct > 0 ? '+' : ''}{recent.return_pct.toFixed(2)}% 최근이상값
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); removeFromWatchlist(ticker) }}
              className="text-gray-600 hover:text-red-400 text-sm ml-2 opacity-0 group-hover:opacity-100 transition-opacity"
            >
              ✕
            </button>
          </div>
        )
      })}
    </div>
  )
}

// ── 포트폴리오 탭 ────────────────────────────────────────────────────────────

function PortfolioTab() {
  const { watchlist, portfolio, setPortfolioItem, removePortfolioItem } = useWatchlistStore()
  const [prices, setPrices] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const [form, setForm] = useState({ ticker: '', qty: '', avgPrice: '' })

  const tickers = Object.keys(portfolio)

  const fetchPrices = useCallback(async () => {
    if (tickers.length === 0) return
    setLoading(true)
    const results: Record<string, number> = {}
    await Promise.all(
      tickers.map(async (ticker) => {
        try {
          const candles = await api.getCandles(ticker, 1)
          if (candles.length > 0) {
            results[ticker] = candles[candles.length - 1].close
          }
        } catch {
          // 가격 조회 실패 시 무시
        }
      })
    )
    setPrices(results)
    setLastUpdated(new Date().toLocaleTimeString('ko-KR'))
    setLoading(false)
  }, [tickers.join(',')])

  // 포트폴리오 탭 진입 시 및 60초마다 가격 갱신
  useEffect(() => {
    fetchPrices()
    const interval = setInterval(fetchPrices, 60_000)
    return () => clearInterval(interval)
  }, [fetchPrices])

  function handleAdd() {
    const qty = parseFloat(form.qty)
    const avgPrice = parseFloat(form.avgPrice)
    if (!form.ticker || isNaN(qty) || isNaN(avgPrice) || qty <= 0 || avgPrice <= 0) return
    setPortfolioItem(form.ticker, qty, avgPrice)
    setForm({ ticker: '', qty: '', avgPrice: '' })
  }

  const items = Object.entries(portfolio)
  const totalCost = items.reduce((s, [, i]) => s + i.qty * i.avgPrice, 0)
  const totalValue = items.reduce((s, [t, i]) => s + i.qty * (prices[t] ?? i.avgPrice), 0)
  const totalPnl = totalValue - totalCost
  const totalPnlPct = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0

  return (
    <div className="space-y-3">
      {/* 종목 추가 폼 */}
      <div className="bg-gray-800 rounded p-3 space-y-2">
        <p className="text-[10px] text-gray-500 font-medium">보유 종목 추가</p>
        <select
          value={form.ticker}
          onChange={(e) => setForm((f) => ({ ...f, ticker: e.target.value }))}
          className="w-full bg-gray-700 text-white text-xs rounded px-2 py-1.5 border border-gray-600"
        >
          <option value="">관심 종목에서 선택</option>
          {watchlist.map((t) => (
            <option key={t} value={t}>
              {hasCompanyName(t) ? getCompanyName(t) : t} ({t})
            </option>
          ))}
        </select>
        <div className="flex gap-2">
          <input
            type="number"
            placeholder="수량"
            value={form.qty}
            onChange={(e) => setForm((f) => ({ ...f, qty: e.target.value }))}
            className="flex-1 bg-gray-700 text-white text-xs rounded px-2 py-1.5 border border-gray-600 placeholder-gray-500"
          />
          <input
            type="number"
            placeholder="평균단가"
            value={form.avgPrice}
            onChange={(e) => setForm((f) => ({ ...f, avgPrice: e.target.value }))}
            className="flex-1 bg-gray-700 text-white text-xs rounded px-2 py-1.5 border border-gray-600 placeholder-gray-500"
          />
        </div>
        <button
          onClick={handleAdd}
          className="w-full bg-indigo-600 hover:bg-indigo-500 text-white text-xs rounded py-1.5 transition-colors"
        >
          추가
        </button>
      </div>

      {/* 보유 종목 목록 */}
      {items.length === 0 ? (
        <p className="text-xs text-gray-600 text-center py-2">보유 종목을 추가하면 현재 손익이 계산됩니다</p>
      ) : (
        <>
          {/* 갱신 상태 */}
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-gray-600">
              {loading ? '가격 조회 중...' : lastUpdated ? `${lastUpdated} 기준` : ''}
            </span>
            <button
              onClick={fetchPrices}
              disabled={loading}
              className="text-[10px] text-indigo-400 hover:text-indigo-300 disabled:text-gray-600"
            >
              새로고침
            </button>
          </div>

          <div className="space-y-1">
            {items.map(([ticker, item]) => {
              const currentPrice = prices[ticker] ?? null
              const value = item.qty * (currentPrice ?? item.avgPrice)
              const cost = item.qty * item.avgPrice
              const pnl = value - cost
              const pnlPct = (pnl / cost) * 100

              return (
                <div key={ticker} className="bg-gray-800 rounded px-3 py-2">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-sm text-white font-medium">
                        {hasCompanyName(ticker) ? getCompanyName(ticker) : ticker}
                      </span>
                      <span className="text-[10px] text-gray-500 ml-1">{ticker}</span>
                    </div>
                    <button
                      onClick={() => removePortfolioItem(ticker)}
                      className="text-gray-600 hover:text-red-400 text-xs"
                    >
                      ✕
                    </button>
                  </div>
                  <div className="mt-1 flex items-center justify-between text-[10px]">
                    <div className="text-gray-400">
                      <span>{item.qty}주</span>
                      <span className="mx-1">·</span>
                      <span>매수 {item.avgPrice.toLocaleString()}</span>
                      {currentPrice && (
                        <>
                          <span className="mx-1">→</span>
                          <span className="text-white">현재 {currentPrice.toLocaleString()}</span>
                        </>
                      )}
                    </div>
                    {currentPrice ? (
                      <span className={clsx('font-bold', pnl >= 0 ? 'text-red-400' : 'text-blue-400')}>
                        {pnl >= 0 ? '+' : ''}{pnl.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        {' '}({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%)
                      </span>
                    ) : (
                      <span className="text-gray-600">조회 중</span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* 총계 */}
          <div className="border-t border-gray-700 pt-2 space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-400">총 투자금액</span>
              <span className="text-white">{totalCost.toLocaleString(undefined, { maximumFractionDigits: 0 })}원</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-gray-400">평가금액</span>
              <span className="text-white">{totalValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}원</span>
            </div>
            <div className="flex items-center justify-between text-xs font-bold">
              <span className="text-gray-300">평가 손익</span>
              <span className={clsx(totalPnl >= 0 ? 'text-red-400' : 'text-blue-400')}>
                {totalPnl >= 0 ? '+' : ''}{totalPnl.toLocaleString(undefined, { maximumFractionDigits: 0 })}원
                {' '}({totalPnlPct >= 0 ? '+' : ''}{totalPnlPct.toFixed(2)}%)
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ── 메인 패널 ────────────────────────────────────────────────────────────────

function LoginPrompt() {
  const setOpenAuthModal = useStore((s) => s.setOpenAuthModal)
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 py-8">
      <p className="text-sm text-gray-400 text-center">
        관심 종목과 포트폴리오는<br />로그인 후 사용할 수 있습니다
      </p>
      <button
        onClick={() => setOpenAuthModal(true)}
        className="px-4 py-2 text-sm bg-indigo-600 hover:bg-indigo-500 rounded-lg font-medium transition-colors"
      >
        로그인 / 회원가입
      </button>
    </div>
  )
}

export default function PortfolioPanel() {
  const [tab, setTab] = useState<Tab>('watchlist')
  const { watchlist, portfolio } = useWatchlistStore()
  const { user } = useAuthStore()

  if (!user) {
    return (
      <div className="rounded-lg bg-gray-900 p-4 flex flex-col h-full">
        <h2 className="text-sm font-semibold text-gray-300 mb-3 shrink-0">관심 종목 / 포트폴리오</h2>
        <LoginPrompt />
      </div>
    )
  }

  return (
    <div className="rounded-lg bg-gray-900 p-4 flex flex-col h-full">
      <div className="flex items-center gap-1 mb-3 shrink-0">
        {(['watchlist', 'portfolio'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              'px-3 py-1 text-xs rounded font-medium transition-colors',
              tab === t ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
            )}
          >
            {t === 'watchlist'
              ? `관심 종목${watchlist.length > 0 ? ` (${watchlist.length})` : ''}`
              : `포트폴리오${Object.keys(portfolio).length > 0 ? ` (${Object.keys(portfolio).length})` : ''}`}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {tab === 'watchlist' ? <WatchlistTab /> : <PortfolioTab />}
      </div>
    </div>
  )
}
