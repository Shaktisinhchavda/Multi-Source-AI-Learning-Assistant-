"use client";

import React, { useRef, useEffect, useState, useCallback } from "react";
import type { SourceRef } from "@/lib/api";
import { streamChat } from "@/lib/api";
import MessageBubble from "./MessageBubble";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
  isStreaming?: boolean;
}

interface ChatPanelProps {
  sessionId: string | null;
  hasSourcesReady: boolean;
  onError: (message: string) => void;
}

export default function ChatPanel({
  sessionId,
  hasSourcesReady,
  onError,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
  };

  const handleSend = useCallback(async () => {
    const message = inputValue.trim();
    if (!message || !sessionId || isLoading) return;

    if (!hasSourcesReady) {
      onError("Please upload at least one document before chatting.");
      return;
    }

    // Add user message
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: message,
    };

    // Add placeholder assistant message
    const assistantMsg: ChatMessage = {
      id: `assistant-${Date.now()}`,
      role: "assistant",
      content: "",
      sources: [],
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInputValue("");
    setIsLoading(true);

    // Reset textarea height
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
    }

    // Stream response
    abortRef.current = streamChat(sessionId, message, {
      onSources: (sources) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id ? { ...m, sources } : m
          )
        );
      },
      onToken: (token) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id
              ? { ...m, content: m.content + token }
              : m
          )
        );
      },
      onDone: () => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id ? { ...m, isStreaming: false } : m
          )
        );
        setIsLoading(false);
      },
      onError: (error) => {
        onError(error.message);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id
              ? {
                  ...m,
                  content:
                    "Sorry, something went wrong. Please try again.",
                  isStreaming: false,
                }
              : m
          )
        );
        setIsLoading(false);
      },
    });
  }, [inputValue, sessionId, isLoading, hasSourcesReady, onError]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-panel">
      {/* Messages */}
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-welcome">
            <div className="chat-welcome-icon">
              <span className="chat-welcome-sparkle">✦</span>
              🧠
              <span className="chat-welcome-sparkle">✦</span>
            </div>
            <h2>
              Knowledge<span style={{ color: "var(--accent-red)" }}>Bot</span>
            </h2>
            <p>
              Upload your documents, paste URLs, and ask anything. I&apos;ll answer
              using only your content — with source citations.
            </p>
            <div className="chat-welcome-steps">
              <div className="chat-welcome-step">
                <div className="chat-welcome-step-number">1</div>
                <div className="chat-welcome-step-text">
                  Upload a PDF or paste a URL
                </div>
              </div>
              <div className="chat-welcome-step">
                <div className="chat-welcome-step-number">2</div>
                <div className="chat-welcome-step-text">
                  Wait for processing to complete
                </div>
              </div>
              <div className="chat-welcome-step">
                <div className="chat-welcome-step-number">3</div>
                <div className="chat-welcome-step-text">
                  Ask questions about your content
                </div>
              </div>
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              role={msg.role}
              content={msg.content}
              sources={msg.sources}
              isStreaming={msg.isStreaming}
            />
          ))
        )}

        {/* Typing indicator */}
        {isLoading &&
          messages.length > 0 &&
          messages[messages.length - 1]?.content === "" && (
            <div className="message assistant">
              <div className="message-avatar">AI</div>
              <div className="typing-indicator">
                <div className="typing-dot" />
                <div className="typing-dot" />
                <div className="typing-dot" />
              </div>
            </div>
          )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="chat-input-area">
        <div className="chat-input-wrapper">
          <textarea
            ref={inputRef}
            className="chat-input"
            placeholder={
              hasSourcesReady
                ? "Ask a question about your uploaded content..."
                : "Upload a document first to start chatting..."
            }
            value={inputValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={isLoading || !hasSourcesReady}
            rows={1}
            id="chat-input"
          />
          <button
            className="chat-send-btn"
            onClick={handleSend}
            disabled={!inputValue.trim() || isLoading || !hasSourcesReady}
            id="chat-send-btn"
            title="Send message"
          >
            ↑
          </button>
        </div>
        <div className="chat-input-hint">
          Press Enter to send · Shift+Enter for new line
        </div>
      </div>
    </div>
  );
}
