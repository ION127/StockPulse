'use client'

import { useStore } from '@/lib/store'
import { api } from '@/lib/api'
import { useState } from 'react'

export default function Header({ lastUpdated }: { lastUpdated: string }) {
  const wsConnected = useStore((s) => s.wsConnected)
  const setRunningJobId = useStore((s) => s.setRunningJobId)
  const runningJobId = useStore((s) => s.runningJobId)
  const [triggering, setTriggering] = useState(false)

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

  return (
    <header className="flex items-center justify-between px-6 py-3 bg-gray-900 border-b border-gray-800">
      <div className="flex items-center gap-3">
        <span className="text-lg font-bold tracking-tight">주식 이상값 AI 분석기</span>
        <span className="text-xs text-gray-400">마지막 업데이트: {lastUpdated}</span>
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${wsConnected ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`} />
          <span className="text-xs text-gray-400">{wsConnected ? '실시간 연결됨' : '연결 끊김'}</span>
        </div>
        <button
          onClick={triggerAnalysis}
          disabled={triggering}
          className="px-3 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:cursor-not-allowed rounded font-medium transition-colors"
        >
          {triggering ? `분석 중... (${runningJobId})` : '수동 분석 실행'}
        </button>
      </div>
    </header>
  )
}
