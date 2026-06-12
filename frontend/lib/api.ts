/**
 * API client for the AI Knowledge Chatbot backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---- Types ----

export interface Session {
  id: string;
  created_at: string;
  sources: Source[];
}

export interface Source {
  id: string;
  session_id: string;
  source_type: "pdf" | "pptx" | "youtube" | "webpage";
  source_name: string;
  summary: string | null;
  chunk_count: number;
  status: "processing" | "ready" | "error";
  error_message?: string;
  created_at: string;
}

export interface Message {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  sources: SourceRef[];
  created_at: string;
}

export interface SourceRef {
  source_name: string;
  source_type: string;
  source_ref: string;
}

export interface ChatResponse {
  response: string;
  sources: SourceRef[];
}

export interface UploadResult {
  source_id: string;
  source_name: string;
  source_type: string;
  status: string;
  summary: string;
  chunk_count: number;
  page_count: number;
}

// ---- Session API ----

export async function createSession(): Promise<Session> {
  const res = await fetch(`${API_BASE}/api/sessions`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to create session: ${res.statusText}`);
  return res.json();
}

export async function getSession(
  sessionId: string
): Promise<{ session: Session; sources: Source[] }> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to get session: ${res.statusText}`);
  return res.json();
}

export async function getHistory(sessionId: string): Promise<Message[]> {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/history`);
  if (!res.ok) throw new Error(`Failed to get history: ${res.statusText}`);
  const data = await res.json();
  return data.messages;
}

// ---- Source Upload API ----

export async function uploadFile(
  sessionId: string,
  file: File,
  onProgress?: (percent: number) => void
): Promise<UploadResult> {
  const formData = new FormData();
  formData.append("session_id", sessionId);
  formData.append("file", file);

  // Use XMLHttpRequest for progress tracking
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/api/sources/upload`);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || `Upload failed: ${xhr.statusText}`));
        } catch {
          reject(new Error(`Upload failed: ${xhr.statusText}`));
        }
      }
    };

    xhr.onerror = () => reject(new Error("Upload failed: network error"));
    xhr.send(formData);
  });
}

export async function addUrlSource(
  sessionId: string,
  url: string,
  sourceType: "youtube" | "webpage"
): Promise<UploadResult> {
  const res = await fetch(`${API_BASE}/api/sources/url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      url,
      source_type: sourceType,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to add URL: ${res.statusText}`);
  }
  return res.json();
}

// ---- Chat API ----

export interface StreamCallbacks {
  onSources: (sources: SourceRef[]) => void;
  onToken: (token: string) => void;
  onDone: () => void;
  onError: (error: Error) => void;
}

export function streamChat(
  sessionId: string,
  message: string,
  callbacks: StreamCallbacks
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message,
          stream: true,
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Chat failed: ${res.statusText}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith("data: ")) continue;

          const jsonStr = trimmed.slice(6);
          try {
            const parsed = JSON.parse(jsonStr);
            if (parsed.type === "sources") {
              callbacks.onSources(parsed.data);
            } else if (parsed.type === "token") {
              callbacks.onToken(parsed.data);
            } else if (parsed.type === "done") {
              callbacks.onDone();
            }
          } catch {
            // Skip malformed lines
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== "AbortError") {
        callbacks.onError(err);
      }
    }
  })();

  return controller;
}
