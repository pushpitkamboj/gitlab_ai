import os
import json
import requests
import hashlib
from dotenv import load_dotenv
load_dotenv()

from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownTextSplitter
import chromadb

api_key = os.getenv("CHROMA_API_KEY")
database = os.getenv("CHROMA_DATABASE")
tenant = os.getenv("CHROMA_TENANT")

def scrape_with_jina(url):
    jina_url = f"https://r.jina.ai/{url}"
    
    response = requests.get(
        jina_url,
        headers={
            "X-Return-Format": "markdown",
            "X-With-Generated-Alt": "true",
            "Authorization": f"Bearer {os.getenv('JINA_API_KEY')}",
            "X-Extract-Only-Main-Content": "true",
        },
        timeout=30
    )
    return response.text

def chunk_text(text, chunk_size=1000, chunk_overlap=200):
    md_splitter = MarkdownTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )
    
    chunks = md_splitter.split_text(text)
    
    if any(len(c) > chunk_size * 1.5 for c in chunks):
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        chunks = splitter.split_text(text)
    
    return chunks

def process_all_links(input_file="filtered_links.json"):
    with open(input_file, 'r', encoding='utf-8') as f:
        all_urls = json.load(f)
    
    api_key = os.getenv("CHROMA_API_KEY")
    database = os.getenv("CHROMA_DATABASE")
    tenant = os.getenv("CHROMA_TENANT")

    client = chromadb.CloudClient(
        api_key=api_key, database=database, tenant=tenant
    )

    collection = client.get_collection(name="handbook")
    
    total_chunks = 0
    failed_urls = []
    
    for idx, url in enumerate(all_urls):
        try:
            content = scrape_with_jina(url)
            
            if not content or len(content) < 100:
                continue
            
            chunks = chunk_text(content)
            
            if not chunks:
                continue
            
            ids = [hashlib.md5(f"{url}_{i}".encode()).hexdigest() for i in range(len(chunks))]
            metadatas = [{"source_url": url, "chunk_index": i} for i in range(len(chunks))]
            
            BATCH_SIZE = 300
            for i in range(0, len(ids), BATCH_SIZE):
                collection.upsert(
                    ids=ids[i:i+BATCH_SIZE],
                    documents=chunks[i:i+BATCH_SIZE],
                    metadatas=metadatas[i:i+BATCH_SIZE]
                )
            
            total_chunks += len(chunks)
            
        except Exception as e:
            failed_urls.append({'url': url, 'error': str(e)})
    
    if failed_urls:
        with open('failed_urls.json', 'w', encoding='utf-8') as f:
            json.dump(failed_urls, f, indent=2)

if __name__ == "__main__":
    process_all_links()
