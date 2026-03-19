'use client'

import { useEffect } from 'react'
import { connectWs, disconnectWs, onAnomaly, onStatus } from '@/lib/websocket'
import { useStore } from '@/lib/store'
import type { Anomaly } from '@/types'

export default function WsProvider({ children }: { children: React.ReactNode }) {
  const prependAnomaly = useStore((s) => s.prependAnomaly)
  const setWsConnected = useStore((s) => s.setWsConnected)

  useEffect(() => {
    connectWs()
    const offAnomaly = onAnomaly((msg) => {
      // WS 메시지를 최소 Anomaly 객체로 변환해 목록 앞에 추가
      const partial: Anomaly = {
        id: Date.now(),
        ticker: msg.ticker,
        anomaly_date: new Date().toISOString().split('T')[0],
        return_pct: msg.return_pct,
        zscore: null,
        close_price: null,
        volume: null,
        direction: msg.direction,
        event_type: msg.event_type as Anomaly['event_type'],
        sector: msg.sector || null,
        sector_peer_count: null,
        moving_sector_count: null,
        detected_at: new Date().toISOString(),
        has_analysis: false,
        bar_timestamp: null,
      }
      prependAnomaly(partial)
    })
    const offStatus = onStatus(setWsConnected)
    return () => {
      offAnomaly()
      offStatus()
      disconnectWs()
    }
  }, [prependAnomaly, setWsConnected])

  return <>{children}</>
}
