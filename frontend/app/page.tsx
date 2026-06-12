"use client";

import React, { useState, useEffect, useCallback } from "react";
import { createSession } from "@/lib/api";
import type { Source } from "@/lib/api";
import SourceUpload from "@/components/SourceUpload";
import ChatPanel from "@/components/ChatPanel";
import QuizMode from "@/components/QuizMode";

type AppMode = "chat" | "quiz";

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [mode, setMode] = useState<AppMode>("chat");
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
  } | null>(null);

  // Initialize session on mount
  useEffect(() => {
    initSession();
  }, []);

  // Auto-dismiss toast
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  const initSession = async () => {
    try {
      const session = await createSession();
      setSessionId(session.id);
    } catch (err) {
      showToast(
        err instanceof Error
          ? err.message
          : "Failed to connect to server. Is the backend running?",
        "error"
      );
    }
  };

  const handleNewSession = async () => {
    setSources([]);
    setSessionId(null);
    setMode("chat");
    await initSession();
    showToast("New session started!", "success");
  };

  const handleSourceAdded = useCallback((source: Source) => {
    setSources((prev) => [...prev, source]);
    showToast(`${source.source_name} processed successfully!`, "success");
  }, []);

  const showToast = (message: string, type: "success" | "error") => {
    setToast({ message, type });
  };

  const handleError = useCallback((message: string) => {
    showToast(message, "error");
  }, []);

  const hasSourcesReady = sources.some((s) => s.status === "ready");

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <div className="header-logo">
          <div className="header-logo-icon">K</div>
          <h1 className="header-title">
            Knowledge<span>Bot</span>
          </h1>
        </div>
        <div className="header-session">
          {/* Mode Toggle */}
          <div className="mode-toggle">
            <button
              className={`mode-toggle-btn ${mode === "chat" ? "active" : ""}`}
              onClick={() => setMode("chat")}
              id="mode-chat-btn"
            >
              💬 Chat
            </button>
            <button
              className={`mode-toggle-btn ${mode === "quiz" ? "active" : ""}`}
              onClick={() => setMode("quiz")}
              id="mode-quiz-btn"
            >
              🎯 Quiz
            </button>
          </div>
          <button
            className="new-session-btn"
            onClick={handleNewSession}
            id="new-session-btn"
          >
            + New Session
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="main-content">
        {/* Sidebar — Source Upload & Badges */}
        <aside className="sidebar">
          <div className="sidebar-header">
            <div className="sidebar-title">Knowledge Sources</div>
            <div className="sidebar-subtitle">
              Upload documents or paste URLs
            </div>
          </div>
          <SourceUpload
            sessionId={sessionId}
            sources={sources}
            onSourceAdded={handleSourceAdded}
            onError={handleError}
          />
        </aside>

        {/* Chat or Quiz Panel */}
        {mode === "chat" ? (
          <ChatPanel
            sessionId={sessionId}
            hasSourcesReady={hasSourcesReady}
            onError={handleError}
          />
        ) : (
          <div className="chat-panel">
            <QuizMode
              sessionId={sessionId}
              hasSourcesReady={hasSourcesReady}
              onError={handleError}
            />
          </div>
        )}
      </main>

      {/* Toast Notification */}
      {toast && (
        <div className={`toast ${toast.type}`} role="alert">
          {toast.type === "success" ? "✓" : "✗"} {toast.message}
        </div>
      )}
    </div>
  );
}
