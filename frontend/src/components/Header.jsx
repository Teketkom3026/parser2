import React from "react";

export default function Header({ currentView, onNavigate, onBack }) {
  return (
    <header className="header">
      <div className="header-left">
        <h1 className="logo" onClick={onBack}>
          🔍 Contact Parser
        </h1>
      </div>

      <nav className="header-nav">
        <button
          className={`nav-btn ${currentView === "form" ? "active" : ""}`}
          onClick={() => onNavigate("form")}
        >
          ➕ Новая задача
        </button>
        <button
          className={`nav-btn ${currentView === "tasks" ? "active" : ""}`}
          onClick={() => onNavigate("tasks")}
        >
          📋 Задачи
        </button>
        <button
          className={`nav-btn ${currentView === "blacklist" ? "active" : ""}`}
          onClick={() => onNavigate("blacklist")}
        >
          🚫 Blacklist
        </button>
      </nav>
    </header>
  );
}
