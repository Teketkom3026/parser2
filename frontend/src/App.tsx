import React, { useState, useEffect, useRef } from 'react'

const API_BASE = '/parser2/api/v1'
const WS_BASE = window.location.protocol === 'https:' 
  ? `wss://${window.location.host}/parser2/ws/tasks`
  : `ws://${window.location.host}/parser2/ws/tasks`

interface TaskInfo {
  task_id: string
  mode: string
  status: string
  total_urls: number
  processed_urls: number
  found_contacts: number
  errors_count: number
  created_at: string
  output_file?: string
}

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

interface BlacklistEntry {
  id: number
  entry_type: string
  entry_value: string
  added_at: string
}

type Tab = 'parser' | 'history' | 'blacklist'
type Mode = 'quick_start' | 'mode_2' | 'mode_1'

export default function App() {
  const [tab, setTab] = useState<Tab>('parser')
  const [mode, setMode] = useState<Mode>('quick_start')
  const [quickUrl, setQuickUrl] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [positions, setPositions] = useState('')
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [taskResult, setTaskResult] = useState<{ taskId: string; status: string } | null>(null)
  const [progress, setProgress] = useState<ProgressMsg | null>(null)
  const [connected, setConnected] = useState(false)
  const [tasks, setTasks] = useState<TaskInfo[]>([])
  const [blacklist, setBlacklist] = useState<BlacklistEntry[]>([])
  const [blFile, setBlFile] = useState<File | null>(null)
  const [blStatus, setBlStatus] = useState('')
  const logRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const addLog = (msg: string) => {
    setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`])
  }

  // WebSocket подключение
  useEffect(() => {
    if (!activeTaskId) return
    const ws = new WebSocket(`${WS_BASE}/${activeTaskId}/progress`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setConnected(false)
    ws.onmessage = (e) => {
      try {
        const data: ProgressMsg = JSON.parse(e.data)
        setProgress(data)
        if (data.message && data.message !== 'heartbeat') {
          addLog(data.message)
        }
        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          setIsRunning(false)
          setTaskResult({ taskId: data.task_id, status: data.status })
        }
      } catch {}
    }

    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send('ping')
    }, 25000)

    return () => {
      clearInterval(ping)
      ws.close()
    }
  }, [activeTaskId])

  // Автоскролл лога
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logs])

  const fetchTasks = async () => {
    const resp = await fetch(`${API_BASE}/tasks`)
    if (resp.ok) setTasks(await resp.json())
  }

  const fetchBlacklist = async () => {
    const resp = await fetch(`${API_BASE}/blacklist`)
    if (resp.ok) setBlacklist(await resp.json())
  }

  useEffect(() => {
    if (tab === 'history') fetchTasks()
    if (tab === 'blacklist') fetchBlacklist()
  }, [tab])

  const handleStart = async () => {
    setLogs([])
    setTaskResult(null)
    setProgress(null)
    setIsRunning(true)
    try {
      if (mode === 'quick_start') {
        if (!quickUrl.trim()) { alert('Введите URL'); setIsRunning(false); return }
        const resp = await fetch(`${API_BASE}/quick-start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            url: quickUrl.trim(),
            mode: positions.trim() ? 'mode_1' : 'mode_2',
            positions: positions.trim() ? positions.split(',').map(p => p.trim()) : [],
          }),
        })
        const data = await resp.json()
        if (!resp.ok) throw new Error(data.detail || 'Ошибка')
        setActiveTaskId(data.task_id)
        addLog(`Задача создана: ${data.task_id}`)
      } else {
        if (!file) { alert('Загрузите Excel-файл с URL'); setIsRunning(false); return }
        const formData = new FormData()
        formData.append('file', file)
        formData.append('mode', mode)
        formData.append('positions', positions)
        const resp = await fetch(`${API_BASE}/tasks`, { method: 'POST', body: formData })
        const data = await resp.json()
        if (!resp.ok) throw new Error(data.detail || 'Ошибка')
        setActiveTaskId(data.task_id)
        addLog(`Задача создана: ${data.task_id}, URL: ${data.total_urls}`)
      }
    } catch (e: any) {
      addLog(`❌ ${e.message}`)
      setIsRunning(false)
    }
  }

  const handlePause = async () => {
    if (!activeTaskId) return
    await fetch(`${API_BASE}/tasks/${activeTaskId}/pause`, { method: 'POST' })
    addLog('⏸ Пауза')
  }

  const handleResume = async () => {
    if (!activeTaskId) return
    await fetch(`${API_BASE}/tasks/${activeTaskId}/resume`, { method: 'POST' })
    addLog('▶ Возобновлено')
    setIsRunning(true)
  }

  const handleCancel = async () => {
    if (!activeTaskId) return
    await fetch(`${API_BASE}/tasks/${activeTaskId}/cancel`, { method: 'POST' })
    addLog('✖ Отменено')
    setIsRunning(false)
  }

  const handleDownload = (taskId: string) => {
    const a = document.createElement('a')
    a.href = `${API_BASE}/tasks/${taskId}/result`
    a.download = `contacts_${taskId}.xlsx`
    a.click()
  }

  const handleBlUpload = async () => {
    if (!blFile) return
    const fd = new FormData()
    fd.append('file', blFile)
    const resp = await fetch(`${API_BASE}/blacklist/upload`, { method: 'POST', body: fd })
    const data = await resp.json()
    setBlStatus(`Добавлено: ${data.entries_added}, всего: ${data.total_entries}`)
    fetchBlacklist()
  }

  const handleBlDelete = async (id: number) => {
    await fetch(`${API_BASE}/blacklist/${id}`, { method: 'DELETE' })
    fetchBlacklist()
  }

  const pct = progress && progress.total > 0
    ? Math.round((progress.processed / progress.total) * 100)
    : 0

  const statusColor = (s: string) => {
    const m: Record<string, string> = {
      completed: '#22c55e', running: '#3b82f6', failed: '#ef4444',
      cancelled: '#6b7280', pending: '#f59e0b', paused: '#a855f7',
    }
    return m[s] || '#6b7280'
  }

  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', background: '#0f172a', minHeight: '100vh', color: '#e2e8f0' }}>
      {/* Header */}
      <header style={{ background: '#1e293b', borderBottom: '1px solid #334155', padding: '0 24px', display: 'flex', alignItems: 'center', gap: 24, height: 56 }}>
        <span style={{ fontWeight: 700, fontSize: 18, color: '#60a5fa' }}>📋 Parser2</span>
        <nav style={{ display: 'flex', gap: 4 }}>
          {(['parser', 'history', 'blacklist'] as Tab[]).map(t => (
            <button key={t} onClick={() => setTab(t)}
              style={{ background: tab === t ? '#3b82f6' : 'transparent', color: tab === t ? '#fff' : '#94a3b8', border: 'none', borderRadius: 6, padding: '6px 16px', cursor: 'pointer', fontSize: 14 }}>
              {t === 'parser' ? '🔍 Парсер' : t === 'history' ? '📜 История' : '🚫 Blacklist'}
            </button>
          ))}
        </nav>
        <div style={{ marginLeft: 'auto', fontSize: 12, color: connected ? '#22c55e' : '#6b7280' }}>
          {connected ? '● Подключено' : '○ Ожидание'}
        </div>
      </header>

      <main style={{ maxWidth: 900, margin: '0 auto', padding: 24 }}>
        {/* ═══ ПАРСЕР ═══ */}
        {tab === 'parser' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Выбор режима */}
            <div style={{ background: '#1e293b', borderRadius: 12, padding: 20, border: '1px solid #334155' }}>
              <h2 style={{ margin: '0 0 16px', fontSize: 16, color: '#94a3b8' }}>РЕЖИМ ПАРСИНГА</h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                {[
                  { v: 'quick_start', label: '⚡ Быстрый старт', desc: 'Один URL — мгновенный результат' },
                  { v: 'mode_2', label: '📄 Все контакты', desc: 'Excel с URL → все контакты' },
                  { v: 'mode_1', label: '🎯 По должностям', desc: 'Excel + целевые должности' },
                ].map(({ v, label, desc }) => (
                  <label key={v} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: 12, background: mode === v ? '#1d4ed8' : '#0f172a', borderRadius: 8, border: `1px solid ${mode === v ? '#3b82f6' : '#334155'}`, cursor: 'pointer' }}>
                    <input type="radio" name="mode" value={v} checked={mode === v as Mode} onChange={() => setMode(v as Mode)} style={{ display: 'none' }} />
                    <strong style={{ fontSize: 14 }}>{label}</strong>
                    <span style={{ fontSize: 12, color: '#94a3b8' }}>{desc}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Ввод данных */}
            <div style={{ background: '#1e293b', borderRadius: 12, padding: 20, border: '1px solid #334155' }}>
              <h2 style={{ margin: '0 0 16px', fontSize: 16, color: '#94a3b8' }}>ВХОДНЫЕ ДАННЫЕ</h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {mode === 'quick_start' && (
                  <div>
                    <label style={{ fontSize: 13, color: '#94a3b8', display: 'block', marginBottom: 6 }}>URL сайта</label>
                    <input type="text" placeholder="https://example.com" value={quickUrl}
                      onChange={e => setQuickUrl(e.target.value)} disabled={isRunning}
                      style={{ width: '100%', background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: '10px 14px', color: '#e2e8f0', fontSize: 14, boxSizing: 'border-box' }} />
                  </div>
                )}
                {(mode === 'mode_1' || mode === 'mode_2') && (
                  <div>
                    <label style={{ fontSize: 13, color: '#94a3b8', display: 'block', marginBottom: 6 }}>Excel-файл с URL (один URL на строку)</label>
                    <input type="file" accept=".xlsx,.xls,.csv" onChange={e => setFile(e.target.files?.[0] || null)} disabled={isRunning}
                      style={{ color: '#e2e8f0', fontSize: 13 }} />
                    {file && <span style={{ fontSize: 12, color: '#60a5fa', marginLeft: 8 }}>📎 {file.name}</span>}
                  </div>
                )}
                {(mode === 'mode_1' || mode === 'quick_start') && (
                  <div>
                    <label style={{ fontSize: 13, color: '#94a3b8', display: 'block', marginBottom: 6 }}>
                      Целевые должности {mode === 'quick_start' ? '(необязательно)' : '(через запятую)'}
                    </label>
                    <input type="text" placeholder="Генеральный директор, Финансовый директор, CTO"
                      value={positions} onChange={e => setPositions(e.target.value)} disabled={isRunning}
                      style={{ width: '100%', background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: '10px 14px', color: '#e2e8f0', fontSize: 14, boxSizing: 'border-box' }} />
                  </div>
                )}
                <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                  <button onClick={handleStart} disabled={isRunning}
                    style={{ background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 8, padding: '10px 24px', cursor: isRunning ? 'not-allowed' : 'pointer', opacity: isRunning ? 0.7 : 1, fontSize: 14, fontWeight: 600 }}>
                    {isRunning ? '⏳ Обработка...' : '🚀 Запустить'}
                  </button>
                  {isRunning && (
                    <>
                      <button onClick={handlePause} style={{ background: '#f59e0b', color: '#fff', border: 'none', borderRadius: 8, padding: '10px 16px', cursor: 'pointer', fontSize: 14 }}>⏸ Пауза</button>
                      <button onClick={handleResume} style={{ background: '#22c55e', color: '#fff', border: 'none', borderRadius: 8, padding: '10px 16px', cursor: 'pointer', fontSize: 14 }}>▶ Продолжить</button>
                      <button onClick={handleCancel} style={{ background: '#ef4444', color: '#fff', border: 'none', borderRadius: 8, padding: '10px 16px', cursor: 'pointer', fontSize: 14 }}>✖ Отмена</button>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* Прогресс */}
            {activeTaskId && (
              <div style={{ background: '#1e293b', borderRadius: 12, padding: 20, border: '1px solid #334155' }}>
                <h2 style={{ margin: '0 0 16px', fontSize: 16, color: '#94a3b8' }}>ПРОГРЕСС</h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                  <span style={{ background: statusColor(progress?.status || 'pending'), color: '#fff', borderRadius: 6, padding: '3px 10px', fontSize: 13, fontWeight: 600 }}>
                    {progress?.status || 'pending'}
                  </span>
                  <span style={{ fontSize: 13, color: '#64748b' }}>{pct}%</span>
                </div>
                <div style={{ background: '#0f172a', borderRadius: 8, height: 10, overflow: 'hidden', marginBottom: 12 }}>
                  <div style={{ width: `${pct}%`, height: '100%', background: 'linear-gradient(90deg, #3b82f6, #60a5fa)', transition: 'width 0.5s ease', borderRadius: 8 }} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                  {[
                    { label: 'Обработано', value: `${progress?.processed || 0} / ${progress?.total || 0}` },
                    { label: 'Контактов', value: progress?.found_contacts || 0 },
                    { label: 'Ошибок', value: progress?.errors || 0 },
                  ].map(({ label, value }) => (
                    <div key={label} style={{ background: '#0f172a', borderRadius: 8, padding: '10px 14px', textAlign: 'center' }}>
                      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>{label}</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: '#e2e8f0' }}>{value}</div>
                    </div>
                  ))}
                </div>
                {taskResult?.status === 'completed' && (
                  <button onClick={() => handleDownload(taskResult.taskId)}
                    style={{ marginTop: 16, background: '#22c55e', color: '#fff', border: 'none', borderRadius: 8, padding: '12px 28px', cursor: 'pointer', fontSize: 15, fontWeight: 700, width: '100%' }}>
                    📥 Скачать результат (XLSX)
                  </button>
                )}
              </div>
            )}

            {/* Лог */}
            {logs.length > 0 && (
              <div style={{ background: '#1e293b', borderRadius: 12, padding: 20, border: '1px solid #334155' }}>
                <h2 style={{ margin: '0 0 12px', fontSize: 16, color: '#94a3b8' }}>ЛОГ ВЫПОЛНЕНИЯ</h2>
                <div ref={logRef} style={{ background: '#0f172a', borderRadius: 8, padding: 12, height: 200, overflowY: 'auto', fontFamily: 'monospace', fontSize: 13 }}>
                  {logs.map((line, i) => (
                    <div key={i} style={{ color: line.includes('❌') ? '#f87171' : '#94a3b8', marginBottom: 2 }}>{line}</div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ═══ ИСТОРИЯ ═══ */}
        {tab === 'history' && (
          <div style={{ background: '#1e293b', borderRadius: 12, padding: 20, border: '1px solid #334155' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <h2 style={{ margin: 0, fontSize: 16, color: '#94a3b8' }}>ИСТОРИЯ ЗАДАЧ</h2>
              <button onClick={fetchTasks} style={{ background: '#334155', color: '#e2e8f0', border: 'none', borderRadius: 6, padding: '6px 14px', cursor: 'pointer', fontSize: 13 }}>🔄 Обновить</button>
            </div>
            {tasks.length === 0 ? (
              <p style={{ color: '#64748b', textAlign: 'center' }}>Задач пока нет</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#0f172a' }}>
                      {['ID', 'Режим', 'Статус', 'URL', 'Контакты', 'Ошибки', 'Дата', 'Действия'].map(h => (
                        <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: '#64748b', borderBottom: '1px solid #334155' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tasks.map(t => (
                      <tr key={t.task_id} style={{ borderBottom: '1px solid #1e293b' }}>
                        <td style={{ padding: '8px 12px', fontFamily: 'monospace', color: '#60a5fa' }}>{t.task_id.slice(0, 8)}…</td>
                        <td style={{ padding: '8px 12px' }}>{t.mode}</td>
                        <td style={{ padding: '8px 12px' }}>
                          <span style={{ background: statusColor(t.status), color: '#fff', borderRadius: 4, padding: '2px 8px', fontSize: 12 }}>{t.status}</span>
                        </td>
                        <td style={{ padding: '8px 12px' }}>{t.processed_urls}/{t.total_urls}</td>
                        <td style={{ padding: '8px 12px' }}>{t.found_contacts}</td>
                        <td style={{ padding: '8px 12px', color: t.errors_count > 0 ? '#f87171' : '#94a3b8' }}>{t.errors_count}</td>
                        <td style={{ padding: '8px 12px', color: '#64748b' }}>{t.created_at?.slice(0, 16)}</td>
                        <td style={{ padding: '8px 12px' }}>
                          {t.status === 'completed' && (
                            <button onClick={() => handleDownload(t.task_id)}
                              style={{ background: '#22c55e', color: '#fff', border: 'none', borderRadius: 4, padding: '4px 10px', cursor: 'pointer', fontSize: 12 }}>📥 XLSX</button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ═══ BLACKLIST ═══ */}
        {tab === 'blacklist' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ background: '#1e293b', borderRadius: 12, padding: 20, border: '1px solid #334155' }}>
              <h2 style={{ margin: '0 0 16px', fontSize: 16, color: '#94a3b8' }}>ЗАГРУЗИТЬ BLACKLIST</h2>
              <p style={{ color: '#64748b', fontSize: 13, margin: '0 0 12px' }}>Excel/CSV файл: один email или домен на строку (со 2-й строки)</p>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <input type="file" accept=".xlsx,.xls,.csv,.txt" onChange={e => setBlFile(e.target.files?.[0] || null)} style={{ color: '#e2e8f0', fontSize: 13 }} />
                <button onClick={handleBlUpload} disabled={!blFile}
                  style={{ background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 18px', cursor: blFile ? 'pointer' : 'not-allowed', fontSize: 13 }}>
                  Загрузить
                </button>
              </div>
              {blStatus && <p style={{ color: '#22c55e', fontSize: 13, marginTop: 8 }}>{blStatus}</p>}
            </div>
            <div style={{ background: '#1e293b', borderRadius: 12, padding: 20, border: '1px solid #334155' }}>
              <h2 style={{ margin: '0 0 16px', fontSize: 16, color: '#94a3b8' }}>ЗАПИСИ BLACKLIST ({blacklist.length})</h2>
              {blacklist.length === 0 ? (
                <p style={{ color: '#64748b' }}>Blacklist пуст</p>
              ) : (
                <div style={{ maxHeight: 400, overflowY: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr style={{ background: '#0f172a' }}>
                        {['Тип', 'Значение', 'Добавлено', ''].map(h => (
                          <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: '#64748b', borderBottom: '1px solid #334155' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {blacklist.map(e => (
                        <tr key={e.id} style={{ borderBottom: '1px solid #1e293b' }}>
                          <td style={{ padding: '6px 12px' }}>
                            <span style={{ background: e.entry_type === 'email' ? '#1d4ed8' : '#7c3aed', color: '#fff', borderRadius: 4, padding: '2px 8px', fontSize: 11 }}>{e.entry_type}</span>
                          </td>
                          <td style={{ padding: '6px 12px', fontFamily: 'monospace' }}>{e.entry_value}</td>
                          <td style={{ padding: '6px 12px', color: '#64748b' }}>{e.added_at?.slice(0, 10)}</td>
                          <td style={{ padding: '6px 12px' }}>
                            <button onClick={() => handleBlDelete(e.id)}
                              style={{ background: 'transparent', color: '#ef4444', border: '1px solid #ef4444', borderRadius: 4, padding: '2px 8px', cursor: 'pointer', fontSize: 12 }}>
                              Удалить
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
