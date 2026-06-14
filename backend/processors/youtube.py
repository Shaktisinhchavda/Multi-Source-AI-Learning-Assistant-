"""
YouTube processor — extracts transcript/subtitles with timestamps.
Uses yt-dlp (robust) with youtube-transcript-api as fallback.
"""

import re
import json
import time
import logging
import tempfile
import os
import base64
from pathlib import Path
from contextlib import contextmanager
from .chunker import chunk_text
from config import get_settings
from rag.gemini import extract_error_message

logger = logging.getLogger(__name__)


class YouTubeTranscriptError(ValueError):
    """Raised when captions cannot be fetched for a YouTube video."""

    pass


def _is_youtube_bot_check_error(message: str) -> bool:
    normalized = message.lower()
    return (
        "sign in to confirm" in normalized
        and "not a bot" in normalized
    ) or "--cookies" in normalized


@contextmanager
def _youtube_cookiefile():
    settings = get_settings()

    if settings.youtube_cookies_file:
        yield settings.youtube_cookies_file
        return

    if not settings.youtube_cookies_b64:
        yield None
        return

    cookie_path = None
    try:
        cookie_bytes = base64.b64decode(settings.youtube_cookies_b64)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix="youtube-cookies-",
            suffix=".txt",
            delete=False,
        ) as cookie_file:
            cookie_file.write(cookie_bytes)
            cookie_path = cookie_file.name

        yield cookie_path
    finally:
        if cookie_path:
            try:
                os.remove(cookie_path)
            except OSError:
                logger.warning("Failed to remove temporary YouTube cookies file")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _youtube_extractor_args() -> dict:
    settings = get_settings()
    youtube_args = {}

    player_clients = _split_csv(settings.youtube_player_clients)
    if player_clients:
        youtube_args['player_client'] = player_clients

    if settings.youtube_visitor_data:
        youtube_args['visitor_data'] = [settings.youtube_visitor_data]

    if settings.youtube_po_token:
        youtube_args['po_token'] = [settings.youtube_po_token]

    return {'youtube': youtube_args} if youtube_args else {}


def _apply_youtube_network_options(ydl_opts: dict) -> dict:
    settings = get_settings()
    opts = dict(ydl_opts)

    extractor_args = _youtube_extractor_args()
    if extractor_args:
        opts['extractor_args'] = extractor_args

    if settings.youtube_proxy:
        opts['proxy'] = settings.youtube_proxy

    if settings.youtube_user_agent:
        opts['http_headers'] = {
            **opts.get('http_headers', {}),
            'User-Agent': settings.youtube_user_agent,
        }

    return opts


def extract_video_id(url: str) -> str:
    """
    Extract video ID from various YouTube URL formats.
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


def _fetch_with_ytdlp(video_id: str) -> list[dict]:
    """
    Fetch subtitles using yt-dlp. Returns list of {text, start} dicts.
    More robust against rate limiting than youtube-transcript-api.
    """
    import yt_dlp

    url = f"https://www.youtube.com/watch?v={video_id}"

    ydl_opts_base = _apply_youtube_network_options({
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['all'],
        'subtitlesformat': 'json3',
        'format': 'best',
        'ignore_no_formats_error': True,
        'quiet': True,
        'no_warnings': True,
    })

    errors = []
    with _youtube_cookiefile() as cookiefile:
        cookie_candidates = [cookiefile, None] if cookiefile else [None]
        for active_cookiefile in cookie_candidates:
            ydl_opts = dict(ydl_opts_base)
            if active_cookiefile:
                ydl_opts['cookiefile'] = active_cookiefile
                logger.warning("Using configured YouTube cookies for %s", video_id)
            else:
                logger.warning("Trying YouTube transcript fetch without cookies for %s", video_id)

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        info = ydl.extract_info(url, download=False)
                    except Exception as e:
                        raise ValueError(f"yt-dlp failed to fetch video info: {str(e)}")

                    # Check for subtitles
                    subtitles = info.get('subtitles', {})
                    auto_captions = info.get('automatic_captions', {})
                    logger.warning(
                        "YouTube subtitle languages for %s: manual=%s automatic=%s",
                        video_id,
                        list(subtitles.keys()),
                        list(auto_captions.keys()),
                    )

                    # Try manual subs first, then auto-captions
                    sub_data = None
                    for lang in ['en', 'en-US', 'en-GB']:
                        if lang in subtitles:
                            sub_data = subtitles[lang]
                            break
                    if not sub_data:
                        for lang in ['en', 'en-US', 'en-GB']:
                            if lang in auto_captions:
                                sub_data = auto_captions[lang]
                                break

                    # If no English, try any language
                    if not sub_data:
                        if subtitles:
                            sub_data = next(iter(subtitles.values()))
                        elif auto_captions:
                            sub_data = next(iter(auto_captions.values()))

                    if not sub_data:
                        raise ValueError("No subtitles or auto-captions available.")

                    # Find json3 format or fall back to any format
                    json3_url = None
                    for fmt in sub_data:
                        if fmt.get('ext') == 'json3':
                            json3_url = fmt.get('url')
                            break

                    # If we have json3 URL, fetch and parse it
                    if json3_url:
                        import httpx
                        resp = httpx.get(json3_url, timeout=30.0)
                        resp.raise_for_status()
                        caption_data = resp.json()

                        segments = []
                        for event in caption_data.get('events', []):
                            start_ms = event.get('tStartMs', 0)
                            segs = event.get('segs', [])
                            text = ''.join(s.get('utf8', '') for s in segs).strip()
                            if text and text != '\n':
                                segments.append({
                                    'text': text,
                                    'start': start_ms / 1000.0,
                                })
                        return segments

                    # Fallback: try to get vtt/srv formats and parse text
                    # Use yt-dlp to write subs to a temp file
                    with tempfile.TemporaryDirectory() as tmpdir:
                        dl_opts = {
                            **ydl_opts,
                            'outtmpl': os.path.join(tmpdir, '%(id)s'),
                            'writesubtitles': True,
                            'writeautomaticsub': True,
                        }
                        with yt_dlp.YoutubeDL(dl_opts) as ydl2:
                            ydl2.download([url])

                        # Find the subtitle file
                        for f in os.listdir(tmpdir):
                            if f.endswith('.vtt') or f.endswith('.srt'):
                                filepath = os.path.join(tmpdir, f)
                                return _parse_vtt_file(filepath)
            except Exception as e:
                label = "with cookies" if active_cookiefile else "without cookies"
                errors.append(f"{label}: {str(e)}")
                logger.warning("yt-dlp transcript fetch failed %s for %s: %s", label, video_id, e)
                continue

    raise ValueError("Could not parse subtitle data. " + "; ".join(errors))


def _audio_mime_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in ('.m4a', '.mp4'):
        return 'audio/mp4'
    if ext == '.mp3':
        return 'audio/mpeg'
    if ext == '.wav':
        return 'audio/wav'
    if ext == '.ogg':
        return 'audio/ogg'
    if ext == '.webm':
        return 'audio/webm'
    return 'application/octet-stream'


def _extract_gemini_text(data: dict) -> str:
    parts = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    )
    return "".join(part.get("text", "") for part in parts).strip()


def _download_youtube_audio(video_id: str, tmpdir: str) -> str:
    """Download audio-only media for transcription fallback."""
    import yt_dlp

    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = _apply_youtube_network_options({
        'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best',
        'outtmpl': os.path.join(tmpdir, '%(id)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    })

    errors = []
    with _youtube_cookiefile() as cookiefile:
        cookie_candidates = [cookiefile, None] if cookiefile else [None]
        for active_cookiefile in cookie_candidates:
            active_opts = dict(ydl_opts)
            if active_cookiefile:
                active_opts['cookiefile'] = active_cookiefile
                logger.warning("Using configured YouTube cookies for audio download %s", video_id)
            else:
                logger.warning("Trying YouTube audio download without cookies for %s", video_id)

            try:
                with yt_dlp.YoutubeDL(active_opts) as ydl:
                    ydl.download([url])
                break
            except Exception as e:
                label = "with cookies" if active_cookiefile else "without cookies"
                errors.append(f"{label}: {str(e)}")
                logger.warning("YouTube audio download failed %s for %s: %s", label, video_id, e)
                continue

    files = [
        os.path.join(tmpdir, f)
        for f in os.listdir(tmpdir)
        if os.path.isfile(os.path.join(tmpdir, f))
    ]
    if not files:
        raise ValueError("Could not download YouTube audio for transcription. " + "; ".join(errors))
    return max(files, key=os.path.getsize)


def _transcribe_audio_with_gemini(audio_path: str) -> str:
    """Transcribe an audio file using Gemini inline audio input."""
    import httpx

    settings = get_settings()
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is required for YouTube audio transcription fallback.")

    max_bytes = max(1, settings.youtube_audio_max_mb) * 1024 * 1024
    audio_size = os.path.getsize(audio_path)
    if audio_size > max_bytes:
        raise ValueError(
            "YouTube captions were unavailable and the audio is too large for "
            f"fallback transcription ({audio_size // (1024 * 1024)} MB)."
        )

    with open(audio_path, 'rb') as audio_file:
        audio_b64 = base64.b64encode(audio_file.read()).decode('ascii')

    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {
                    "text": (
                        "Transcribe this audio accurately. Return only the spoken "
                        "transcript text. Do not summarize, add headings, or include "
                        "commentary."
                    )
                },
                {
                    "inlineData": {
                        "mimeType": _audio_mime_type(audio_path),
                        "data": audio_b64,
                    }
                },
            ],
        }],
        "generationConfig": {
            "temperature": 0.0,
        },
    }

    url = (
        f"{settings.gemini_base_url}/models/"
        f"{settings.gemini_chat_model}:generateContent"
    )
    with httpx.Client(timeout=300.0) as client:
        response = client.post(
            url,
            params={"key": settings.gemini_api_key},
            json=payload,
        )

    if response.status_code >= 400:
        raise ValueError(
            "Gemini audio transcription request failed with HTTP "
            f"{response.status_code}: {extract_error_message(response)}"
        )

    transcript = _extract_gemini_text(response.json())
    if not transcript:
        raise ValueError("Gemini returned an empty audio transcript.")
    return transcript


def _fetch_with_audio_transcription(video_id: str) -> list[dict]:
    """Fallback for videos whose caption tracks are hidden from the backend."""
    logger.warning("Falling back to audio transcription for %s", video_id)
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = _download_youtube_audio(video_id, tmpdir)
        transcript = _transcribe_audio_with_gemini(audio_path)
    return [{'text': transcript, 'start': 0.0}]


def _parse_vtt_file(filepath: str) -> list[dict]:
    """Parse a VTT/SRT subtitle file into segments."""
    segments = []
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Simple VTT/SRT parser
    time_pattern = r'(\d{1,2}):(\d{2}):(\d{2})[.,](\d{3})'
    lines = content.split('\n')
    current_time = 0
    current_text = []

    for line in lines:
        line = line.strip()
        time_match = re.search(f'{time_pattern}\\s*-->\\s*{time_pattern}', line)
        if time_match:
            # Save previous segment
            if current_text:
                text = ' '.join(current_text).strip()
                if text:
                    segments.append({'text': text, 'start': current_time})
            current_text = []
            h, m, s, ms = int(time_match.group(1)), int(time_match.group(2)), int(time_match.group(3)), int(time_match.group(4))
            current_time = h * 3600 + m * 60 + s + ms / 1000.0
        elif line and not line.isdigit() and 'WEBVTT' not in line:
            # Remove HTML tags
            clean = re.sub(r'<[^>]+>', '', line)
            if clean.strip():
                current_text.append(clean.strip())

    # Last segment
    if current_text:
        text = ' '.join(current_text).strip()
        if text:
            segments.append({'text': text, 'start': current_time})

    return segments


def _fetch_with_transcript_api(video_id: str) -> list[dict]:
    """Fallback: fetch using youtube-transcript-api."""
    from youtube_transcript_api import YouTubeTranscriptApi

    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

    try:
        transcript = transcript_list.find_transcript(['en', 'en-US', 'en-GB'])
    except Exception:
        transcript = next(iter(transcript_list))
        try:
            transcript = transcript.translate('en')
        except Exception:
            pass

    raw_segments = transcript.fetch()
    segments = []
    for seg in raw_segments:
        start = seg.start if hasattr(seg, 'start') else seg.get('start', 0)
        text = seg.text if hasattr(seg, 'text') else seg.get('text', '')
        segments.append({'text': text, 'start': start})

    return segments


def process_youtube(url: str) -> dict:
    """
    Full YouTube processing pipeline:
    1. Extract video ID
    2. Fetch transcript (yt-dlp primary, transcript-api fallback)
    3. Group segments into chunks with timestamps
    4. Generate a summary

    Returns: {chunks: [...], summary: str, video_id: str}
    """
    video_id = extract_video_id(url)

    # Try yt-dlp first (more robust), fall back to transcript API
    segments = None
    errors = []

    try:
        logger.info(f"Fetching transcript via yt-dlp for {video_id}")
        segments = _fetch_with_ytdlp(video_id)
    except Exception as e:
        errors.append(f"yt-dlp: {str(e)}")
        logger.warning(f"yt-dlp failed for {video_id}: {e}")

    if not segments:
        try:
            logger.info(f"Falling back to transcript API for {video_id}")
            segments = _fetch_with_transcript_api(video_id)
        except Exception as e:
            errors.append(f"transcript-api: {str(e)}")
            logger.warning(f"transcript API also failed for {video_id}: {e}")

    settings = get_settings()
    if not segments and settings.youtube_audio_fallback:
        try:
            segments = _fetch_with_audio_transcription(video_id)
        except Exception as e:
            errors.append(f"audio-transcription: {str(e)}")
            logger.warning(f"audio transcription fallback failed for {video_id}: {e}")

    if not segments:
        details = "; ".join(errors)
        if _is_youtube_bot_check_error(details):
            raise YouTubeTranscriptError(
                "YouTube blocked this server while fetching the video audio. "
                "The video has no usable captions, and audio transcription could "
                "not start because yt-dlp hit YouTube's bot check. Refresh "
                "YOUTUBE_COOKIES_B64, or configure YOUTUBE_PROXY / "
                "YOUTUBE_PO_TOKEN for the deployed backend and restart it."
            )

        raise YouTubeTranscriptError(
            f"Could not fetch subtitles for video '{video_id}'. "
            "The video may not have captions available, captions may be disabled, "
            "or YouTube may be limiting transcript access for this request."
        )

    # Group segments into ~30-second windows with timestamps
    grouped_segments = []
    current_text = []
    current_start = 0
    window_duration = 30

    for segment in segments:
        seg_start = segment.get('start', 0)
        seg_text = segment.get('text', '')

        if not current_text:
            current_start = seg_start

        current_text.append(seg_text)

        if seg_start - current_start >= window_duration:
            timestamp = _format_timestamp(current_start)
            grouped_segments.append({
                "text": " ".join(current_text),
                "timestamp": timestamp,
                "start_seconds": current_start,
            })
            current_text = []

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

    # Generate summary
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
