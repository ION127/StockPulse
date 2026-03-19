'use client'

import { useState, useRef, useEffect } from 'react'
import { useStore } from '@/lib/store'
import { searchTickers, getCompanyName } from '@/lib/tickerNames'

export default function SearchBar() {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const setSelectedTicker = useStore((s) => s.setSelectedTicker)
  const setSelectedAnomalyId = useStore((s) => s.setSelectedAnomalyId)
  const ref = useRef<HTMLDivElement>(null)

  const results = searchTickers(query)

  function select(ticker: string) {
    setSelectedTicker(ticker)
    setSelectedAnomalyId(null)
    setQuery(getCompanyName(ticker))
    setOpen(false)
  }

  // 외부 클릭 시 드롭다운 닫기
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  return (
    <div ref={ref} className="relative w-64">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-800 border border-gray-700 rounded-lg focus-within:border-indigo-500 transition-colors">
        <svg className="w-3.5 h-3.5 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          placeholder="종목 검색 (예: NVIDIA, 삼성)"
          className="bg-transparent text-xs text-white placeholder-gray-500 outline-none w-full"
        />
        {query && (
          <button
            onClick={() => { setQuery(''); setOpen(false); setSelectedTicker(null) }}
            className="text-gray-500 hover:text-gray-300 shrink-0"
          >
            ✕
          </button>
        )}
      </div>

      {open && results.length > 0 && (
        <div className="absolute top-full mt-1 w-full bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 overflow-hidden">
          {results.map(({ ticker, name }) => (
            <button
              key={ticker}
              onMouseDown={() => select(ticker)}
              className="w-full text-left px-3 py-2 hover:bg-gray-700 flex items-center justify-between gap-2 transition-colors"
            >
              <span className="text-xs text-white">{name}</span>
              <span className="text-[10px] text-gray-400 font-mono shrink-0">{ticker}</span>
            </button>
          ))}
        </div>
      )}

      {open && query.length > 0 && results.length === 0 && (
        <div className="absolute top-full mt-1 w-full bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 px-3 py-2">
          <span className="text-xs text-gray-500">검색 결과 없음</span>
        </div>
      )}
    </div>
  )
}
