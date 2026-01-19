import os
import json
from typing import List, TypedDict, Annotated
from dotenv import load_dotenv
load_dotenv()

from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
import chromadb
import operator

llm = init_chat_model("gpt-4o", model_provider="openai")

api_key = os.getenv("CHROMA_API_KEY")
database = os.getenv("CHROMA_DATABASE")
tenant = os.getenv("CHROMA_TENANT")

client = chromadb.CloudClient(
    api_key=api_key, database=database, tenant=tenant
)
collection = client.get_collection(name="handbook")

with open("rag/filtered_links.json", "r", encoding="utf-8") as f:
    ALL_LINKS = json.load(f)

class RelevantLinksOutput(BaseModel):
    links: List[str]

class AnswerOutput(BaseModel):
    answer: str
    sources: List[str]

class GraphState(TypedDict):
    prompt: str
    relevant_links: List[str]
    retrieved_chunks: List[dict]
    answer: str
    messages: Annotated[List[BaseMessage], operator.add]

def find_relevant_links(state: GraphState) -> GraphState:
    prompt = state["prompt"]
    messages = state.get("messages", [])
    
    conversation_context = ""
    if messages:
        recent_messages = messages[-8:]
        conversation_context = "\n\nRecent conversation history:\n"
        for msg in recent_messages:
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            conversation_context += f"{role}: {msg.content[:500]}...\n" if len(msg.content) > 500 else f"{role}: {msg.content}\n"
    
    links_context = "\n".join(ALL_LINKS)  
    
    system_prompt = """You are an expert at analyzing GitLab documentation structure.
    Given a user question and a list of available documentation URLs, identify the most relevant URLs 
    where the answer to the question might be found.

    Return maximum 50 relevant URLs.
    {conversation_context}
    Available URLs:
    {links}
    """
    
    structured_llm = llm.with_structured_output(RelevantLinksOutput)
    response = structured_llm.invoke([
        {"role": "system", "content": system_prompt.format(links=links_context, conversation_context=conversation_context)},
        {"role": "user", "content": prompt}
    ])
    
    relevant_links = response.links
    
    return {"relevant_links": relevant_links, "messages": [HumanMessage(content=prompt)]}

def retrieve_chunks(state: GraphState) -> GraphState:
    prompt = state["prompt"]
    relevant_links = state["relevant_links"]
    
    if not relevant_links:
        results = collection.query(
            query_texts=[prompt],
            n_results=10
        )
    else:
        results = collection.query(
            query_texts=[prompt],
            n_results=10,
            where={"source_url": {"$in": relevant_links}}
        )
    
    retrieved_chunks = []
    for i, doc in enumerate(results["documents"][0]):
        chunk_data = {
            "content": doc,
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i] if results.get("distances") else None
        }
        retrieved_chunks.append(chunk_data)
    
    return {"retrieved_chunks": retrieved_chunks}

def generate_answer(state: GraphState) -> GraphState:
    prompt = state["prompt"]
    chunks = state["retrieved_chunks"]
    messages = state.get("messages", [])
    
    context_parts = []
    sources = set()
    
    for i, chunk in enumerate(chunks, 1):
        source_url = chunk["metadata"].get("source_url", "Unknown")
        sources.add(source_url)
        context_parts.append(f"[Source {i}]: {source_url}\n{chunk['content']}\n")
    
    context = "\n---\n".join(context_parts)
    
    conversation_history = ""
    if messages:
        recent_messages = messages[-7:-1] if len(messages) > 1 else []
        if recent_messages:
            conversation_history = "\n\nPrevious conversation:\n"
            for msg in recent_messages:
                role = "User" if isinstance(msg, HumanMessage) else "Assistant"
                content = msg.content[:800] + "..." if len(msg.content) > 800 else msg.content
                conversation_history += f"{role}: {content}\n"
    
    system_prompt = """You are a helpful GitLab expert assistant. Answer the user's question based on the provided context from GitLab documentation.

Guidelines:
- Provide a clear, structured answer
- Use bullet points or numbered lists when appropriate
- Include relevant code examples if applicable
- If the context doesn't fully answer the question, say so
- Consider the conversation history when answering follow-up questions
- If the user refers to something from previous messages, use that context
{conversation_history}
Context from GitLab Documentation:
{context}

NOTE: if there is no context or very less context then dont say, no info available but instead reply according to what data you have about that prompt's potential reply.
NOTE2: the length of reply should depend on the relevancy and complexity of input prompt
"""
    
    structured_llm = llm.with_structured_output(AnswerOutput)
    response = structured_llm.invoke([
        {"role": "system", "content": system_prompt.format(context=context, conversation_history=conversation_history)},
        {"role": "user", "content": prompt}
    ])
    
    sources_list = "\n".join([f"- {s}" for s in response.sources])
    answer = f"{response.answer}"
    
    return {"answer": answer, "messages": [AIMessage(content=answer)]}

graph = StateGraph(GraphState)

graph.add_node(find_relevant_links)
graph.add_node(retrieve_chunks)
graph.add_node(generate_answer)

graph.add_edge(START, "find_relevant_links")
graph.add_edge("find_relevant_links", "retrieve_chunks")
graph.add_edge("retrieve_chunks", "generate_answer")
graph.add_edge("generate_answer", END)

memory = MemorySaver()

workflow_app = graph.compile(checkpointer=memory)
