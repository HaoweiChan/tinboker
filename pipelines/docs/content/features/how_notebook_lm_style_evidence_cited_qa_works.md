# How NotebookLM-style Evidence-Cited QA Works

## Core Idea
NotebookLM is **not just an LLM reading documents**. It is a **Retrieval-Augmented Generation (RAG)** system where:

> **Answers are generated only from retrieved document snippets, and citations are produced at the same time as the answer.**

This makes every claim traceable to exact document locations (e.g. line numbers).

---

## High-Level Architecture

```
User Question
      ↓
Vector Retrieval (Evidence First)
      ↓
Constrained Prompt (Sources + Rules)
      ↓
Answer + Inline Citations
```

Key principle: **Retrieval happens before generation, never after.**

---

## 1. Document Ingestion

### Chunking
Documents are split into small chunks, each with metadata:

```json
{
  "text": "...",
  "source_id": "doc_001",
  "line_start": 23,
  "line_end": 25,
  "chunk_id": "doc_001_chunk_004"
}
```

- Line numbers are stored explicitly
- The model never infers or guesses them

---

## 2. Indexing

Each chunk has two representations:

- **Raw text** → used for grounding
- **Embedding vector** → used for retrieval

Stored in a vector database (e.g. FAISS, Pinecone).

---

## 3. Question Answering Pipeline

### Step 1: Evidence Retrieval

- User question is embedded
- Top-K relevant chunks are retrieved
- Each chunk already contains line numbers

### Step 2: Constrained Prompt Construction

The LLM receives:

- Only the retrieved chunks
- Explicit rules:
  - Use **only** provided sources
  - Cite line numbers for every claim
  - Say *"Not found in sources"* if unsupported

### Step 3: Answer Generation

The model generates:

- Natural language answer
- Inline citations (e.g. `[lines 23–25]`)

Citations are generated **together with the text**, not added later.

---

## Why Citations Are Accurate

Because:

1. Line numbers are explicit metadata
2. The model is constrained to visible text only
3. Each chunk is an atomic evidence unit

This is **pattern completion**, not fact verification.

---

## Hallucination Prevention

NotebookLM-style systems enforce:

- Evidence-first answering
- Refusal rules when evidence is missing
- No access to full documents
- Optional structured outputs (e.g. JSON with `claim + citations`)

---

## Key Design Patterns

- **Evidence-Then-Answer (ETA)**: no evidence → no answer
- **Source-aware prompting**: citations are first-class output
- **Chunk-level provenance**: every claim maps to a known span

---

## Minimal Stack to Build This

- Document parser (with line numbers)
- Chunker
- Embedding model
- Vector database
- Prompt template enforcing citations
- (Optional) Output schema validation

---

## Most Important Takeaway

> **This feature is achieved by system design, not by a smarter model.**

The LLM is summarizing retrieved evidence under strict constraints — not reasoning about truth or recalling documents from memory.

