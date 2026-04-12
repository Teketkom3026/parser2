import { useState, useCallback } from 'react'

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

export function useTaskStatus() {
  const [tasks, setTasks] = useState<TaskInfo[]>([])

  const fetchTasks = useCallback(async () => {
    try {
      const resp = await fetch('/parser2/api/v1/tasks')
      if (resp.ok) {
        const data = await resp.json()
        setTasks(data)
      }
    } catch (e) {
      console.error('fetchTasks error', e)
    }
  }, [])

  return { tasks, fetchTasks }
}
