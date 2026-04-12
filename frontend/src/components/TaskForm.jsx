import React, { useState, useRef } from "react";

const API = import.meta.env.VITE_API_URL || "";

export default function TaskForm({ onTaskCreated }) {
  const [mode, setMode] = useState("mode_2");
  const [urlsText, setUrlsText] = useState("");
  const [positions, setPositions] = useState("");
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append("mode", mode);

      if (file) {
        formData.append("file", file);
      } else if (urlsText.trim()) {
        formData.append("urls", urlsText.trim());
      } else {
        setError("Укажите URL или загрузите файл");
        setLoading(false);
        return;
      }

      if (mode === "mode_1" && positions.trim()) {
        formData.append("positions", positions.trim());
      }

      const resp = await fetch(`${API}/api/tasks`, {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `Ошибка ${resp.status}`);
      }

      const data = await resp.json();
      onTaskCreated(data.task_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleFileDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer?.files?.[0];
    if (f) setFile(f);
  };

  return (
    <div className="card">
      <h2>Новая задача парсинга</h2>

      <form onSubmit={handleSubmit}>
        {/* Режим */}
        <div className="form-group">
          <label>Режим работы</label>
          <div className="mode-selector">
            <button
              type="button"
              className={`mode-btn ${mode === "mode_1" ? "active" : ""}`}
              onClick={() => setMode("mode_1")}
            >
              <span className="mode-icon">🎯</span>
              <span className="mode-title">Режим 1</span>
              <span className="mode-desc">Поиск конкретных должностей</span>
            </button>
            <button
              type="button"
              className={`mode-btn ${mode === "mode_2" ? "active" : ""}`}
              onClick={() => setMode("mode_2")}
            >
              <span className="mode-icon">📊</span>
              <span className="mode-title">Режим 2</span>
              <span className="mode-desc">Сбор всех контактов</span>
            </button>
          </div>
        </div>

        {/* Должности (mode_1) */}
        {mode === "mode_1" && (
          <div className="form-group">
            <label>Целевые должности (через запятую)</label>
            <input
              type="text"
              className="input"
              placeholder="директор, руководитель, менеджер по продажам"
              value={positions}
              onChange={(e) => setPositions(e.target.value)}
            />
          </div>
        )}

        {/* URL */}
        <div className="form-group">
          <label>Список URL (по одному на строку)</label>
          <textarea
            className="textarea"
            rows={6}
            placeholder={"example.com\ncompany.ru\nhttps://site.org"}
            value={urlsText}
            onChange={(e) => setUrlsText(e.target.value)}
            disabled={!!file}
          />
        </div>

        {/* Или файл */}
        <div className="form-group">
          <label>Или загрузите файл (Excel / CSV)</label>
          <div
            className={`dropzone ${file ? "has-file" : ""}`}
            onClick={() => fileRef.current?.click()}
            onDrop={handleFileDrop}
            onDragOver={(e) => e.preventDefault()}
          >
            {file ? (
              <div className="dropzone-file">
                <span>📄 {file.name}</span>
                <button
                  type="button"
                  className="btn-remove"
                  onClick={(e) => {
                    e.stopPropagation();
                    setFile(null);
                  }}
                >
                  ✕
                </button>
              </div>
            ) : (
              <div className="dropzone-placeholder">
                <span className="dropzone-icon">📁</span>
                <span>Перетащите файл или нажмите для выбора</span>
                <span className="dropzone-hint">.xlsx, .xls, .csv</span>
              </div>
            )}
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              hidden
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </div>
        </div>

        {error && <div className="error-msg">❌ {error}</div>}

        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? "⏳ Создание..." : "🚀 Запустить парсинг"}
        </button>
      </form>
    </div>
  );
}
