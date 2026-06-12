"""
YouTube processor — extracts transcript with timestamps.
"""

import re
from youtube_transcript_api import YouTubeTranscriptApi
from .chunker import chunk_text


def extract_video_id(url: str) -> str:
    """
    Extract video ID from various YouTube URL formats:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    """
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from URL: {url}")


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to human-readable timestamp (e.g., '3:22')."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    if mins >= 60:
        hours = int(mins // 60)
        mins = int(mins % 60)
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def process_youtube(url: str) -> dict:
    """
    Full YouTube processing pipeline:
    1. Extract video ID
    2. Fetch transcript
    3. Group transcript segments into chunks with timestamps
    4. Generate a summary

    Returns: {chunks: [...], summary: str, video_id: str}
    """
    video_id = extract_video_id(url)

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        # Try to get English transcript, or first available
        try:
            transcript = transcript_list.find_transcript(['en'])
        except Exception:
            # Get the first available and translate to English if possible
            transcript = next(iter(transcript_list))
            try:
                transcript = transcript.translate('en')
            except Exception:
                pass  # Use whatever language is available

        segments = transcript.fetch()
    except Exception as e:
        raise ValueError(
            f"Could not fetch transcript for video '{video_id}'. "
            f"The video may not have captions available. Error: {str(e)}"
        )

    if not segments:
        raise ValueError(f"No transcript content found for video '{video_id}'.")

    # Group segments into ~30-second windows with timestamps
    grouped_segments = []
    current_text = []
    current_start = 0
    window_duration = 30  # seconds per group

    for segment in segments:
        seg_start = segment.start if hasattr(segment, 'start') else segment.get('start', 0)
        seg_text = segment.text if hasattr(segment, 'text') else segment.get('text', '')

        if not current_text:
            current_start = seg_start

        current_text.append(seg_text)

        # Check if we've exceeded the window
        if seg_start - current_start >= window_duration:
            timestamp = _format_timestamp(current_start)
            grouped_segments.append({
                "text": " ".join(current_text),
                "timestamp": timestamp,
                "start_seconds": current_start,
            })
            current_text = []

    # Don't forget the last group
    if current_text:
        timestamp = _format_timestamp(current_start)
        grouped_segments.append({
            "text": " ".join(current_text),
            "timestamp": timestamp,
            "start_seconds": current_start,
        })

    # Chunk with timestamp references
    all_chunks = []
    source_name = f"YouTube: {video_id}"

    for group in grouped_segments:
        chunks = chunk_text(
            text=group["text"],
            source_type="youtube",
            source_name=source_name,
            source_ref=f"at {group['timestamp']}",
        )
        all_chunks.extend(chunks)

    # Generate summary from first few segments
    full_text = " ".join(g["text"] for g in grouped_segments[:5])
    summary = full_text[:500].strip()
    if len(full_text) > 500:
        summary += "..."

    return {
        "chunks": all_chunks,
        "summary": summary,
        "video_id": video_id,
        "segment_count": len(grouped_segments),
    }
