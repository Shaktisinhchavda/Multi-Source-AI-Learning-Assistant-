"""
Webpage processor — scrapes and parses public webpage content.
"""

import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from .chunker import chunk_text


def _clean_url(url: str) -> str:
    """Ensure URL has a scheme."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _get_domain(url: str) -> str:
    """Extract domain name from URL."""
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split("/")[0]


async def fetch_webpage(url: str) -> str:
    """Fetch webpage HTML content."""
    url = _clean_url(url)

    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


def parse_html(html: str) -> dict:
    """
    Parse HTML and extract structured text content.
    Returns: {title, sections: [{heading, text}]}
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove script, style, nav, footer, header elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "noscript", "iframe"]):
        tag.decompose()

    # Get title
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)

    # Extract content by sections
    sections = []
    current_heading = "Introduction"
    current_text = []

    # Try to find the main content area
    main_content = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", {"role": "main"})
        or soup.find("div", class_=lambda c: c and "content" in str(c).lower())
        or soup.body
        or soup
    )

    for element in main_content.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "blockquote", "pre"]
    ):
        tag_name = element.name
        text = element.get_text(separator=" ", strip=True)

        if not text:
            continue

        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            # Save previous section
            if current_text:
                sections.append({
                    "heading": current_heading,
                    "text": "\n".join(current_text),
                })
            current_heading = text
            current_text = []
        else:
            current_text.append(text)

    # Don't forget the last section
    if current_text:
        sections.append({
            "heading": current_heading,
            "text": "\n".join(current_text),
        })

    return {"title": title, "sections": sections}


async def process_webpage(url: str) -> dict:
    """
    Full webpage processing pipeline:
    1. Fetch page HTML
    2. Parse and extract structured text
    3. Chunk by sections with references

    Returns: {chunks: [...], summary: str, title: str, url: str}
    """
    url = _clean_url(url)
    domain = _get_domain(url)

    try:
        html = await fetch_webpage(url)
    except httpx.HTTPStatusError as e:
        raise ValueError(f"Failed to fetch '{url}': HTTP {e.response.status_code}")
    except httpx.ConnectError:
        raise ValueError(f"Could not connect to '{url}'. Please check the URL.")
    except Exception as e:
        raise ValueError(f"Failed to fetch '{url}': {str(e)}")

    parsed = parse_html(html)

    if not parsed["sections"]:
        raise ValueError(
            f"Could not extract meaningful text content from '{url}'. "
            "The page may be JavaScript-rendered or require authentication."
        )

    source_name = parsed["title"] or domain
    all_chunks = []

    for section in parsed["sections"]:
        section_ref = f"section: {section['heading']}"
        chunks = chunk_text(
            text=section["text"],
            source_type="webpage",
            source_name=source_name,
            source_ref=section_ref,
        )
        all_chunks.extend(chunks)

    # Generate summary
    full_text = " ".join(s["text"] for s in parsed["sections"][:3])
    summary = full_text[:500].strip()
    if len(full_text) > 500:
        summary += "..."

    return {
        "chunks": all_chunks,
        "summary": summary,
        "title": parsed["title"],
        "url": url,
        "section_count": len(parsed["sections"]),
    }
