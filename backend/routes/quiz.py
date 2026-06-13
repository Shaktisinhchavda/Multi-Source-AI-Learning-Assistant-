"""
Quiz API — generate questions from loaded content and check answers.
"""

import json
import logging
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client
from config import get_settings
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


class QuizGenerateRequest(BaseModel):
    session_id: str
    num_questions: int = 5
    source_ids: list[str] | None = None  # None = all sources
    custom_instructions: str = ""  # User-described quiz format


def _parse_num_questions(custom_instructions: str, default_count: int) -> int:
    """Parse question count from custom instructions if user mentions it."""
    if not custom_instructions:
        return _clamp_question_count(default_count)

    # Match numbers like "10 questions", "10 q", "7 tricky questions", "3 hard mcqs"
    match = re.search(r'\b(\d+)\s*(?:\w+\s+){0,2}(?:questions?|mcqs?|q)\b', custom_instructions.lower())
    if match:
        try:
            return _clamp_question_count(int(match.group(1)))
        except ValueError:
            pass

    # Match written numbers
    words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
    }
    for word, val in words.items():
        if re.search(r'\b' + word + r'\s*(?:\w+\s+){0,2}(?:questions?|mcqs?|q)\b', custom_instructions.lower()):
            return _clamp_question_count(val)

    return _clamp_question_count(default_count)


def _parse_option_count(custom_instructions: str, default_count: int = 4) -> int:
    """Parse requested options per question from custom instructions."""
    if not custom_instructions:
        return default_count

    text = custom_instructions.lower()
    if re.search(r'\b(true\s*/?\s*false|true\s+or\s+false|yes\s*/?\s*no|yes\s+or\s+no)\b', text):
        return 2

    match = re.search(
        r'\b(?:only\s+)?(\d+)\s*(?:answer\s+)?(?:options?|choices?|alternatives?)\b',
        text,
    )
    if match:
        return _clamp_option_count(int(match.group(1)))

    words = {
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
    }
    for word, val in words.items():
        if re.search(
            r'\b(?:only\s+)?' + word + r'\s*(?:answer\s+)?(?:options?|choices?|alternatives?)\b',
            text,
        ):
            return _clamp_option_count(val)

    return default_count


def _clamp_question_count(count: int) -> int:
    """Keep quiz size practical for local models and the frontend."""
    return max(1, min(count, 10))


def _clamp_option_count(count: int) -> int:
    """Keep option counts usable with A-Z answer letters."""
    return max(2, min(count, 6))


def _option_letters(count: int) -> list[str]:
    """Return answer letters for the configured number of options."""
    return [chr(65 + idx) for idx in range(count)]


def _sample_evenly(items: list[dict], count: int) -> list[dict]:
    """Pick chunks across the whole source instead of only the beginning."""
    if count <= 0 or not items:
        return []
    if count >= len(items):
        return items
    if count == 1:
        return [items[0]]

    last_index = len(items) - 1
    indexes = {
        round(i * last_index / (count - 1))
        for i in range(count)
    }
    return [items[i] for i in sorted(indexes)]


def _balanced_chunks_by_source(
    all_chunks: list[dict],
    selected_ids: list[str],
    limit_total: int = 40,
) -> list[dict]:
    """Return a bounded, balanced context set across selected sources."""
    chunks_by_source = {sid: [] for sid in selected_ids}
    for chunk in all_chunks:
        source_id = chunk.get("source_id")
        if source_id in chunks_by_source:
            chunks_by_source[source_id].append(chunk)

    non_empty_sources = [
        sid for sid in selected_ids
        if chunks_by_source[sid]
    ]
    if not non_empty_sources:
        return []

    per_source = max(1, limit_total // len(non_empty_sources))
    selected: list[dict] = []

    for sid in non_empty_sources:
        remaining_capacity = limit_total - len(selected)
        if remaining_capacity <= 0:
            break
        take = min(per_source, remaining_capacity, len(chunks_by_source[sid]))
        selected.extend(_sample_evenly(chunks_by_source[sid], take))

    if len(selected) < limit_total:
        selected_keys = {
            (
                chunk.get("source_id"),
                chunk.get("source_ref"),
                chunk.get("content"),
            )
            for chunk in selected
        }
        for chunk in all_chunks:
            key = (
                chunk.get("source_id"),
                chunk.get("source_ref"),
                chunk.get("content"),
            )
            if chunk.get("source_id") in non_empty_sources and key not in selected_keys:
                selected.append(chunk)
                selected_keys.add(key)
            if len(selected) >= limit_total:
                break

    return selected


def _allocate_questions(source_ids: list[str], total_questions: int) -> dict[str, int]:
    """Split requested questions across sources as evenly as possible."""
    if not source_ids:
        return {}

    base = total_questions // len(source_ids)
    remainder = total_questions % len(source_ids)
    allocations = {}

    for index, source_id in enumerate(source_ids):
        allocations[source_id] = base + (1 if index < remainder else 0)

    return {source_id: count for source_id, count in allocations.items() if count > 0}


def _build_context(chunks: list[dict]) -> str:
    """Build quiz context with explicit source labels."""
    context_parts = []
    for chunk in chunks:
        ref = f"[{chunk['source_name']}"
        if chunk.get("source_ref"):
            ref += f", {chunk['source_ref']}"
        ref += "]"
        context_parts.append(f"{ref}\n{chunk['content']}")

    return "\n\n---\n\n".join(context_parts)


def _extract_raw_questions(response_text: str) -> list[dict]:
    """Extract question objects from common LLM JSON shapes."""
    json_text = response_text.strip()

    if "```json" in json_text:
        json_text = json_text.split("```json", 1)[1]
        if "```" in json_text:
            json_text = json_text.split("```", 1)[0]
    elif "```" in json_text:
        parts = json_text.split("```")
        if len(parts) >= 3:
            json_text = parts[1]
        elif len(parts) == 2:
            json_text = parts[1] if parts[1].strip().startswith("[") else parts[0]

    json_text = json_text.strip()

    def _flatten(item):
        flat = []
        if isinstance(item, dict):
            has_numbered = any(
                isinstance(k, str)
                and (k.startswith("question_") or k.startswith("q_") or k.isdigit())
                for k in item.keys()
            )
            if has_numbered:
                for k, v in item.items():
                    if isinstance(k, str) and (
                        k.startswith("question") or k.startswith("q") or k.isdigit()
                    ):
                        if isinstance(v, str):
                            flat.append({"question": v})
                        elif isinstance(v, dict):
                            flat.append(v)
                return flat

            for k in ["questions", "question", "quiz", "data"]:
                if k in item and isinstance(item[k], list):
                    for sub in item[k]:
                        flat.extend(_flatten(sub))
                    return flat
            flat.append(item)
        elif isinstance(item, list):
            for sub in item:
                flat.extend(_flatten(sub))
        return flat

    try:
        return _flatten(json.loads(json_text))
    except json.JSONDecodeError:
        array_match = re.search(r'\[[\s\S]*\]', json_text)
        if array_match:
            try:
                return _flatten(json.loads(array_match.group(0)))
            except json.JSONDecodeError:
                return []

        obj_match = re.search(r'\{[\s\S]*\}', json_text)
        if obj_match:
            try:
                return _flatten(json.loads(obj_match.group(0)))
            except json.JSONDecodeError:
                return []

    return []


def _validate_questions(
    raw_questions: list[dict],
    limit: int,
    source_name: str,
    option_count: int,
) -> list[dict]:
    """Normalize tolerant LLM output into the frontend quiz shape."""
    validated = []

    for q in raw_questions:
        if not isinstance(q, dict):
            continue

        question_text = q.get("question") or q.get("q")
        if not question_text:
            continue

        options = q.get("options") or q.get("choices")
        correct_val = q.get("correct") or q.get("correct_answer") or q.get("answer")

        if not options or not isinstance(options, list) or len(options) == 0:
            if not correct_val:
                continue
            ans_str = str(correct_val).strip()
            options = [ans_str, "Information not provided"]
            correct_val = "A"

        options = [str(opt) for opt in options]
        option_count = _clamp_option_count(option_count)
        valid_letters = _option_letters(option_count)

        normalized_correct = None
        if isinstance(correct_val, str) and correct_val.strip():
            stripped = correct_val.strip()
            first_char = stripped[0].upper()
            if first_char in valid_letters:
                normalized_correct = first_char
            else:
                for idx, opt in enumerate(options[:option_count]):
                    if stripped.lower() in opt.lower() or opt.lower() in stripped.lower():
                        normalized_correct = chr(65 + idx)
                        break

        if not normalized_correct:
            if correct_val and str(correct_val) not in options:
                options[0] = str(correct_val)
            normalized_correct = "A"

        while len(options) < option_count:
            options.append(f"Option {len(options) + 1}")
        options = options[:option_count]

        formatted_options = []
        for idx, opt in enumerate(options):
            prefix = f"{chr(65 + idx)})"
            opt_str = str(opt).strip()
            if (
                len(opt_str) >= 2
                and opt_str[0].upper() == chr(65 + idx)
                and opt_str[1] in [")", ".", " ", ":"]
            ):
                opt_str = opt_str[2:].strip()
            formatted_options.append(f"{prefix} {opt_str}")

        source_ref = str(q.get("source_ref", "")).strip()
        if source_ref and source_name not in source_ref:
            source_ref = f"{source_name} - {source_ref}"
        elif not source_ref:
            source_ref = source_name

        validated.append({
            "question": str(question_text),
            "options": formatted_options,
            "correct": normalized_correct,
            "explanation": str(q.get("explanation", "")),
            "source_ref": source_ref,
        })

        if len(validated) >= limit:
            break

    return validated


class QuizCheckRequest(BaseModel):
    session_id: str
    question: str
    user_answer: str
    correct_answer: str
    explanation: str = ""


QUIZ_SYSTEM_PROMPT = """You are a quiz generator. Based on the provided source material, generate exactly {num_questions} multiple-choice questions to test the reader's understanding.

CRITICAL INSTRUCTION: You MUST output a JSON object containing a SINGLE key called "questions". The value MUST be a list of question objects. DO NOT output a list of references, citations, or anything else.

Return ONLY valid JSON in this exact format:
{{
  "questions": [
    {{
      "question": "What is...?",
      "options": [{example_options}],
      "correct": "A",
      "explanation": "Brief explanation of why A is correct, citing the source.",
      "source_ref": "page 3"
    }}
  ]
}}

Rules:
1. Questions must be answerable from the provided material ONLY.
2. Each question must have exactly {option_count} options ({option_letters}).
3. Vary difficulty: include easy recall, understanding, and application questions.
4. The "correct" field must be just one of these letters: {option_letters}.
5. Include source references in the explanation.
6. Return ONLY the JSON object, nothing else. DO NOT extract bibliography or references.
{custom_instructions}"""


CHECK_SYSTEM_PROMPT = """You are a quiz evaluator. The user answered a quiz question. Evaluate their answer.

Question: {question}
Correct Answer: {correct_answer}
User's Answer: {user_answer}

Respond with a brief, encouraging evaluation. If they got it right, congratulate them. If wrong, explain the correct answer kindly. Keep it to 2-3 sentences."""


async def _chat_ollama_simple(messages: list[dict], response_format: str | None = None) -> str:
    """Simple non-streaming Ollama chat call."""
    settings = get_settings()
    payload = {
        "model": settings.ollama_chat_model,
        "messages": messages,
        "stream": False,
    }
    if response_format:
        payload["format"] = response_format

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json=payload,
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
    sources_query = (
        client.table("sources")
        .select("id, source_name, source_type")
        .eq("session_id", body.session_id)
        .eq("status", "ready")
    )
    sources = sources_query.execute()

    if not sources.data:
        raise HTTPException(
            status_code=400,
            detail="No sources loaded. Please upload documents first.",
        )

    # Determine which source IDs to use
    if body.source_ids and len(body.source_ids) > 0:
        valid_ids = {s["id"] for s in sources.data}
        selected_ids = [sid for sid in body.source_ids if sid in valid_ids]
        if not selected_ids:
            raise HTTPException(
                status_code=400,
                detail="None of the selected sources are available.",
            )
    else:
        selected_ids = [s["id"] for s in sources.data]

    # Retrieve chunks directly from the documents table, filtered by source_ids.
    # Ordered by created_at to ensure the text context is continuous and readable.
    docs_query = (
        client.table("documents")
        .select("content, source_type, source_name, source_ref, source_id")
        .eq("session_id", body.session_id)
        .in_("source_id", selected_ids)
        .order("created_at")
    )
    docs_result = docs_query.execute()
    all_chunks = docs_result.data or []

    source_lookup = {
        source["id"]: source
        for source in sources.data
        if source["id"] in selected_ids
    }
    non_empty_source_ids = [
        source_id
        for source_id in selected_ids
        if any(chunk.get("source_id") == source_id for chunk in all_chunks)
    ]

    if not non_empty_source_ids:
        raise HTTPException(
            status_code=400,
            detail="No content found in the selected sources.",
        )

    # Resolve the final number of questions to generate (override default if mentioned in instructions)
    num_questions = _parse_num_questions(body.custom_instructions, body.num_questions)
    option_count = _parse_option_count(body.custom_instructions)
    option_letters = _option_letters(option_count)
    option_letters_text = ", ".join(option_letters)
    example_options = ", ".join(
        f'"{letter}) Option {index + 1}"'
        for index, letter in enumerate(option_letters)
    )
    allocations = _allocate_questions(non_empty_source_ids, num_questions)

    # Build custom instructions block
    custom_block = ""
    if body.custom_instructions.strip():
        custom_block = f"\n\nAdditional instructions from the user:\n{body.custom_instructions.strip()}"

    try:
        validated = []
        for source_id, source_question_count in allocations.items():
            source = source_lookup[source_id]
            source_name = source["source_name"]
            source_type = source["source_type"]
            chunks = _balanced_chunks_by_source(
                all_chunks,
                [source_id],
                limit_total=20,
            )
            context = _build_context(chunks)

            system_content = QUIZ_SYSTEM_PROMPT.format(
                num_questions=source_question_count,
                option_count=option_count,
                option_letters=option_letters_text,
                example_options=example_options,
                custom_instructions=custom_block,
            )
            user_content = f"""--- SOURCE MATERIAL ---
Source name: {source_name}
Source type: {source_type}

{context}

{system_content}

CRITICAL: Generate exactly {source_question_count} multiple-choice quiz question(s) from ONLY this source: {source_name}. Each question must have exactly {option_count} options ({option_letters_text}). Do not use any other source. The source_ref field must mention this source and its page/slide/timestamp/section when available."""

            source_questions = []
            for response_format in ("json", None):
                response_text = await _chat_ollama_simple(
                    [{"role": "user", "content": user_content}],
                    response_format=response_format,
                )
                logger.info(
                    "Quiz LLM raw response for %s (first 500 chars): %s",
                    source_name,
                    response_text[:500],
                )

                raw_questions = _extract_raw_questions(response_text)
                source_questions = _validate_questions(
                    raw_questions,
                    source_question_count,
                    source_name,
                    option_count,
                )
                if source_questions:
                    break

                logger.error(
                    "Failed to parse quiz questions for %s. Raw: %s",
                    source_name,
                    response_text[:1000],
                )

            if not source_questions:
                raise HTTPException(
                    status_code=500,
                    detail=f"Quiz generation failed for source: {source_name}. Please try again.",
                )

            validated.extend(source_questions)

        if not validated:
            raise HTTPException(
                status_code=500,
                detail="Quiz generation returned no valid questions. Please try again.",
            )

        validated = validated[:num_questions]

        return {"questions": validated, "total": len(validated)}

    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Failed to parse quiz questions from AI response. Please try again.",
        )
    except Exception as e:
        logger.error(f"Quiz generation error: {type(e).__name__}: {e}")
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
