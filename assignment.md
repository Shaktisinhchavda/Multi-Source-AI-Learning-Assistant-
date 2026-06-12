# Stack 
FastAPI · React / Next.js · Supabase · any LLM API (create separate modules for frontend and backend and use python as a backend)
frontend should be look like this @image.png (not exact but i want this co;or combination)

# what to build
Build a web-based AI chatbot that accepts one or more knowledge sources from the user, processes them, and
then answers questions, explains concepts, and resolves doubts based on that content.

# Supported Input Sources
• YouTube video URL — transcribe or summarise the video and use it as context
• PDF file — extract and chunk text, build a retrieval index
• PowerPoint / PPTX file — parse slides, extract text + structure
• Any public webpage URL — scrape and parse the page content
The user should be able to mix and combine sources in a single session (e.g. a PDF + a YouTube video
together).

# Chatbot Behaviour
• Answer questions grounded strictly in the uploaded/linked content
• Explain topics in simple language on request ("explain this in simple terms")
• Handle cross-questions and follow-up queries in the same session
• Cite or reference the source when answering (e.g. "from slide 4" or "at 3:22 in the video")
• Gracefully decline questions that are out of scope of the provided material

# Technical Requirements
1. Chunking & Retrieval — use vector embeddings or keyword search to retrieve relevant chunks before
calling the LLM. Do not dump the full document into a single prompt.
2. Streaming responses — the chatbot should stream the reply token by token, not wait for the full
response.

3. Session memory — the conversation history should persist for the duration of the session so follow-
up questions work naturally.

4. Basic UI — a clean chat interface; file upload area; source badges showing what has been loaded.

# additional features
• Support multiple simultaneous sources and indicate which source each answer came from
• Add a "quiz me" mode that auto-generates questions based on the loaded content
• Show a short summary of each source once it has been processed