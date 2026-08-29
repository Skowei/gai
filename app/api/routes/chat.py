from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.agent.brain import agent_brain
# Importujemy oficjalną klasę wiadomości ludzkiej, którą rozumie stan w state.py
from langchain_core.messages import HumanMessage

router = APIRouter(prefix="/v1", tags=["Czat Vue 3"])

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_session"

@router.post("/chat")
async def chat_endpoint(payload: ChatRequest):
    """Główny punkt wejścia dla aplikacji Vue 3 oraz Postmana."""
    try:
        # Przekazujemy instancję HumanMessage. 
        # Dzięki temu Pydantic v2 przejdzie walidację AgentState w ułamek milisekundy!
        initial_state = {
            "messages": [HumanMessage(content=payload.message)],
            "session_id": payload.session_id,
            "system_instructions": "Jesteś zaawansowanym, autonomicznym ekosystemem AI."
        }
        
        # Wywołanie maszyny stanów LangGraph
        final_state = await agent_brain.ainvoke(initial_state)
        
        return {
            "status": "success",
            "session_id": payload.session_id,
            "plan_executed": final_state.get("reason_response", ""),
            "tool_summary": final_state.get("tool_summary", ""),
            "response": final_state.get("final_response", "Brak odpowiedzi silnika.")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd jądra grafu: {str(e)}")
