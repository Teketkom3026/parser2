export interface TaskInfo {
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

export interface ProgressMessage {
  task_id: string
  status: string
  processed: number
  total: number
  found_contacts: number
  errors: number
  current_url: string
  message: string
}

export interface BlacklistEntry {
  id: number
  entry_type: string
  entry_value: string
  added_at: string
  source?: string
}

export interface QuickStartRequest {
  url: string
  mode: string
  positions: string[]
}
