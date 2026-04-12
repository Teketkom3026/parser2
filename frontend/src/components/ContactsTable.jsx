import React, { useState } from "react";

export default function ContactsTable({ contacts }) {
  const [search, setSearch] = useState("");
  const [sortField, setSortField] = useState("");
  const [sortDir, setSortDir] = useState("asc");

  if (!contacts || contacts.length === 0) {
    return <div className="empty-state">Контакты не найдены</div>;
  }

  // Фильтрация
  let filtered = contacts;
  if (search.trim()) {
    const q = search.toLowerCase();
    filtered = contacts.filter((c) =>
      Object.values(c).some(
        (v) => v && String(v).toLowerCase().includes(q)
      )
    );
  }

  // Сортировка
  if (sortField) {
    filtered = [...filtered].sort((a, b) => {
      const va = (a[sortField] || "").toString().toLowerCase();
      const vb = (b[sortField] || "").toString().toLowerCase();
      const cmp = va.localeCompare(vb);
      return sortDir === "asc" ? cmp : -cmp;
    });
  }

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  };

  const sortIcon = (field) => {
    if (sortField !== field) return "";
    return sortDir === "asc" ? " ↑" : " ↓";
  };

  const columns = [
    { key: "company_name", label: "Компания" },
    { key: "site_url", label: "Сайт" },
    { key: "person_name", label: "ФИО" },
    { key: "position_norm", label: "Должность" },
    { key: "role_category", label: "Категория" },
    { key: "person_email", label: "Email персоны" },
    { key: "company_email", label: "Email компании" },
    { key: "company_phone", label: "Телефон" },
    { key: "inn", label: "ИНН" },
  ];

  return (
    <div className="contacts-panel">
      <div className="contacts-toolbar">
        <input
          type="text"
          className="input search-input"
          placeholder="🔍 Поиск по контактам..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span className="contacts-count">
          {filtered.length} из {contacts.length}
        </span>
      </div>

      <div className="table-wrapper">
        <table className="contacts-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className="sortable"
                >
                  {col.label}{sortIcon(col.key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 200).map((c, i) => (
              <tr key={i}>
                <td>{c.company_name || "—"}</td>
                <td className="url-cell">
                  {c.site_url ? (
                    <a href={c.site_url} target="_blank" rel="noopener noreferrer">
                      {c.site_url.replace(/^https?:\/\//, "").slice(0, 30)}
                    </a>
                  ) : "—"}
                </td>
                <td>{c.person_name || "—"}</td>
                <td>{c.position_norm || c.position_raw || "—"}</td>
                <td>
                  {c.role_category ? (
                    <span className="role-badge">{c.role_category}</span>
                  ) : "—"}
                </td>
                <td className="email-cell">{c.person_email || "—"}</td>
                <td className="email-cell">{c.company_email || "—"}</td>
                <td>{c.company_phone || c.person_phone || "—"}</td>
                <td>{c.inn || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {filtered.length > 200 && (
        <div className="table-footer">
          Показано 200 из {filtered.length}. Скачайте Excel для полного списка.
        </div>
      )}
    </div>
  );
}
