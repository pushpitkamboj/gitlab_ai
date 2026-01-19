from dotenv import load_dotenv
load_dotenv()

import os
import uuid
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

from chatbot.graph import workflow_app

app = FastAPI(title="GitLab AI Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PromptInput(BaseModel):
    prompt: str

class PromptResponse(BaseModel):
    reply: str
    status: str

@app.post("/chat", response_model=PromptResponse)
async def chat(request: Request, data: PromptInput):
    """
    Process a prompt and return AI response.
    """
    logger.info(f"Received prompt: {data.prompt[:100]}...")
    
    try:
        thread_id = "009" #hardcoded because we dont have auth, or user_id
        logger.info(f"Created thread_id: {thread_id}")
        
        result = await workflow_app.ainvoke(
            input={"prompt": data.prompt},
            config={"configurable": {"thread_id": thread_id}}
        )
        
        logger.info(f"Workflow completed successfully for thread: {thread_id}")
        
        return JSONResponse(
            status_code=200,
            content={
                "reply": result.get("answer", ""),
                "status": "success"
            }
        )
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "reply": "An error occurred while processing your request.",
                "status": "error"
            }
        )

@app.get("/health")
def health():
    logger.info("Health check OK")
    return {"status": "ok"}