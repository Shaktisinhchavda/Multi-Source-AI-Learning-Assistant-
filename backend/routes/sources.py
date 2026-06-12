"""
Sources API — upload files and submit URLs for processing.
Supports: PDF, PPTX (file upload), YouTube, Webpage (URL).
"""

import json
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from supabase import create_client
from config import get_settings
from processors.pdf import process_pdf
from processors.pptx import process_pptx
from processors.youtube import process_youtube
from processors.webpage import process_webpage
from rag.embeddings import embed_texts

router = APIRouter(prefix="/api/sources", tags=["sources"])


class URLSource(BaseModel):
    session_id: str
    url: str
    source_type: str  # 'youtube' or 'webpage'


async def _store_chunks(client, session_id: str, source_id: str, chunks: list[dict]):
    """Generate embeddings and store chunks in Supabase."""
    if not chunks:
        raise ValueError("No text content could be extracted.")

    # Generate embeddings for all chunks
    chunk_texts = [c["content"] for c in chunks]
    embeddings = await embed_texts(chunk_texts)

    # Build rows
    rows = []
    for chunk, embedding in zip(chunks, embeddings):
        rows.append({
            "session_id": session_id,
            "source_id": source_id,
            "content": chunk["content"],
            "embedding": embedding,
            "source_type": chunk["source_type"],
            "source_name": chunk["source_name"],
            "source_ref": chunk.get("source_ref"),
            "metadata": json.dumps(chunk.get("metadata", {})),
        })

    # Insert in batches
    batch_size = 50
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        client.table("documents").insert(batch).execute()

    return len(rows)


@router.post("/upload")
async def upload_file(
    session_id: str = Form(...),
    file: UploadFile = File(...),
):
    """
    Upload a PDF or PPTX file for processing.
    Extracts text, chunks it, generates embeddings, and stores in Supabase.
    """
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_key)

    # Determine file type
    filename = file.filename or "unknown"
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if ext not in ("pdf", "pptx"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{ext}. Supported: .pdf, .pptx",
        )

    # Create source record
    source_record = client.table("sources").insert({
        "session_id": session_id,
        "source_type": ext,
        "source_name": filename,
        "status": "processing",
    }).execute()

    if not source_record.data:
        raise HTTPException(status_code=500, detail="Failed to create source record")

    source_id = source_record.data[0]["id"]

    try:
        file_bytes = await file.read()

        # Process based on type
        if ext == "pdf":
            result = process_pdf(file_bytes, filename)
        elif ext == "pptx":
            result = process_pptx(file_bytes, filename)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        chunks = result["chunks"]
        summary = result["summary"]

        # Embed and store
        await _store_chunks(client, session_id, source_id, chunks)

        # Update source record
        client.table("sources").update({
            "status": "ready",
            "summary": summary,
            "chunk_count": len(chunks),
        }).eq("id", source_id).execute()

        return {
            "source_id": source_id,
            "source_name": filename,
            "source_type": ext,
            "status": "ready",
            "summary": summary,
            "chunk_count": len(chunks),
            "page_count": result.get("page_count", result.get("slide_count", 0)),
        }

    except Exception as e:
        client.table("sources").update({
            "status": "error",
            "error_message": str(e),
        }).eq("id", source_id).execute()

        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@router.post("/url")
async def add_url_source(body: URLSource):
    """
    Submit a YouTube or webpage URL for processing.
    Fetches content, chunks, embeds, and stores in Supabase.
    """
    if body.source_type not in ("youtube", "webpage"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source type: {body.source_type}. Supported: youtube, webpage",
        )

    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_key)

    # Determine source name
    source_name = body.url
    if body.source_type == "youtube":
        source_name = f"YouTube: {body.url}"
    elif body.source_type == "webpage":
        source_name = body.url

    # Create source record
    source_record = client.table("sources").insert({
        "session_id": body.session_id,
        "source_type": body.source_type,
        "source_name": source_name,
        "status": "processing",
    }).execute()

    if not source_record.data:
        raise HTTPException(status_code=500, detail="Failed to create source record")

    source_id = source_record.data[0]["id"]

    try:
        # Process based on type
        if body.source_type == "youtube":
            result = process_youtube(body.url)
        elif body.source_type == "webpage":
            result = await process_webpage(body.url)
        else:
            raise ValueError(f"Unsupported source type: {body.source_type}")

        chunks = result["chunks"]
        summary = result["summary"]

        # Update source name with title if available
        final_name = source_name
        if body.source_type == "youtube" and result.get("video_id"):
            final_name = f"YouTube: {result['video_id']}"
        elif body.source_type == "webpage" and result.get("title"):
            final_name = result["title"]

        # Embed and store
        await _store_chunks(client, body.session_id, source_id, chunks)

        # Update source record
        client.table("sources").update({
            "status": "ready",
            "summary": summary,
            "source_name": final_name,
            "chunk_count": len(chunks),
        }).eq("id", source_id).execute()

        return {
            "source_id": source_id,
            "source_name": final_name,
            "source_type": body.source_type,
            "status": "ready",
            "summary": summary,
            "chunk_count": len(chunks),
        }

    except Exception as e:
        client.table("sources").update({
            "status": "error",
            "error_message": str(e),
        }).eq("id", source_id).execute()

        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
