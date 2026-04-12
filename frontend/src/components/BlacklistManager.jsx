import React, { useState, useEffect } from 'react';
import { useApi } from '../hooks/useApi';

export default function BlacklistManager() {
  const api = useApi();
  const [entries, setEntries] = useState([]);
  const [entryType, setEntryType] = useState('email');
  const [value, setValue] = useState('');
  const [bulkText, setBulkText] = useState('');
  const [showBulk, setShowBulk] = useState(false);

  const fetchEntries = async () => {
    try {
      const data = await api.getBlacklist();
      setEntries(data.entries || []);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    fetchEntries();
  }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!value.trim()) return;
    try {
      await api.addBlacklistEntry(entryType, value.trim());
      setValue('');
      fetchEntries();
    } catch { /* ignore */ }
  };

  const handleDelete = async (id) => {
    try {
      await api.deleteBlacklistEntry(id);
      fetchEntries();
    } catch { /* ignore */ }
  };

  const handleBulkAdd = async () => {
    const lines = bulkText.split('\n').filter((l) => l.trim());
    if (lines.length === 0) return;

    const parsed = lines.map((line) => {
      const trimmed = line.trim().toLowerCase();
      const isEmail = trimmed.includes('@');
      return {
        entry_type: isEmail ? 'email' : 'domain',
        value: trimmed,
      };
    });

    try {
      await api.addBlacklistEntry; // unused, use batch
      // Batch
      const form = { entries: parsed };
      const res = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/blacklist/batch`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(form),
        }
      );
      if (res.ok) {
        setBulkText('');
        setShowBulk(false);
        fetchEntries();
      }
    } catch { /* ignore */ }
  };

  return (
    <div className="card">
      <h2 className="card-title">🚫 Blacklist</h2>
      <p style={{ color: 'var(--text-secondary)', marginBottom: 16, fontSize: 14 }}>
        Email и домены, которые будут исключены из результатов
      </p>

      {/* Форма добавления */}
      <form onSubmit={handleAdd} style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <select
          className="form-select"
          style={{ width: 120 }}
          value={entryType}
          onChange={(e) => setEntryType(e.target.value)}
        >
          <option value="email">Email</option>
          <option value="domain">Домен</option>
        </select>
        <input
          className="form-input"
          style={{ flex: 1, minWidth: 200 }}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={entryType === 'email' ? 'user@example.com' : 'example.com'}
        />
        <button className="btn btn-primary btn-sm" type="submit" disabled={!value.trim()}>
          + Добавить
        </button>
        <button
          type="button"
          className="btn btn-outline btn-sm"
          onClick={() => setShowBulk(!showBulk)}
        >
          📋 Массовое добавление
        </button>
      </form>

      {/* Массовое добавление */}
      {showBulk && (
        <div style={{ marginBottom: 16 }}>
          <textarea
            className="form-input"
            rows={6}
            value={bulkText}
            onChange={(e) => setBulkText(e.target.value)}
            placeholder={"Введите по одному значению на строку:\nspam@example.com\nbaddomain.com\nuser@test.org"}
          />
          <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
            <button className="btn btn-primary btn-sm" onClick={handleBulkAdd}>
              Добавить все
            </button>
            <button className="btn btn-outline btn-sm" onClick={() => setShowBulk(false)}>
              Отмена
            </button>
          </div>
        </div>
      )}

      {api.error && <div className="alert alert-error">{api.error}</div>}

      {/* Таблица */}
      {entries.length === 0 ? (
        <p style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: 24 }}>
          Blacklist пуст
        </p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Тип</th>
                <th>Значение</th>
                <th>Добавлен</th>
                <th style={{ width: 80 }}>Действие</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id}>
                  <td>
                    <span className={`badge ${entry.entry_type === 'email' ? 'badge-running' : 'badge-paused'}`}>
                      {entry.entry_type}
                    </span>
                  </td>
                  <td>{entry.value}</td>
                  <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                    {entry.created_at ? new Date(entry.created_at).toLocaleDateString('ru-RU') : '—'}
                  </td>
                  <td>
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={() => handleDelete(entry.id)}
                    >
                      🗑️
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
            Всего: {entries.length}
          </p>
        </div>
      )}
    </div>
  );
}
