# KnowledgeBot: Multi-Source AI Learning Assistant

KnowledgeBot is a web-based AI chatbot that helps users learn from their own study material. Users can upload or link multiple knowledge sources in one session, ask questions about that material, request simple explanations, and generate quizzes from the loaded content.

The application follows a retrieval-augmented generation (RAG) workflow: each source is parsed, chunked, embedded, stored in Supabase with pgvector, and retrieved before calling the selected LLM. Answers are grounded in the provided sources and include citations such as PDF pages, slide numbers, webpage sections, or video timestamps where available.

Live application: https://multi-source-ai-learning-assistant.vercel.app

## Assignment Coverage

| Requirement | Implementation |
| --- | --- |
| FastAPI backend | Python backend built with FastAPI and modular route/processors/RAG packages |
| React / Next.js frontend | Next.js App Router frontend with a clean chat interface and source management UI |
| Supabase | Stores sessions, sources, messages, chunks, and vector embeddings |
| LLM integration | Supports local Ollama for development and Gemini for production-style usage |
| PDF support | Extracts text, chunks content, and stores page-aware metadata |
| PowerPoint support | Parses PPTX slides and preserves slide-level references |
| YouTube support | Extracts transcript content where available and stores timestamp metadata |
| Public webpage support | Scrapes and parses webpage text for retrieval |
| Multiple sources per session | Users can combine PDFs, PPTX files, YouTube URLs, and webpages in one chat session |
| Grounded answers | Chat responses are generated only from retrieved source chunks |
| Source citations | Answers return references to the content used |
| Streaming responses | Chat replies stream token by token from the backend |
| Session memory | Conversation history is stored for the active session |
| Quiz mode | Generates source-aware quiz questions from loaded content |
| Source summaries | Each processed source returns a short summary |

## Core Features

- Multi-source ingestion for PDF, PPTX, YouTube URLs, and public webpage URLs.
- Retrieval-based answering using chunked content and vector similarity search.
- Source-grounded citations for user-facing answers.
- Streaming chat responses using server-sent events.
- Session-scoped chat history for natural follow-up questions.
- Source badges that show loaded content and processing status.
- Quiz generation and answer checking based on uploaded or linked sources.
- Out-of-scope handling when the answer is not supported by the provided material.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, CSS |
| Backend | FastAPI, Python 3.11, uv |
| Database | Supabase PostgreSQL with pgvector |
| Local LLM | Ollama chat and embedding models |
| Cloud LLM | Google Gemini chat and embedding models |
| Retrieval | Chunking, embeddings, Supabase vector search |
| Streaming | Server-sent events from FastAPI to the frontend |

## Project Structure

```text
AS-1/
|-- assignment.md
|-- image.png
|-- README.md
|-- backend/
|   |-- main.py
|   |-- config.py
|   |-- schema.sql
|   |-- pyproject.toml
|   |-- .env.example
|   |-- processors/
|   |   |-- chunker.py
|   |   |-- pdf.py
|   |   |-- pptx.py
|   |   |-- webpage.py
|   |   `-- youtube.py
|   |-- rag/
|   |   |-- chat.py
|   |   |-- embeddings.py
|   |   |-- gemini.py
|   |   `-- vectorstore.py
|   `-- routes/
|       |-- chat.py
|       |-- quiz.py
|       |-- sessions.py
|       `-- sources.py
`-- frontend/
    |-- app/
    |   |-- globals.css
    |   |-- layout.tsx
    |   `-- page.tsx
    |-- components/
    |   |-- ChatPanel.tsx
    |   |-- MessageBubble.tsx
    |   |-- QuizMode.tsx
    |   |-- SourceBadge.tsx
    |   `-- SourceUpload.tsx
    `-- lib/
        `-- api.ts
```

## How It Works

1. A user creates a session in the frontend.
2. The user uploads a PDF/PPTX file or submits a YouTube/webpage URL.
3. The backend extracts text and source metadata from the submitted content.
4. Extracted text is split into chunks and embedded.
5. Chunks and embeddings are stored in Supabase.
6. During chat, the backend retrieves the most relevant chunks for the question.
7. The LLM receives only the retrieved context plus session history.
8. The answer streams back to the UI with source references.

## Architectural Decisions

- Separate frontend and backend modules keep the UI, API, document processing, and RAG logic independently maintainable.
- FastAPI was used for the backend because it provides typed request handling, async endpoints, automatic API documentation, and simple support for streaming responses.
- Next.js was used for the frontend to provide a structured React application with reusable components for chat, source upload, source badges, and quiz mode.
- Supabase PostgreSQL with pgvector was selected so source chunks, chat sessions, messages, and embeddings can live in one managed database.
- The system uses retrieval-augmented generation instead of sending full documents to the LLM. This keeps prompts smaller, improves relevance, and satisfies the assignment requirement to retrieve chunks before answering.
- Each supported source type has its own processor module. This keeps PDF, PPTX, YouTube, and webpage parsing isolated while producing a shared chunk format for retrieval.
- Source metadata is preserved during chunking so answers can cite pages, slides, webpages, or timestamps instead of returning unsupported generic responses.
- Chat history is stored per session so follow-up questions can use previous conversation context without mixing data between sessions.
- Streaming is handled from the backend to the frontend so users see answers token by token instead of waiting for a complete response.
- LLM and embedding providers are configurable. Ollama supports local development, while Gemini can be used for hosted or production-style deployments.

## Prerequisites

- Python 3.11 or newer
- uv for Python dependency management
- Node.js 18 or newer
- Supabase project with pgvector enabled
- Ollama for local development, or a Gemini API key for Gemini mode

## Supabase Setup

1. Create a Supabase project.
2. Open the Supabase SQL editor.
3. Run the SQL in `backend/schema.sql`.
4. Copy the project URL and anon key from the Supabase API settings.
5. Add those values to `backend/.env`.

## Backend Setup

```bash
cd backend
uv sync
cp .env.example .env
uv run uvicorn main:app --reload --port 8000
```

The API will run at:

```text
http://localhost:8000
```

Useful backend endpoints:

- `GET /health` - health check
- `POST /api/sessions` - create a session
- `POST /api/sources/upload` - upload PDF or PPTX files
- `POST /api/sources/url` - add YouTube or webpage URLs
- `POST /api/chat` - ask questions with optional streaming
- `POST /api/quiz/generate` - generate source-based quiz questions

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend will run at:

```text
http://localhost:3000
```

If the backend is not running on `http://localhost:8000`, set this in the frontend environment:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Local LLM Setup with Ollama

Install Ollama and pull the required local models:

```bash
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
```

Set the backend provider to Ollama:

```bash
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
```

## Gemini Setup

To use Gemini instead of Ollama, configure the backend environment:

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-api-key
GEMINI_CHAT_MODEL=gemini-2.5-flash
GEMINI_EMBED_MODEL=gemini-embedding-001
GEMINI_EMBED_DIMENSIONS=768
```

Keep `GEMINI_EMBED_DIMENSIONS=768` unless the Supabase schema is updated to use a different embedding size.

## Environment Variables

| Variable | Purpose | Required |
| --- | --- | --- |
| `SUPABASE_URL` | Supabase project URL | Yes |
| `SUPABASE_KEY` | Supabase anon key | Yes |
| `LLM_PROVIDER` | Selects `ollama` or `gemini` | Yes |
| `OLLAMA_BASE_URL` | Local Ollama server URL | Required for Ollama |
| `GEMINI_API_KEY` | Gemini API key | Required for Gemini |
| `GEMINI_CHAT_MODEL` | Gemini chat model name | No |
| `GEMINI_EMBED_MODEL` | Gemini embedding model name | No |
| `GEMINI_EMBED_DIMENSIONS` | Embedding vector size for Gemini | No |
| `GEMINI_MAX_RETRIES` | Retry attempts for Gemini API failures | No |
| `GEMINI_RETRY_BASE_SECONDS` | Initial Gemini retry backoff | No |
| `GEMINI_RETRY_MAX_SECONDS` | Maximum Gemini retry backoff | No |
| `FRONTEND_ORIGINS` | Additional comma-separated CORS origins | No |
| `NEXT_PUBLIC_API_URL` | Frontend API base URL | No |

## Development Phases

The assignment asks for phase-wise progress instead of one large commit. The implemented phases are:

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Project foundation, FastAPI backend, Next.js frontend, Supabase schema | Complete |
| 2 | PDF ingestion, chunking, embeddings, and basic RAG chat | Complete |
| 3 | YouTube, PPTX, and webpage processors | Complete |
| 4 | Streaming responses and session memory | Complete |
| 5 | Source summaries, citations, source badges, and out-of-scope handling | Complete |
| 6 | Quiz mode and UI refinement based on the provided reference image | Complete |
| 7 | Gemini provider support and production configuration | Complete |

## Notes and Limitations

- YouTube transcript quality depends on transcript availability for the submitted video.
- Webpage extraction depends on the page being public and parseable by the backend.
- The chatbot is designed to decline answers that are not supported by the uploaded or linked material.
- Deployment requires setting production environment variables and configuring CORS for the deployed frontend domain.

