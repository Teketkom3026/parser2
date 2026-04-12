import React, { useState, useEffect } from 'react';
import { useApi } from '../hooks/useApi';
import { useWebSocket } from '../hooks/useWebSocket';
import ProgressBar from './ProgressBar';

export default function TaskDetails({ taskId, onBack }) {
  const api = useApi();
  const { progress, connected } = useWebSocket(taskId);
  const [task, setTask] = useState(null);
  const [contacts, setContacts] = useState([]);
  const [summary, setSummary] = useState(null);
  const [errors, setErrors] = useState([]);
  const [activeSubTab, setActiveSubTab] = useState('progress');

  // Загрузка задачи
  useEffect(() => {
    const fetch = async () => {
      try {
        const data = await api.getTask(taskId);
        setTask(data);
      } catch { /* ignore */ }
    };
    fetch();
  }, [taskId]);

  // Обновляем task из WebSocket
  useEffect(() => {
    if (progress && progress.task_id === taskId) {
      setTask((prev) => ({
        ...prev,
        status: progress.status || prev?.status,
        processed_urls: progress.processed ?? prev?.processed_urls,
        total_urls: progress.total ?? prev?.total_urls,
        found_contacts: progress.found_contacts ?? prev?.found_contacts,
        errors_count: progress.errors ?? prev?.errors_count,
      }));
    }
  }, [progress, taskId]);

  // Загрузка контактов
  const loadContacts = async () => {
    try {
      const data = await api.getContacts(taskId);
      setContacts(data.contacts || []);
      setActiveSubTab('contacts');
    } catch { /* ignore */ }
  };

  // Загрузка сводки
  const loadSummary = async () => {
    try {
      const data = await api.getSummary(taskId);
      setSummary(data);
      setActiveSubTab('summary');
    } catch { /* ignore */ }
  };

  // Загрузка ошибок
  const loadErrors = async () => {
    try {
      const data = await api.getErrors(taskId);
      setErrors(data.errors || []);
      setActiveSubTab('errors');
    } catch { /* ignore */ }
  };

  if (!task) {
    return <div className="card"><p>Загрузка...</p></div>;
  }

  const pct = task.total_urls
    ? Math.round((task.processed_urls / task.total_urls) * 100)
    : 0;

  return (
    <div>
      {/* Кнопка назад */}
      <button className="btn btn-outline btn-sm" onClick={onBack} style={{ marginBottom: 16 }}>
        ← Назад к задачам
      </button>

      {/* Статистика */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{task.processed_urls || 0}</div>
          <div className="stat-label">Обработано из {task.total_urls || 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--success)' }}>
            {task.found_contacts || 0}
          </div>
          <div className="stat-label">Контактов найдено</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: 'var(--danger)' }}>
            {task.errors_count || 0}
          </div>
          <div className="stat-label">Ошибок</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ fontSize: 16 }}>
            <span className={`badge badge-${task.status}`}>
              {task.status}
            </span>
          </div>
          <div className="stat-label">
            {connected ? '🟢 Live' : '🔴 Offline'}
          </div>
        </div>
      </div>

      {/* Прогресс */}
      <div className="card">
        <ProgressBar
          percent={pct}
          status={task.status}
          message={progress?.message || `${pct}% завершено`}
          currentUrl={progress?.current_url || ''}
        />

        {/* Кнопки управления */}
        <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
          {task.status === 'running' && (
            <button className="btn btn-warning btn-sm" onClick={() => api.pauseTask(taskId)}>
              ⏸️ Пауза
            </button>
          )}
          {task.status === 'paused' && (
            <button className="btn btn-primary btn-sm" onClick={() => api.resumeTask(taskId)}>
              ▶️ Продолжить
            </button>
          )}
          {['running', 'paused', 'pending'].includes(task.status) && (
            <button className="btn btn-danger btn-sm" onClick={() => api.cancelTask(taskId)}>
              ✕ Отменить
            </button>
          )}
          {task.status === 'completed' && (
            <a
              className="btn btn-success btn-sm"
              href={api.downloadUrl(taskId)}
              target="_blank"
              rel="noopener noreferrer"
            >
              📥 Скачать Excel
            </a>
          )}
        </div>
      </div>

      {/* Вкладки */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          className={`btn btn-sm ${activeSubTab === 'progress' ? 'btn-primary' : 'btn-outline'}`}
          onClick={() => setActiveSubTab('progress')}
        >
          📊 Прогресс
        </button>
        <button
          className={`btn btn-sm ${activeSubTab === 'contacts' ? 'btn-primary' : 'btn-outline'}`}
          onClick={loadContacts}
        >
          👥 Контакты ({task.found_contacts || 0})
        </button>
        <button
          className={`btn btn-sm ${activeSubTab === 'summary' ? 'btn-primary' : 'btn-outline'}`}
          onClick={loadSummary}
        >
          📈 Сводка
        </button>
        <button
          className={`btn btn-sm ${activeSubTab === 'errors' ? 'btn-primary' : 'btn-outline'}`}
          onClick={loadErrors}
        >
          ⚠️ Ошибки ({task.errors_count || 0})
        </button>
      </div>

      {/* Контент вкладок */}
      {activeSubTab === 'contacts' && (
        <div className="card" style={{ overflowX: 'auto' }}>
          <h3 className="card-title">Найденные контакты</h3>
          {contacts.length === 0 ? (
            <p style={{ color: 'var(--text-secondary)' }}>Контактов пока нет</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Компания</th>
                  <th>ФИО</th>
                  <th>Должность</th>
                  <th>Email</th>
                  <th>Телефон</th>
                  <th>Сайт</th>
                </tr>
              </thead>
              <tbody>
                {contacts.slice(0, 100).map((c, i) => (
                  <tr key={i}>
                    <td>{c.company_name || '—'}</td>
                    <td><strong>{c.person_name || '—'}</strong></td>
                    <td>{c.position_norm || c.position_raw || '—'}</td>
                    <td>{c.person_email || c.company_email || '—'}</td>
                    <td>{c.person_phone || c.company_phone || '—'}</td>
                    <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {c.site_url || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {contacts.length > 100 && (
            <p style={{ marginTop: 12, color: 'var(--text-secondary)', fontSize: 13 }}>
              Показано 100 из {contacts.length}. Скачайте Excel для полного списка.
            </p>
          )}
        </div>
      )}

      {activeSubTab === 'summary' && summary && (
        <div className="card">
          <h3 className="card-title">Сводка</h3>
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-value">{summary.total_contacts}</div>
              <div className="stat-label">Всего контактов</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{summary.unique_sites}</div>
              <div className="stat-label">Уникальных сайтов</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{summary.with_person_name}</div>
              <div className="stat-label">С ФИО</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{summary.with_person_email}</div>
              <div className="stat-label">С email персоны</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{summary.with_phone}</div>
              <div className="stat-label">С телефоном</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{summary.with_inn}</div>
              <div className="stat-label">С ИНН</div>
            </div>
          </div>

          {summary.by_role_category && Object.keys(summary.by_role_category).length > 0 && (
            <div style={{ marginTop: 16 }}>
              <h4 style={{ marginBottom: 8 }}>По категориям</h4>
              <table className="data-table">
                <thead>
                  <tr><th>Категория</th><th>Количество</th></tr>
                </thead>
                <tbody>
                  {Object.entries(summary.by_role_category).map(([cat, cnt]) => (
                    <tr key={cat}><td>{cat}</td><td>{cnt}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeSubTab === 'errors' && (
        <div className="card">
          <h3 className="card-title">Ошибки</h3>
          {errors.length === 0 ? (
            <p style={{ color: 'var(--text-secondary)' }}>Ошибок нет</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr><th>URL</th><th>Ошибка</th><th>Время</th></tr>
              </thead>
              <tbody>
                {errors.map((e, i) => (
                  <tr key={i}>
                    <td style={{ maxWidth: 250, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {e.url || '—'}
                    </td>
                    <td style={{ color: 'var(--danger)', maxWidth: 400, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {e.error_message || '—'}
                    </td>
                    <td style={{ whiteSpace: 'nowrap', fontSize: 12 }}>
                      {e.created_at || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
