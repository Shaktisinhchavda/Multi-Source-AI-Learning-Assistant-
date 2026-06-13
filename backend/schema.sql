-- ============================================
-- AI Knowledge Chatbot — Supabase Schema
-- Run this in your Supabase SQL Editor
-- ============================================

-- 1. Enable pgvector extension
create extension if not exists vector;

-- 2. Sessions table
create table if not exists sessions (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  metadata jsonb default '{}'::jsonb
);

-- 3. Sources metadata (tracks each uploaded/linked source)
create table if not exists sources (
  id uuid primary key default gen_random_uuid(),
  session_id uuid references sessions(id) on delete cascade,
  source_type text not null,         -- 'youtube', 'pdf', 'pptx', 'webpage'
  source_name text not null,         -- filename or URL
  summary text,                       -- auto-generated summary
  chunk_count int default 0,
  status text default 'processing',  -- 'processing', 'ready', 'error'
  error_message text,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

-- 4. Document chunks with vector embeddings
create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  session_id uuid references sessions(id) on delete cascade,
  source_id uuid references sources(id) on delete cascade,
  content text not null,
  embedding vector(768),             -- nomic-embed-text dimension
  source_type text not null,
  source_name text not null,
  source_ref text,                   -- 'page 5', 'slide 4', 'at 3:22'
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

-- 5. Conversation messages
create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid references sessions(id) on delete cascade,
  role text not null,                -- 'user' or 'assistant'
  content text not null,
  sources jsonb default '[]'::jsonb, -- [{source_name, source_ref}]
  created_at timestamptz default now()
);

-- ============================================
-- 6. Enable Row Level Security + permissive policies
--    (allows anon key full access — fine for this app)
-- ============================================

alter table sessions enable row level security;
create policy "Allow all on sessions" on sessions
  for all using (true) with check (true);

alter table sources enable row level security;
create policy "Allow all on sources" on sources
  for all using (true) with check (true);

alter table documents enable row level security;
create policy "Allow all on documents" on documents
  for all using (true) with check (true);

alter table messages enable row level security;
create policy "Allow all on messages" on messages
  for all using (true) with check (true);

-- 7. Create index for vector similarity search (HNSW — works on empty tables)
create index if not exists documents_embedding_idx
  on documents
  using hnsw (embedding vector_cosine_ops);

-- 8. Vector similarity search function
create or replace function match_documents(
  query_embedding vector(768),
  match_count int default 5,
  filter_session_id uuid default null
)
returns table (
  id uuid,
  source_id uuid,
  content text,
  source_type text,
  source_name text,
  source_ref text,
  similarity float
)
language plpgsql
as $$
begin
  return query
  select
    d.id,
    d.source_id,
    d.content,
    d.source_type,
    d.source_name,
    d.source_ref,
    1 - (d.embedding <=> query_embedding) as similarity
  from documents d
  where d.session_id = filter_session_id
  order by d.embedding <=> query_embedding
  limit match_count;
end;
$$;
