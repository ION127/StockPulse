'use client'

import { useStore } from '@/lib/store'
import { useAuthStore } from '@/lib/authStore'
import { api } from '@/lib/api'
import { useState } from 'react'
import SearchBar from './SearchBar'
import AuthModal from './AuthModal'

export default function Header({ lastUpdated }: { lastUpdated: string }) {
  const wsConnected = useStore((s) => s.wsConnected)
  const setRunningJobId = useStore((s) => s.setRunningJobId)
  const runningJobId = useStore((s) => s.runningJobId)
  const [triggering, setTriggering] = useState(false)
  const [reanalyzing, setReanalyzing] = useState(false)

  const { user, logout } = useAuthStore()
  const openAuthModal = useStore((s) => s.openAuthModal)
  const setOpenAuthModal = useStore((s) => s.setOpenAuthModal)

  async function triggerAnalysis() {
    setTriggering(true)
    try {
      const job = await api.triggerAnalysis()
      setRunningJobId(job.job_id)

      // 완료될 때까지 폴링
      const interval = setInterval(async () => {
        const status = await api.getJobStatus(job.job_id)
        if (status.status === 'done' || status.status === 'failed') {
          clearInterval(interval)
          setRunningJobId(null)
          setTriggering(false)
          window.location.reload()
        }
      }, 3000)
    } catch {
      setTriggering(false)
    }
  }

  async function reanalyze() {
    setReanalyzing(true)
    try {
      const job = await api.reanalyzeAnomalies(7)
      setRunningJobId(job.job_id)

      const interval = setInterval(async () => {
        const status = await api.getJobStatus(job.job_id)
        if (status.status === 'done' || status.status === 'failed') {
          clearInterval(interval)
          setRunningJobId(null)
          setReanalyzing(false)
          window.location.reload()
        }
      }, 3000)
    } catch {
      setReanalyzing(false)
    }
  }

  return (
    <header className="bg-gray-900 border-b border-gray-800 px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-2">
      {/* 브랜드 */}
      <div className="flex items-center gap-2 min-w-0 shrink-0">
        <span className="text-base font-bold tracking-tight whitespace-nowrap">주식 이상값 AI 분석기</span>
        <span className="hidden lg:block text-xs text-gray-400 truncate">마지막 업데이트: {lastUpdated}</span>
      </div>

      {/* 데스크톱 여백 */}
      <div className="hidden md:block flex-1" />

      {/* 검색바: 모바일은 마지막 줄 전체 너비, md+는 인라인 고정 너비 */}
      <div className="order-last w-full md:order-none md:w-52 lg:w-64">
        <SearchBar />
      </div>

      {/* 우측 컨트롤 */}
      <div className="flex items-center gap-2 ml-auto md:ml-0 shrink-0">
        {/* WS 상태 */}
        <div className="flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full shrink-0 ${wsConnected ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`} />
          <span className="hidden sm:block text-xs text-gray-400 whitespace-nowrap">
            {wsConnected ? '실시간' : '끊김'}
          </span>
        </div>

        {/* 과거 재분석 버튼 */}
        <button
          onClick={reanalyze}
          disabled={reanalyzing || triggering}
          className="px-2.5 py-1.5 text-xs bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:cursor-not-allowed rounded font-medium transition-colors whitespace-nowrap"
          title="분석 리포트가 없는 최근 7일 이상값을 재분석"
        >
          {reanalyzing ? '재분석 중...' : '과거 재분석'}
        </button>

        {/* 분석 실행 버튼 */}
        <button
          onClick={triggerAnalysis}
          disabled={triggering || reanalyzing}
          className="px-2.5 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:cursor-not-allowed rounded font-medium transition-colors whitespace-nowrap"
        >
          {triggering ? '분석 중...' : <><span className="hidden sm:inline">수동 </span>분석 실행</>}
        </button>

        {/* 로그인 / 유저 정보 */}
        {user ? (
          <div className="flex items-center gap-1.5">
            <span className="hidden sm:block text-xs text-gray-300 max-w-[100px] truncate">{user.email}</span>
            <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-900 text-indigo-300 shrink-0">{user.tier}</span>
            <button
              onClick={logout}
              className="px-2.5 py-1.5 text-xs bg-gray-700 hover:bg-gray-600 rounded font-medium transition-colors whitespace-nowrap"
            >
              로그아웃
            </button>
          </div>
        ) : (
          <button
            onClick={() => setOpenAuthModal(true)}
            className="px-2.5 py-1.5 text-xs bg-gray-700 hover:bg-gray-600 rounded font-medium transition-colors whitespace-nowrap"
          >
            로그인
          </button>
        )}
      </div>

      {openAuthModal && <AuthModal onClose={() => setOpenAuthModal(false)} />}
    </header>
  )
}
