"""Chat endpoint."""

from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.constants import model
from models.llm_factory import LLM

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    provider: str = "openrouter"  # "openai" | "openrouter" | "bedrock"
    model_id: str = model.NEMOTRON_3_NANO_30B_A3B
    system_prompt: str = "You are a helpful assistant."
    max_tokens: int = 1000
    temperature: float = 0.7
    top_p: float = 0.9


class ChatResponse(BaseModel):
    answer: Optional[str] = None
    input_tokens: int
    output_tokens: int


def _build_llm(req: ChatRequest) -> LLM:
    inference_config = {
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "top_p": req.top_p,
    }
    return LLM(
        system_prompt=req.system_prompt,
        inference_config=inference_config,
        provider=req.provider,
        model_id=req.model_id,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Send a single message to the LLM and return the full answer."""
    llm = _build_llm(req)
    try:
        return llm.invoke(req.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """Stream the LLM answer chunk-by-chunk as plain text."""
    llm = _build_llm(req)

    def token_generator():
        try:
            for chunk in llm.invoke_stream(req.message):
                yield chunk
        except Exception as e:
            yield f"\n[error] {type(e).__name__}: {e}"

    return StreamingResponse(token_generator(), media_type="text/plain")
