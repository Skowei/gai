import json
import time
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Any
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.core.agent.brain import agent_brain
from app.core.config import settings

router = APIRouter(tags=["Cline / OpenAI API Compatibility"])

class OpenAIStyleMessage(BaseModel):
    role: str
    content: str

class ClineCompletionsRequest(BaseModel):
    model: str
    messages: List[OpenAIStyleMessage]
    stream: Optional[bool] = False
    tools: Optional[List[Any]] = None


@router.post("/api/v1/chat/completions")
@router.post("/api/chat/completions")
async def cline_chat_completions(payload: ClineCompletionsRequest, x_session_id: Optional[str] = Header(None)):
    """
    Asynchronous OpenAI-compatible API emulator for the Cline VS Code extension.
    Supports real-time token streaming mapped directly to the L0-L4 cognitive core.
    """
    try:
        # Dynamic fallback session management
        session_id = x_session_id or f"cline-session-{int(time.time())}"
        
        # Transform incoming OpenAI payload into native LangChain message objects
        graph_messages = []
        for msg in payload.messages:
            if msg.role == "user":
                graph_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                graph_messages.append(AIMessage(content=msg.content))
            elif msg.role == "system":
                graph_messages.append(SystemMessage(content=msg.content))

        # Build initial state configuration - fetch_memory_node handles the RAG automatically
        initial_state = {
            "messages": graph_messages, 
            "session_id": session_id,
            "target_role": "code_analysis"  # Enforces Qwen-2.5-Coder deployment target
        }

        async def token_stream_generator():
            chunk_id = f"chatcmpl-{int(time.time())}"
            created_time = int(time.time())
            
            # Use LangGraph asynchronous stream to capture real-time tokens from the final node
            async for event in agent_brain.astream(initial_state, stream_mode="updates"):
                # Track transitions inside the reflect_and_finalize node execution block
                if "reflect_and_finalize" in event:
                    node_output = event["reflect_and_finalize"]
                    # Extract active token mutations if streaming capability is available
                    raw_chunk = node_output.get("final_response", "")
                    
                    if raw_chunk:
                        chunk_payload = {
                            "id": chunk_id,
                            "object": "chat.completion.chunk",
                            "created": created_time,
                            "model": payload.model,
                            "choices": [{
                                "index": 0,
                                "delta": {"role": "assistant", "content": raw_chunk},
                                "finish_reason": None
                            }]
                        }
                        yield f"data: {json.dumps(chunk_payload)}\n\n"
            
            # Send standard OpenAI finalization packets to complete the connection cycle safely
            final_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": payload.model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
            }
            yield f"data: {json.dumps(final_chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(token_stream_generator(), media_type="text/event-stream")

    except Exception as exc:
        print(f"❌ [Cline API Exception] Routing failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/v1/models")
@router.get("/api/models")
async def cline_models_discovery():
    """
    [Dynamic Discovery] Automatically inspects config/models.yaml configuration parameters
    and exposes active Ollama LLM definitions formatted strictly to the OpenAI spec.
    """
    discovered_data = []
    try:
        for role_key, model_config in settings.models.items():
            # Exclude embedding engine as text editor extensions look for generation models only
            if hasattr(model_config, "name") and model_config.name and role_key != "embedding":
                discovered_data.append({
                    "id": model_config.name,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": getattr(model_config, "provider", "ollama")
                })
    except Exception as err:
        print(f"⚠️ [Models Discovery Warning] Could not scan active settings attributes: {err}")
        
    return {
        "object": "list",
        "data": discovered_data
    }
