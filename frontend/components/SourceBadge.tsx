"use client";

import React from "react";
import type { Source } from "@/lib/api";

interface SourceBadgeProps {
  source: Source;
}

const typeIcons: Record<string, string> = {
  pdf: "📄",
  pptx: "📊",
  youtube: "🎬",
  webpage: "🌐",
};

const typeLabels: Record<string, string> = {
  pdf: "PDF Document",
  pptx: "PowerPoint",
  youtube: "YouTube Video",
  webpage: "Web Page",
};

export default function SourceBadge({ source }: SourceBadgeProps) {
  const [expanded, setExpanded] = React.useState(false);

  return (
    <div className="source-badge" onClick={() => setExpanded(!expanded)}>
      <div className={`source-badge-icon ${source.source_type}`}>
        {typeIcons[source.source_type] || "📎"}
      </div>
      <div className="source-badge-info">
        <div className="source-badge-name" title={source.source_name}>
          {source.source_name}
        </div>
        <div className="source-badge-type">
          {typeLabels[source.source_type] || source.source_type}
          {source.chunk_count > 0 && ` · ${source.chunk_count} chunks`}
        </div>
        {source.summary && (
          <div className={`source-summary ${expanded ? "expanded" : ""}`}>
            {source.summary}
          </div>
        )}
      </div>
      <span className={`source-badge-status ${source.status}`}>
        {source.status === "processing" && "⏳ Processing"}
        {source.status === "ready" && "✓ Ready"}
        {source.status === "error" && "✗ Error"}
      </span>
    </div>
  );
}
