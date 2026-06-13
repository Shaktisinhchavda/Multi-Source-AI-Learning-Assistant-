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
      const headingMatch = line.match(/^\s*(#{1,3})\s+(.+)/);
      const bulletMatch = line.match(/^[\s]*[-•*]\s+(.+)/);
      const numberedMatch = line.match(/^[\s]*\d+[.)]\s+(.+)/);

      if (headingMatch) {
        flushList();
        const level = headingMatch[1].length;
        const className = `message-heading h${level}`;
        elements.push(
          <div key={`h-${i}`} className={className}>
            {renderInline(headingMatch[2])}
          </div>
        );
      } else if (bulletMatch) {
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

  const groupedSources = React.useMemo(() => {
    const groups = new Map<string, SourceRef[]>();
    for (const source of sources || []) {
      const key = `${source.source_name}|${source.source_type}`;
      const existing = groups.get(key) || [];
      existing.push(source);
      groups.set(key, existing);
    }
    return Array.from(groups.values()).map((group) => {
      const first = group[0];
      const refs = Array.from(
        new Set(group.map((source) => source.source_ref).filter(Boolean))
      );
      return { ...first, refs };
    });
  }, [sources]);

  const isOutOfScopeDecline =
    role === "assistant" &&
    /i couldn'?t find information about that in the provided sources/i.test(
      content
    );

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
        {groupedSources.length > 0 && !isStreaming && !isOutOfScopeDecline && (
          <div className="message-sources">
            {groupedSources.map((s, i) => (
              <span key={i} className="message-source-tag">
                📄 {s.source_name}
                {s.refs.length > 0 ? ` · ${s.refs.slice(0, 3).join(", ")}` : ""}
                {s.refs.length > 3 ? ` +${s.refs.length - 3} more` : ""}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
