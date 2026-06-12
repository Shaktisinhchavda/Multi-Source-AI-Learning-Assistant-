"use client";

import React, { useState, useEffect, useCallback } from "react";
import { createSession } from "@/lib/api";
import type { Source } from "@/lib/api";
import SourceUpload from "@/components/SourceUpload";
import ChatPanel from "@/components/ChatPanel";

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
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
          {sessionId && (
            <span className="header-session-id">
              {sessionId.slice(0, 8)}...
            </span>
          )}
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

        {/* Chat Panel */}
        <ChatPanel
          sessionId={sessionId}
          hasSourcesReady={hasSourcesReady}
          onError={handleError}
        />
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
