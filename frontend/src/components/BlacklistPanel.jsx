import React, { useState, useEffect, useCallback } from "react";

const API = import.meta.env.VITE_API_URL || "";

export default function BlacklistPanel() {
  const [entries, setEntries] = useState([]);
  const [entryType, setEntryType] = useState("domain");
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [bulkText, setBulkText] = useState("");
  const [showBulk, setShowBulk] = useState(false);

  const fetchEntries = useCallback(async () => {
    try {
      const resp = await fetch(`${API}/api/blacklist`);
      if (resp.ok) {
        const data = await resp.json();
        setEntries(data.entries || []);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEntries();
  }, [fetchEntries]);

  const handleAdd = async (e) => {
    e.preventDefault();
    setError("");

    if (!value.trim()) {
      setError("Значение не может быть пустым");
      return;
    }

    try {
      const formData = new FormData();
      formData.append("entry_type", entryType);
      formData.append("value", value.trim());

      const resp = await fetch(`${API}/api/blacklist`, {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || "Ошибка добавления");
      }

      setValue("");
      fetchEntries();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleBulkAdd = async () => {
    setError("");

    const lines = bulkText
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0);

    if (lines.length === 0) {
      setError("Введите значения (по одному на строку)");
      return;
    }

    const batchEntries = lines.map((line) => ({
      entry_type: entryType,
      value: line,
    }));

    try {
      const resp = await fetch(`${API}/api/blacklist/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entries: batchEntries }),
      });

      if (!resp.ok) {
        throw new Error("Ошибка массового добавления");
      }

      setBulkText("");
      setShowBulk(false);
      fetchEntries();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async (id) => {
    try {
      await fetch(`${API}/api/blacklist/${id}`, { method: "DELETE" });
      fetchEntries();
    } catch {
      // ignore
    }
  };

  return (
    <div className="card">
      <h2>🚫 Blacklist</h2>
      <p className="hint">
        Email и домены из blacklist будут исключены из результатов парсинга.
      </p>

      {/* Форма добавления */}
      <form onSubmit={handleAdd} className="blacklist-form">
        <select
          className="input select-type"
          value={entryType}
          onChange={(e) => setEntryType(e.target.value)}
        >
          <option value="domain">Домен</option>
          <option value="email">Email</option>
        </select>

        <input
          type="text"
          className="input blacklist-input"
          placeholder={entryType === "domain" ? "example.com" : "spam@example.com"}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />

        <button type="submit" className="btn-primary">
          ➕ Добавить
        </button>

        <button
          type="button"
          className="btn-secondary"
          onClick={() => setShowBulk(!showBulk)}
        >
          📋 Массово
        </button>
      </form>

      {/* Массовое добавление */}
      {showBulk && (
        <div className="bulk-section">
          <textarea
            className="textarea"
            rows={5}
            placeholder={"Введите по одному на строку:\nexample.com\nspam.ru\njunk.org"}
            value={bulkText}
            onChange={(e) => setBulkText(e.target.value)}
          />
          <button className="btn-primary" onClick={handleBulkAdd}>
            📥 Добавить все
          </button>
        </div>
      )}

      {error && <div className="error-msg">❌ {error}</div>}

      {/* Список */}
      {loading ? (
        <div className="loading">Загрузка...</div>
      ) : entries.length === 0 ? (
        <div className="empty-state">Blacklist пуст</div>
      ) : (
        <div className="blacklist-list">
          <div className="blacklist-header-row">
            <span>Тип</span>
            <span>Значение</span>
            <span>Добавлено</span>
            <span></span>
          </div>
          {entries.map((entry) => (
            <div key={entry.id} className="blacklist-row">
              <span className="bl-type">
                {entry.entry_type === "domain" ? "🌐" : "📧"} {entry.entry_type}
              </span>
              <span className="bl-value">{entry.value}</span>
              <span className="bl-date">
                {entry.created_at
                  ? new Date(entry.created_at).toLocaleDateString("ru")
                  : "—"}
              </span>
              <button
                className="btn-icon btn-delete"
                onClick={() => handleDelete(entry.id)}
                title="Удалить"
              >
                🗑
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
