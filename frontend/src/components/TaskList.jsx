import React, { useState, useEffect } from "react";

const API = import.meta.env.VITE_API_URL || "";

const STATUS_MAP = {
  pending: { label: "Ожидает", color: "#6c757d", icon: "⏳" },
  running: { label: "Выполняется", color: "#0d6efd", icon: "🔄" },
  paused: { label: "На паузе", color: "#ffc107", icon: "⏸" },
  completed: { label: "Завершена", color: "#198754", icon: "✅" },
  cancelled: { label: "Отменена", color: "#dc3545", icon: "🚫" },
  failed: { label: "Ошибка", color: "#dc3545", icon: "❌" },
};

export default function TaskList({ onSelectTask }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchTasks = async () => {
    try {
      const resp = await fetch(`${API}/api/tasks`);
      if (resp.ok) {
        const data = await resp.json();
        setTasks(data.tasks || []);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="card">
        <h2>📋 Задачи</h2>
        <div className="loading">Загрузка...</div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <h2>📋 Задачи</h2>
        <button className="btn-secondary" onClick={fetchTasks}>
          🔄 Обновить
        </button>
      </div>

      {tasks.length === 0 ? (
        <div className="empty-state">
          <p>Нет задач</p>
          <p className="hint">Создайте первую задачу парсинга</p>
        </div>
      ) : (
        <div className="task-table-wrapper">
          <table className="task-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Статус</th>
                <th>Режим</th>
                <th>Прогресс</th>
                <th>Контакты</th>
                <th>Ошибки</th>
                <th>Создана</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => {
                const status = STATUS_MAP[task.status] || STATUS_MAP.pending;
                const processed = task.processed_urls || 0;
                const total = task.total_urls || 0;
                const pct = total > 0 ? Math.round((processed / total) * 100) : 0;

                return (
                  <tr key={task.id} onClick={() => onSelectTask(task.id)}>
                    <td className="task-id">{task.id?.slice(0, 8)}</td>
                    <td>
                      <span
                        className="status-badge"
                        style={{ backgroundColor: status.color }}
                      >
                        {status.icon} {status.label}
                      </span>
                    </td>
                    <td>{task.mode === "mode_1" ? "🎯 Режим 1" : "📊 Режим 2"}</td>
                    <td>
                      <div className="progress-cell">
                        <div className="progress-bar-mini">
                          <div
                            className="progress-fill-mini"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="progress-text-mini">
                          {processed}/{total} ({pct}%)
                        </span>
                      </div>
                    </td>
                    <td className="contacts-count">{task.found_contacts || 0}</td>
                    <td className="errors-count">{task.errors_count || 0}</td>
                    <td className="created-at">
                      {task.created_at
                        ? new Date(task.created_at).toLocaleString("ru")
                        : "—"}
                    </td>
                    <td>
                      <button className="btn-icon" title="Открыть">→</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
