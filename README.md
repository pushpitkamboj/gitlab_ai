# GitLab AI Bot

A RAG-based chatbot for GitLab documentation using LangGraph, ChromaDB, and FastAPI.

## Overview

This project builds an intelligent chatbot that answers questions about GitLab by:
1. Crawling and indexing GitLab handbook documentation
2. Storing content as vector embeddings in ChromaDB
3. Using a multi-step LangGraph pipeline for intelligent retrieval and answer generation

## Architecture

```
User Query --> FastAPI --> LangGraph Pipeline --> Response
                              |
                              v
                    [1] Find Relevant Links
                              |
                              v
                    [2] Retrieve Chunks (ChromaDB)
                              |
                              v
                    [3] Generate Answer (GPT-4o)
```

## Project Structure

```
gitlab_ai_bot/
├── api/
│   └── main.py              # FastAPI server
├── chatbot/
│   └── graph.py             # LangGraph workflow
├── rag/
│   ├── sitemap.py           # URL discovery with Firecrawl
│   ├── data_collection.py   # Link filtering
│   ├── data_scrapping.py    # Content scraping and indexing
│   ├── filtered_links.json  # Curated URLs
│   └── gitlab_sitemap.json  # Raw sitemap data
├── Dockerfile
├── requirements.txt
```

## Data Pipeline

### Step 1: Sitemap Generation

Used Firecrawl to discover all URLs from GitLab handbook and direction pages.

```python
# rag/sitemap.py
firecrawl = Firecrawl()
urls = ["https://handbook.gitlab.com/", "https://about.gitlab.com/direction/"]

res = firecrawl.map(url=url, limit=1000)
```

This generated `gitlab_sitemap.json` containing 921 URLs with titles and descriptions.

### Step 2: Link Filtering

Filtered the raw sitemap to remove irrelevant pages (login pages, assets, etc.) and saved curated URLs to `filtered_links.json`.

### Step 3: Content Scraping and Chunking

Used Jina AI Reader to scrape each URL and convert to clean markdown:

```python
# rag/data_scrapping.py
def scrape_with_jina(url):
    jina_url = f"https://r.jina.ai/{url}"
    response = requests.get(
        jina_url,
        headers={
            "X-Return-Format": "markdown",
            "X-With-Generated-Alt": "true",
            "Authorization": f"Bearer {JINA_API_KEY}",
            "X-Extract-Only-Main-Content": "true",
        }
    )
    return response.text
```

Content is chunked using a two-stage approach:

1. **MarkdownTextSplitter** - Preserves markdown structure (headers, code blocks)
2. **RecursiveCharacterTextSplitter** - Fallback for oversized chunks

```python
def chunk_text(text, chunk_size=1000, chunk_overlap=200):
    md_splitter = MarkdownTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = md_splitter.split_text(text)
    
    if any(len(c) > chunk_size * 1.5 for c in chunks):
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        chunks = splitter.split_text(text)
    
    return chunks
```

### Step 4: Vector Storage

Chunks are stored in ChromaDB Cloud with metadata:

```python
ids = [hashlib.md5(f"{url}_{i}".encode()).hexdigest() for i in range(len(chunks))]
metadatas = [{"source_url": url, "chunk_index": i} for i in range(len(chunks))]

collection.upsert(
    ids=ids,
    documents=chunks,
    metadatas=metadatas
)
```

Each chunk stores:
- `source_url`: Original page URL (used for filtering during retrieval)
- `chunk_index`: Position in the original document

## LangGraph Workflow

The chatbot uses a 3-node LangGraph pipeline:

### Node 1: Find Relevant Links

Instead of querying all vectors directly, the LLM first identifies which URLs are likely to contain the answer:

```python
def find_relevant_links(state: GraphState) -> GraphState:
    # LLM analyzes the question against all available URLs
    # Returns up to 50 most relevant URLs
    structured_llm = llm.with_structured_output(RelevantLinksOutput)
    response = structured_llm.invoke([
        {"role": "system", "content": system_prompt.format(links=links_context)},
        {"role": "user", "content": prompt}
    ])
    return {"relevant_links": response.links}
```

This pre-filtering step improves retrieval precision by narrowing the search space.

### Node 2: Retrieve Chunks

Queries ChromaDB with metadata filtering on the relevant URLs:

```python
def retrieve_chunks(state: GraphState) -> GraphState:
    results = collection.query(
        query_texts=[prompt],
        n_results=10,
        where={"source_url": {"$in": relevant_links}}  # Filter by pre-selected URLs
    )
    return {"retrieved_chunks": retrieved_chunks}
```

The `$in` filter ensures we only search within documents from URLs identified in Node 1.

### Node 3: Generate Answer

Combines retrieved chunks with conversation history to generate the final response:

```python
def generate_answer(state: GraphState) -> GraphState:
    # Format chunks with source attribution
    for chunk in chunks:
        source_url = chunk["metadata"].get("source_url")
        context_parts.append(f"[Source]: {source_url}\n{chunk['content']}")
    
    # Generate with conversation history for follow-up questions
    structured_llm = llm.with_structured_output(AnswerOutput)
    response = structured_llm.invoke([...])
    return {"answer": response.answer}
```

### Conversation Memory

Uses LangGraph's MemorySaver for multi-turn conversations:

```python
memory = MemorySaver()
workflow_app = graph.compile(checkpointer=memory)
```

The state includes message history with a reducer to accumulate messages:

```python
class GraphState(TypedDict):
    prompt: str
    relevant_links: List[str]
    retrieved_chunks: List[dict]
    answer: str
    messages: Annotated[List[BaseMessage], operator.add]
```

## API

### POST /chat

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "How does GitLab handle merge requests?"}'
```

Response:
```json
{
  "reply": "GitLab handles merge requests by...",
  "status": "success"
}
```

## Setup

### Environment Variables

Create a `.env` file:

```env
OPENAI_API_KEY=your_openai_key
CHROMA_API_KEY=your_chroma_key
CHROMA_DATABASE=your_database
CHROMA_TENANT=your_tenant
JINA_API_KEY=your_jina_key
FIRECRAWL_API_KEY=your_firecrawl_key
```

### Local Development

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload
```

### Docker

```bash
docker build -t gitlab-ai-bot .
docker run -p 8000:8000 --env-file .env gitlab-ai-bot
```

## Indexing New Content

To re-index the documentation:

```bash
cd rag

# 1. Generate sitemap
python sitemap.py

# 2. Filter links (manual curation or script)
# Edit filtered_links.json

# 3. Scrape and index
python data_scrapping.py
```

## Tech Stack

- **LLM**: OpenAI GPT-4o
- **Orchestration**: LangGraph
- **Vector Database**: ChromaDB Cloud
- **Web Scraping**: Jina AI Reader, Firecrawl
- **Text Splitting**: LangChain text splitters
- **API Framework**: FastAPI
- **Containerization**: Docker
