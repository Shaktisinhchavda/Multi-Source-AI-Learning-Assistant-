"""
Sources API — upload files and submit URLs for processing.
"""

import json
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from supabase import create_client
from config import get_settings
from processors.pdf import process_pdf
from rag.embeddings import embed_texts

router = APIRouter(prefix="/api/sources", tags=["sources"])


class URLSource(BaseModel):
    session_id: str
    url: str
    source_type: str  # 'youtube' or 'webpage'


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
        # Read file bytes
        file_bytes = await file.read()

        # Process based on type
        if ext == "pdf":
            result = process_pdf(file_bytes, filename)
        else:
            # PPTX will be added in Phase 2
            raise HTTPException(status_code=501, detail="PPTX processing coming in Phase 2")

        chunks = result["chunks"]
        summary = result["summary"]

        if not chunks:
            raise ValueError("No text content could be extracted from the file.")

        # Generate embeddings for all chunks
        chunk_texts = [c["content"] for c in chunks]
        embeddings = await embed_texts(chunk_texts)

        # Store chunks with embeddings in Supabase
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

        # Update source record with summary and status
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
            "page_count": result.get("page_count", 0),
        }

    except Exception as e:
        # Update source record with error
        client.table("sources").update({
            "status": "error",
            "error_message": str(e),
        }).eq("id", source_id).execute()

        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@router.post("/url")
async def add_url_source(body: URLSource):
    """
    Submit a YouTube or webpage URL for processing.
    Phase 2 — currently returns a placeholder.
    """
    if body.source_type not in ("youtube", "webpage"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source type: {body.source_type}. Supported: youtube, webpage",
        )

    # Phase 2 implementation
    raise HTTPException(
        status_code=501,
        detail=f"{body.source_type} processing coming in Phase 2",
    )
