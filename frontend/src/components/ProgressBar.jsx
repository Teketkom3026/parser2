import React from "react";

const STATUS_COLORS = {
  pending: "#6c757d",
  running: "#0d6efd",
  paused: "#ffc107",
  completed: "#198754",
  cancelled: "#dc3545",
  failed: "#dc3545",
};

const STATUS_LABELS = {
  pending: "Ожидание",
  running: "Выполняется",
  paused: "На паузе",
  completed: "Завершено",
  cancelled: "Отменено",
  failed: "Ошибка",
};

export default function ProgressBar({ progress }) {
  const { status, processed, total } = progress;
  const pct = total > 0 ? Math.round((processed / total) * 100) : 0;
  const color = STATUS_COLORS[status] || STATUS_COLORS.pending;
  const label = STATUS_LABELS[status] || status;

  return (
    <div className="progress-section">
      <div className="progress-header">
        <span
          className="progress-status"
          style={{ color }}
        >
          {label}
        </span>
        <span className="progress-pct">{pct}%</span>
      </div>
      <div className="progress-bar">
        <div
          className={`progress-fill ${status === "running" ? "animated" : ""}`}
          style={{
            width: `${pct}%`,
            backgroundColor: color,
          }}
        />
      </div>
      <div className="progress-footer">
        <span>{processed} / {total} URL</span>
      </div>
    </div>
  );
}
