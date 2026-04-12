import { useState, useEffect, useRef } from 'react'

interface ProgressMsg {
  task_id: string
  status: string
  processed: number
  total: number
  found_contacts: number
  errors: number
  current_url: string
  message: string
}

export function useWebSocket(taskId: string | null) {
  const [progress, setProgress] = useState<ProgressMsg | null>(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!taskId) return

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/parser2/ws/tasks/${taskId}/progress`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setConnected(false)

    ws.onmessage = (e) => {
      try {
        const data: ProgressMsg = JSON.parse(e.data)
        setProgress(data)
      } catch {}
    }

    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send('ping')
    }, 25000)

    return () => {
      clearInterval(ping)
      ws.close()
      wsRef.current = null
    }
  }, [taskId])

  return { progress, connected }
}
