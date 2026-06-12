"use client";

import React from "react";
import type { SourceRef } from "@/lib/api";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  sources?: SourceRef[];
  isStreaming?: boolean;
}

export default function MessageBubble({
  role,
  content,
  sources,
  isStreaming,
}: MessageBubbleProps) {
  // Simple markdown-like rendering (bold, code, lists)
  const renderContent = (text: string) => {
    if (!text) return null;

    const lines = text.split("\n");
    const elements: React.ReactNode[] = [];
    let listItems: string[] = [];
    let listType: "ul" | "ol" | null = null;

    const flushList = () => {
      if (listItems.length > 0 && listType) {
        const ListTag = listType;
        elements.push(
          <ListTag key={`list-${elements.length}`}>
            {listItems.map((item, i) => (
              <li key={i}>{renderInline(item)}</li>
            ))}
          </ListTag>
        );
        listItems = [];
        listType = null;
      }
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const bulletMatch = line.match(/^[\s]*[-•*]\s+(.+)/);
      const numberedMatch = line.match(/^[\s]*\d+[.)]\s+(.+)/);

      if (bulletMatch) {
        if (listType !== "ul") flushList();
        listType = "ul";
        listItems.push(bulletMatch[1]);
      } else if (numberedMatch) {
        if (listType !== "ol") flushList();
        listType = "ol";
        listItems.push(numberedMatch[1]);
      } else {
        flushList();
        if (line.trim()) {
          elements.push(<p key={`p-${i}`}>{renderInline(line)}</p>);
        }
      }
    }
    flushList();

    return elements;
  };

  const renderInline = (text: string): React.ReactNode => {
    // Handle **bold**, `code`, and regular text
    const parts: React.ReactNode[] = [];
    const regex = /(\*\*(.+?)\*\*|`(.+?)`)/g;
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.slice(lastIndex, match.index));
      }
      if (match[2]) {
        parts.push(<strong key={match.index}>{match[2]}</strong>);
      } else if (match[3]) {
        parts.push(<code key={match.index}>{match[3]}</code>);
      }
      lastIndex = regex.lastIndex;
    }

    if (lastIndex < text.length) {
      parts.push(text.slice(lastIndex));
    }

    return parts.length === 1 ? parts[0] : <>{parts}</>;
  };

  return (
    <div className={`message ${role}`}>
      <div className="message-avatar">
        {role === "user" ? "U" : "AI"}
      </div>
      <div>
        <div className="message-content">
          {renderContent(content)}
          {isStreaming && (
            <span
              style={{
                display: "inline-block",
                width: "2px",
                height: "16px",
                background: "currentColor",
                marginLeft: "2px",
                animation: "pulse 1s infinite",
                verticalAlign: "text-bottom",
              }}
            />
          )}
        </div>
        {sources && sources.length > 0 && !isStreaming && (
          <div className="message-sources">
            {sources.map((s, i) => (
              <span key={i} className="message-source-tag">
                📄 {s.source_name}
                {s.source_ref ? ` · ${s.source_ref}` : ""}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
