"use client";

import React, { useRef, useState, useCallback } from "react";
import type { Source } from "@/lib/api";
import { uploadFile, addUrlSource } from "@/lib/api";
import SourceBadge from "./SourceBadge";

interface SourceUploadProps {
  sessionId: string | null;
  sources: Source[];
  onSourceAdded: (source: Source) => void;
  onError: (message: string) => void;
}

export default function SourceUpload({
  sessionId,
  sources,
  onSourceAdded,
  onError,
}: SourceUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [urlInput, setUrlInput] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const files = e.dataTransfer.files;
      if (files.length > 0) {
        handleFileUpload(files[0]);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sessionId]
  );

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFileUpload(files[0]);
    }
    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleFileUpload = async (file: File) => {
    if (!sessionId) {
      onError("Please wait for session to initialize.");
      return;
    }

    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !["pdf", "pptx"].includes(ext)) {
      onError("Unsupported file type. Please upload PDF or PPTX files.");
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);

    try {
      const result = await uploadFile(sessionId, file, (progress) => {
        setUploadProgress(progress);
      });

      // Create a source object from the result
      const newSource: Source = {
        id: result.source_id,
        session_id: sessionId,
        source_type: result.source_type as Source["source_type"],
        source_name: result.source_name,
        summary: result.summary,
        chunk_count: result.chunk_count,
        status: "ready",
        created_at: new Date().toISOString(),
      };

      onSourceAdded(newSource);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
    }
  };

  const detectUrlType = (url: string): "youtube" | "webpage" => {
    const ytPatterns = [
      /youtube\.com\/watch/,
      /youtu\.be\//,
      /youtube\.com\/embed/,
    ];
    for (const pattern of ytPatterns) {
      if (pattern.test(url)) return "youtube";
    }
    return "webpage";
  };

  const handleUrlSubmit = async () => {
    const url = urlInput.trim();
    if (!url || !sessionId) return;

    setIsUploading(true);
    setUploadProgress(0);

    const sourceType = detectUrlType(url);

    try {
      const result = await addUrlSource(sessionId, url, sourceType);

      const newSource: Source = {
        id: result.source_id,
        session_id: sessionId,
        source_type: result.source_type as Source["source_type"],
        source_name: result.source_name,
        summary: result.summary,
        chunk_count: result.chunk_count,
        status: "ready",
        created_at: new Date().toISOString(),
      };

      onSourceAdded(newSource);
      setUrlInput("");
    } catch (err) {
      onError(err instanceof Error ? err.message : "URL processing failed");
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
    }
  };

  return (
    <>
      {/* Upload Section */}
      <div className="upload-section">
        <div
          className={`upload-dropzone ${isDragging ? "dragging" : ""}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.pptx"
            onChange={handleFileSelect}
            style={{ display: "none" }}
            id="file-upload-input"
          />
          {isUploading ? (
            <>
              <div className="spinner" style={{ margin: "0 auto 8px" }} />
              <div className="upload-dropzone-text">
                Uploading... {uploadProgress}%
              </div>
              <div
                style={{
                  width: "80%",
                  height: "4px",
                  background: "var(--border-color)",
                  borderRadius: "2px",
                  margin: "8px auto 0",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${uploadProgress}%`,
                    height: "100%",
                    background: "var(--accent-red)",
                    borderRadius: "2px",
                    transition: "width 0.3s ease",
                  }}
                />
              </div>
            </>
          ) : (
            <>
              <div className="upload-dropzone-icon">📁</div>
              <div className="upload-dropzone-text">
                Drop a file here or click to upload
              </div>
              <div className="upload-dropzone-hint">
                Supports PDF, PPTX
              </div>
            </>
          )}
        </div>

        {/* URL Input */}
        <div className="url-input-group">
          <div className="url-input-wrapper">
            <input
              type="url"
              className="url-input"
              placeholder="Paste YouTube or webpage URL..."
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleUrlSubmit()}
              id="url-input"
            />
            <button
              className="url-submit-btn"
              onClick={handleUrlSubmit}
              disabled={!urlInput.trim() || !sessionId}
              id="url-submit-btn"
            >
              Add
            </button>
          </div>
        </div>
      </div>

      {/* Loaded Sources */}
      <div className="sidebar-content">
        {sources.length > 0 ? (
          <>
            <div className="sidebar-header" style={{ padding: "0 0 12px 0", border: "none" }}>
              <div className="sidebar-title">Loaded Sources</div>
              <div className="sidebar-subtitle">
                {sources.filter((s) => s.status === "ready").length} of{" "}
                {sources.length} ready
              </div>
            </div>
            <div className="sources-list">
              {sources.map((source) => (
                <SourceBadge key={source.id} source={source} />
              ))}
            </div>
          </>
        ) : (
          <div
            style={{
              textAlign: "center",
              padding: "32px 16px",
              color: "var(--text-muted)",
              fontSize: "13px",
            }}
          >
            <div style={{ fontSize: "32px", marginBottom: "8px" }}>📚</div>
            No sources loaded yet.
            <br />
            Upload a file or paste a URL to get started.
          </div>
        )}
      </div>
    </>
  );
}
