"""
AI Knowledge Chatbot — FastAPI Backend
Main entry point with CORS configuration and router mounting.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.sessions import router as sessions_router
from routes.sources import router as sources_router
from routes.chat import router as chat_router
from routes.quiz import router as quiz_router

app = FastAPI(
    title="AI Knowledge Chatbot",
    description="RAG-powered chatbot that answers questions from uploaded documents",
    version="1.0.0",
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://multi-source-ai-learning-assistant.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(sessions_router)
app.include_router(sources_router)
app.include_router(chat_router)
app.include_router(quiz_router)


@app.get("/")
async def root():
    return {
        "name": "AI Knowledge Chatbot API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
