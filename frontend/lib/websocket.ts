import type { WsAnomalyMessage } from '@/types'

const WS_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000')
  .replace(/^http/, 'ws') + '/ws/live'

type Listener = (msg: WsAnomalyMessage) => void
type StatusCb = (connected: boolean) => void

let ws: WebSocket | null = null
let listeners: Listener[] = []
let statusCbs: StatusCb[] = []
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

function notify(connected: boolean) {
  statusCbs.forEach((cb) => cb(connected))
}

export function connectWs() {
  if (ws && ws.readyState === WebSocket.OPEN) return

  ws = new WebSocket(WS_URL)

  ws.onopen = () => {
    notify(true)
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  }

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data) as WsAnomalyMessage
      if (msg.type === 'anomaly') listeners.forEach((l) => l(msg))
    } catch { /* ignore */ }
  }

  ws.onclose = () => {
    notify(false)
    reconnectTimer = setTimeout(connectWs, 5000)
  }

  ws.onerror = () => ws?.close()
}

export function disconnectWs() {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  ws?.close()
  ws = null
}

export function onAnomaly(cb: Listener) {
  listeners.push(cb)
  return () => { listeners = listeners.filter((l) => l !== cb) }
}

export function onStatus(cb: StatusCb) {
  statusCbs.push(cb)
  return () => { statusCbs = statusCbs.filter((s) => s !== cb) }
}
