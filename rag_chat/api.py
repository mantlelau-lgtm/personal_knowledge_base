from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from .chat import RAGChat


router = APIRouter(prefix="/chat", tags=["chat"])
_chat = RAGChat()


class ChatRequest(BaseModel):
    query: str
    top_k: int = 5


@router.post("")
def chat(request: ChatRequest):
    return _chat.ask(request.query, top_k=request.top_k).__dict__


@router.post("/stream")
def stream_chat(request: ChatRequest):
    return StreamingResponse(_chat.stream_ask(request.query, top_k=request.top_k), media_type="text/plain")
