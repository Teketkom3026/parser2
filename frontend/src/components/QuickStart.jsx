import React, { useState } from 'react';
import { useApi } from '../hooks/useApi';

export default function QuickStart({ onTaskCreated }) {
  const { quickStart, loading, error } = useApi();
  const [url, setUrl] = useState('');
  const [mode, setMode] = useState('mode_2');
  const [positions, setPositions] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;

    try {
      const posArray = positions
        ? positions.split(',').map((p) => p.trim()).filter(Boolean)
        : [];
      const result = await quickStart(url.trim(), mode, posArray);
      if (result?.task_id) {
        onTaskCreated(result.task_id);
      }
    } catch {
      // error уже в state
    }
  };

  return (
    <div className="card">
      <h2 className="card-title">⚡ Быстрый старт</h2>
      <p style={{ color: 'var(--text-secondary)', marginBottom: 16, fontSize: 14 }}>
        Введите URL сайта для сбора контактов
      </p>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>URL сайта</label>
          <input
            className="form-input"
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com"
            required
          />
        </div>

        <div className="form-group">
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

        <button className="btn btn-primary" type="submit" disabled={loading || !url.trim()}>
          {loading ? '⏳ Запуск...' : '🚀 Начать парсинг'}
        </button>
      </form>
    </div>
  );
}
