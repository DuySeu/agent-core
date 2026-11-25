"""Chat endpoint."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.constants import model
from core.wiring import build_llm

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
    answer: str | None = None
    input_tokens: int
    output_tokens: int


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Send a single message to the LLM and return the full answer."""
    llm = build_llm(req.provider, req.max_tokens)
    try:
        response = llm.invoke(
            req.model_id, [{"role": "user", "content": req.message}], req.system_prompt
        )
        return ChatResponse(
            answer=response.answer,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """Stream the LLM answer chunk-by-chunk as plain text."""
    llm = build_llm(req.provider, req.max_tokens)

    def token_generator():
        try:
            for chunk in llm.invoke_stream(
                req.model_id, [{"role": "user", "content": req.message}], req.system_prompt
            ):
                if chunk.delta:
                    yield chunk.delta
        except Exception as e:
            yield f"\n[error] {type(e).__name__}: {e}"

    return StreamingResponse(token_generator(), media_type="text/plain")
