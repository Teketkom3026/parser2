import React, { useState, useEffect, useRef, useCallback } from "react";
import ProgressBar from "./ProgressBar";
import ContactsTable from "./ContactsTable";

const API = import.meta.env.VITE_API_URL || "";
const WS_URL = import.meta.env.VITE_WS_URL || `ws://${window.location.host}`;

export default function TaskDetail({ taskId, onBack }) {
  const [task, setTask] = useState(null);
  const [progress, setProgress] = useState(null);
  const [contacts, setContacts] = useState([]);
  const [summary, setSummary] = useState(null);
  const [errors, setErrors] = useState([]);
  const [activeTab, setActiveTab] = useState("progress");
  const wsRef = useRef(null);
  const pingRef = useRef(null);

  // Загрузка данных задачи
  const fetchTask = useCallback(async () => {
    try {
      const resp = await fetch(`${API}/api/tasks/${taskId}`);
      if (resp.ok) {
        const data = await resp.json();
        setTask(data);
      }
    } catch { /* ignore */ }
  }, [taskId]);

  const fetchContacts = useCallback(async () => {
    try {
      const resp = await fetch(`${API}/api/tasks/${taskId}/contacts`);
      if (resp.ok) {
        const data = await resp.json();
        setContacts(data.contacts || []);
      }
    } catch { /* ignore */ }
  }, [taskId]);

  const fetchSummary = useCallback(async () => {
    try {
      const resp = await fetch(`${API}/api/tasks/${taskId}/summary`);
      if (resp.ok) {
        const data = await resp.json();
        setSummary(data);
      }
    } catch { /* ignore */ }
  }, [taskId]);

  const fetchErrors = useCallback(async () => {
    try {
      const resp = await fetch(`${API}/api/tasks/${taskId}/errors`);
      if (resp.ok) {
        const data = await resp.json();
        setErrors(data.errors || []);
      }
    } catch { /* ignore */ }
  }, [taskId]);

  // WebSocket
  useEffect(() => {
    fetchTask();

    const connectWs = () => {
      try {
        const ws = new WebSocket(`${WS_URL}/ws/tasks/${taskId}`);

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === "keepalive") return;
            setProgress(data);

            if (data.status === "completed" || data.status === "failed" || data.status === "cancelled") {
              fetchTask();
              fetchContacts();
              fetchSummary();
              fetchErrors();
            }
          } catch { /* ignore */ }
        };

        ws.onclose = () => {
          setTimeout(connectWs, 3000);
        };

        ws.onerror = () => {
          ws.close();
        };

        wsRef.current = ws;

        // Ping
        pingRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
          }
        }, 20000);
      } catch { /* ignore */ }
    };

    connectWs();

    return () => {
      if (wsRef.current) wsRef.current.close();
      if (pingRef.current) clearInterval(pingRef.current);
    };
  }, [taskId, fetchTask, fetchContacts, fetchSummary, fetchErrors]);

  // Загрузка табов
  useEffect(() => {
    if (activeTab === "contacts") fetchContacts();
    if (activeTab === "summary") fetchSummary();
    if (activeTab === "errors") fetchErrors();
  }, [activeTab, fetchContacts, fetchSummary, fetchErrors]);

  // Управление задачей
  const controlTask = async (action) => {
    try {
      await fetch(`${API}/api/tasks/${taskId}/${action}`, { method: "POST" });
      fetchTask();
    } catch { /* ignore */ }
  };

  const p = progress || {
    status: task?.status || "pending",
    processed: task?.processed_urls || 0,
    total: task?.total_urls || 0,
    found_contacts: task?.found_contacts || 0,
    errors: task?.errors_count || 0,
    message: "",
    current_url: "",
  };

  return (
    <div className="card">
      {/* Заголовок */}
      <div className="detail-header">
        <button className="btn-back" onClick={onBack}>← Назад</button>
        <h2>Задача {taskId?.slice(0, 8)}</h2>
        <div className="detail-controls">
          {(p.status === "running") && (
            <button className="btn-warning" onClick={() => controlTask("pause")}>
              ⏸ Пауза
            </button>
          )}
          {(p.status === "paused") && (
            <button className="btn-primary" onClick={() => controlTask("resume")}>
              ▶ Продолжить
            </button>
          )}
          {(p.status === "running" || p.status === "paused") && (
            <button className="btn-danger" onClick={() => controlTask("cancel")}>
              ✕ Отмена
            </button>
          )}
          {(p.status === "completed") && (
            <a
              href={`${API}/api/tasks/${taskId}/download`}
              className="btn-success"
              download
            >
              📥 Скачать Excel
            </a>
          )}
        </div>
      </div>

      {/* Прогресс */}
      <ProgressBar progress={p} />

      {/* Текущий URL */}
      {p.current_url && (
        <div className="current-url">
          🌐 {p.current_url}
        </div>
      )}

      {/* Табы */}
      <div className="tabs">
        <button
          className={`tab ${activeTab === "progress" ? "active" : ""}`}
          onClick={() => setActiveTab("progress")}
        >
          📊 Прогресс
        </button>
        <button
          className={`tab ${activeTab === "contacts" ? "active" : ""}`}
          onClick={() => setActiveTab("contacts")}
        >
          👤 Контакты ({p.found_contacts || 0})
        </button>
        <button
          className={`tab ${activeTab === "summary" ? "active" : ""}`}
          onClick={() => setActiveTab("summary")}
        >
          📈 Сводка
        </button>
        <button
          className={`tab ${activeTab === "errors" ? "active" : ""}`}
          onClick={() => setActiveTab("errors")}
        >
          ⚠️ Ошибки ({p.errors || 0})
        </button>
      </div>

      {/* Контент табов */}
      <div className="tab-content">
        {activeTab === "progress" && (
          <div className="progress-details">
            <div className="stat-grid">
              <div className="stat-card">
                <div className="stat-value">{p.processed || 0}</div>
                <div className="stat-label">Обработано URL</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{p.total || 0}</div>
                <div className="stat-label">Всего URL</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{p.found_contacts || 0}</div>
                <div className="stat-label">Найдено контактов</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{p.errors || 0}</div>
                <div className="stat-label">Ошибок</div>
              </div>
            </div>
            {p.message && <div className="progress-message">{p.message}</div>}
          </div>
        )}

        {activeTab === "contacts" && (
          <ContactsTable contacts={contacts} />
        )}

        {activeTab === "summary" && summary && (
          <div className="summary-panel">
            <div className="stat-grid">
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
                <div className="stat-label">С персональным email</div>
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
              <div className="summary-section">
                <h3>По категориям должностей</h3>
                <div className="category-list">
                  {Object.entries(summary.by_role_category).map(([cat, count]) => (
                    <div key={cat} className="category-item">
                      <span className="category-name">{cat}</span>
                      <span className="category-count">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === "errors" && (
          <div className="errors-panel">
            {errors.length === 0 ? (
              <div className="empty-state">Ошибок нет ✨</div>
            ) : (
              <table className="errors-table">
                <thead>
                  <tr>
                    <th>URL</th>
                    <th>Ошибка</th>
                    <th>Время</th>
                  </tr>
                </thead>
                <tbody>
                  {errors.map((err, i) => (
                    <tr key={i}>
                      <td className="error-url">{err.url}</td>
                      <td className="error-msg">{err.error_message}</td>
                      <td className="error-time">
                        {err.created_at
                          ? new Date(err.created_at).toLocaleTimeString("ru")
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
