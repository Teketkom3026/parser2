import React, { useState, useRef } from 'react';
import { useApi } from '../hooks/useApi';

export default function FileUpload({ onTaskCreated }) {
  const { uploadAndStart, loading, error } = useApi();
  const [file, setFile] = useState(null);
  const [mode, setMode] = useState('mode_2');
  const [positions, setPositions] = useState('');
  const [dragover, setDragover] = useState(false);
  const inputRef = useRef();

  const handleDrop = (e) => {
    e.preventDefault();
    setDragover(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) return;

    try {
      const result = await uploadAndStart(file, mode, positions);
      if (result?.task_id) {
        onTaskCreated(result.task_id);
      }
    } catch {
      // error уже в state
    }
  };

  return (
    <div className="card">
      <h2 className="card-title">📁 Загрузить файл с URL</h2>
      <p style={{ color: 'var(--text-secondary)', marginBottom: 16, fontSize: 14 }}>
        Загрузите Excel или CSV файл со списком сайтов
      </p>

      <form onSubmit={handleSubmit}>
        <div
          className={`file-dropzone ${dragover ? 'dragover' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragover(true); }}
          onDragLeave={() => setDragover(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
        >
          <div className="file-dropzone-icon">📄</div>
          {file ? (
            <div>
              <strong>{file.name}</strong>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {(file.size / 1024).toFixed(1)} КБ
              </p>
            </div>
          ) : (
            <div>
              <p><strong>Перетащите файл</strong> или кликните для выбора</p>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                Поддерживаются .xlsx, .xls, .csv
              </p>
            </div>
          )}
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx,.xls,.csv"
            style={{ display: 'none' }}
            onChange={(e) => setFile(e.target.files[0] || null)}
          />
        </div>

        <div className="form-group" style={{ marginTop: 16 }}>
          <label>Режим парсинга</label>
          <select
            className="form-select"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="mode_2">Режим 2 — Все контакты</option>
            <option value="mode_1">Режим 1 — По должностям</option>
          </select>
        </div>

        {mode === 'mode_1' && (
          <div className="form-group">
            <label>Целевые должности (через запятую)</label>
            <input
              className="form-input"
              type="text"
              value={positions}
              onChange={(e) => setPositions(e.target.value)}
              placeholder="директор, CEO, руководитель"
            />
          </div>
        )}

        {error && <div className="alert alert-error">{error}</div>}

        <button className="btn btn-primary" type="submit" disabled={loading || !file}>
          {loading ? '⏳ Загрузка...' : '🚀 Загрузить и начать'}
        </button>

        {file && (
          <button
            type="button"
            className="btn btn-outline"
            style={{ marginLeft: 8 }}
            onClick={() => setFile(null)}
          >
            ✕ Убрать файл
          </button>
        )}
      </form>
    </div>
  );
}
