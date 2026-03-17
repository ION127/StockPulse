'use client'

import { useEffect } from 'react'
import { useStore } from '@/lib/store'
import { api } from '@/lib/api'
import clsx from 'clsx'

export default function AnalysisPanel() {
  const selectedAnomalyId = useStore((s) => s.selectedAnomalyId)
  const analyses = useStore((s) => s.analyses)
  const setAnalysis = useStore((s) => s.setAnalysis)
  const lang = useStore((s) => s.analysisLang)
  const setLang = useStore((s) => s.setAnalysisLang)

  const analysis = selectedAnomalyId != null ? analyses[selectedAnomalyId] : null

  useEffect(() => {
    if (selectedAnomalyId == null || analyses[selectedAnomalyId]) return
    api.getAnalysis(selectedAnomalyId)
      .then((a) => setAnalysis(selectedAnomalyId, a))
      .catch(() => { /* 분석 없음 */ })
  }, [selectedAnomalyId, analyses, setAnalysis])

  return (
    <div className="rounded-lg bg-gray-900 p-4 flex flex-col h-full">
      <div className="flex items-center justify-between mb-3 shrink-0">
        <h2 className="text-sm font-semibold text-gray-300">AI 분석 리포트</h2>
        <div className="flex rounded overflow-hidden border border-gray-700">
          {(['ko', 'en'] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={clsx(
                'px-3 py-1 text-xs font-medium transition-colors',
                lang === l ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'
              )}
            >
              {l === 'ko' ? '한국어' : 'English'}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {!selectedAnomalyId ? (
          <p className="text-xs text-gray-600">이상값을 선택하세요</p>
        ) : !analysis ? (
          <p className="text-xs text-gray-600">분석 데이터를 불러오는 중...</p>
        ) : (
          <>
            <div className="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">
              {lang === 'ko' ? analysis.analysis_ko : analysis.analysis_en}
            </div>

            {/* 뉴스 참고자료 */}
            {(() => {
              const news = lang === 'ko' ? analysis.news_kr : analysis.news_en
              if (!news || news.length === 0) return null
              return (
                <div className="mt-4 border-t border-gray-800 pt-3">
                  <p className="text-xs text-gray-500 mb-2">참고 뉴스</p>
                  <ul className="space-y-1.5">
                    {news.map((n, i) => (
                      <li key={i}>
                        <a
                          href={n.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-indigo-400 hover:text-indigo-300 line-clamp-2"
                        >
                          {n.title}
                        </a>
                        <span className="text-[10px] text-gray-600 ml-1">{n.source}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )
            })()}
          </>
        )}
      </div>
    </div>
  )
}
