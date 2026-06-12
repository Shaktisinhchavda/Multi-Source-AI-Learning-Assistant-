"""
Quiz API — generate questions from loaded content and check answers.
"""

import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client
from config import get_settings
from rag.embeddings import embed_query
from rag.vectorstore import search_similar
import httpx

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


class QuizGenerateRequest(BaseModel):
    session_id: str
    num_questions: int = 5


class QuizCheckRequest(BaseModel):
    session_id: str
    question: str
    user_answer: str
    correct_answer: str
    explanation: str = ""


QUIZ_SYSTEM_PROMPT = """You are a quiz generator. Based on the provided source material, generate exactly {num_questions} multiple-choice questions to test the reader's understanding.

Return ONLY valid JSON in this exact format (no markdown, no code blocks):
[
  {{
    "question": "What is...?",
    "options": ["A) First option", "B) Second option", "C) Third option", "D) Fourth option"],
    "correct": "A",
    "explanation": "Brief explanation of why A is correct, citing the source.",
    "source_ref": "page 3"
  }}
]

Rules:
1. Questions must be answerable from the provided material ONLY.
2. Each question must have exactly 4 options (A, B, C, D).
3. Vary difficulty: include easy recall, understanding, and application questions.
4. The "correct" field must be just the letter (A, B, C, or D).
5. Include source references in the explanation.
6. Return ONLY the JSON array, nothing else."""


CHECK_SYSTEM_PROMPT = """You are a quiz evaluator. The user answered a quiz question. Evaluate their answer.

Question: {question}
Correct Answer: {correct_answer}
User's Answer: {user_answer}

Respond with a brief, encouraging evaluation. If they got it right, congratulate them. If wrong, explain the correct answer kindly. Keep it to 2-3 sentences."""


async def _chat_ollama_simple(messages: list[dict]) -> str:
    """Simple non-streaming Ollama chat call."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_chat_model,
                "messages": messages,
                "stream": False,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]


@router.post("/generate")
async def generate_quiz(body: QuizGenerateRequest):
    """
    Generate quiz questions from the loaded sources in a session.
    Uses RAG to retrieve diverse content, then asks LLM to create questions.
    """
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_key)

    # Check sources exist
    sources = (
        client.table("sources")
        .select("id, source_name, source_type")
        .eq("session_id", body.session_id)
        .eq("status", "ready")
        .execute()
    )
    if not sources.data:
        raise HTTPException(
            status_code=400,
            detail="No sources loaded. Please upload documents first.",
        )

    # Retrieve diverse chunks for quiz generation
    # Use a broad query to get varied content
    query_embedding = await embed_query(
        "key concepts main ideas important facts summary overview"
    )
    chunks = await search_similar(
        body.session_id, query_embedding, match_count=15
    )

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="No content found to generate quiz from.",
        )

    # Build context from retrieved chunks
    context_parts = []
    for chunk in chunks:
        ref = f"[{chunk['source_name']}"
        if chunk.get("source_ref"):
            ref += f", {chunk['source_ref']}"
        ref += "]"
        context_parts.append(f"{ref}\n{chunk['content']}")

    context = "\n\n---\n\n".join(context_parts)

    # Generate quiz via LLM
    messages = [
        {
            "role": "system",
            "content": QUIZ_SYSTEM_PROMPT.format(
                num_questions=body.num_questions
            ),
        },
        {
            "role": "user",
            "content": f"Generate {body.num_questions} quiz questions from this material:\n\n{context}",
        },
    ]

    try:
        response_text = await _chat_ollama_simple(messages)

        # Parse JSON from response (handle potential markdown wrapping)
        json_text = response_text.strip()
        if json_text.startswith("```"):
            # Remove markdown code block
            json_text = json_text.split("\n", 1)[1]
            if json_text.endswith("```"):
                json_text = json_text[:-3]
            json_text = json_text.strip()

        questions = json.loads(json_text)

        # Validate structure
        validated = []
        for q in questions:
            if (
                isinstance(q, dict)
                and "question" in q
                and "options" in q
                and "correct" in q
            ):
                validated.append({
                    "question": q["question"],
                    "options": q["options"][:4],
                    "correct": q["correct"],
                    "explanation": q.get("explanation", ""),
                    "source_ref": q.get("source_ref", ""),
                })

        if not validated:
            raise ValueError("No valid questions generated")

        return {"questions": validated, "total": len(validated)}

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Failed to parse quiz questions. Please try again.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Quiz generation failed: {str(e)}",
        )


@router.post("/check")
async def check_answer(body: QuizCheckRequest):
    """
    Check a user's answer and provide feedback.
    """
    messages = [
        {
            "role": "system",
            "content": CHECK_SYSTEM_PROMPT.format(
                question=body.question,
                correct_answer=body.correct_answer,
                user_answer=body.user_answer,
            ),
        },
        {
            "role": "user",
            "content": f"My answer: {body.user_answer}",
        },
    ]

    try:
        feedback = await _chat_ollama_simple(messages)
        is_correct = body.user_answer.strip().upper() == body.correct_answer.strip().upper()

        return {
            "is_correct": is_correct,
            "correct_answer": body.correct_answer,
            "feedback": feedback,
            "explanation": body.explanation,
        }
    except Exception as e:
        # Fallback without LLM
        is_correct = body.user_answer.strip().upper() == body.correct_answer.strip().upper()
        return {
            "is_correct": is_correct,
            "correct_answer": body.correct_answer,
            "feedback": "Correct! ✓" if is_correct else f"The correct answer was {body.correct_answer}.",
            "explanation": body.explanation,
        }
