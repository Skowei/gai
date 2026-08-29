from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, START, END
from app.core.agent.state import AgentState
from app.core.agent.nodes import (
    fetch_memory_node,
    cognitive_core_node,
    execute_mcp_tools_node,
    reflect_and_finalize_node
)

def route_next_step(state: Any) -> Literal["execute_mcp_tools", "reflect_and_finalize"]:
    """
    [L0 PACKET ROUTER] 
    Directs the graph flow safely based on cognitive engine decisions.
    """
    next_step = state.get("next_step") if isinstance(state, dict) else getattr(state, "next_step", None)
    
    # Jeśli model kognitywny zgłosi chęć użycia sieci lub zapisu pliku, idziemy do narzędzi
    if next_step and next_step != "FINISH":
        print(f"[Router Grafu] Action requested: {next_step}. Routing directly to execution tools.")
        return "execute_mcp_tools"
    
    print("[Router Grafu] No tools required. Routing directly to final text synthesis.")
    return "reflect_and_finalize"

def build_cognitive_graph():
    """
    Compiles the asynchronous Enterprise L0-L4 linear cognitive graph.
    Forces direct execution paths to prevent multi-turn prompt pollution.
    """
    workflow = StateGraph(AgentState)

    # 1. Rejestracja modułowych węzłów operacyjnych z podfolderu nodes/
    workflow.add_node("fetch_memory", fetch_memory_node)
    workflow.add_node("cognitive_core", cognitive_core_node)
    workflow.add_node("execute_mcp_tools", execute_mcp_tools_node)
    workflow.add_node("reflect_and_finalize", reflect_and_finalize_node)

    # 2. Definicja stałych połączeń (Edges)
    workflow.add_edge(START, "fetch_memory")
    workflow.add_edge("fetch_memory", "cognitive_core")

    # 3. Definicja dynamicznego routingu (Conditional Edges)
    workflow.add_conditional_edges(
        "cognitive_core",
        route_next_step,
        {
            "execute_mcp_tools": "execute_mcp_tools",
            "reflect_and_finalize": "reflect_and_finalize"
        }
    )

    # 🚨 KRYTYCZNA POPRAWKA: Po wykonaniu narzędzia (zapisu pliku lub przeszukania sieci)
    # przekierowujemy stan grafu PROSTO do syntezy (reflect_and_finalize).
    # Całkowicie odcinamy powrót do cognitive_core, uniemożliwiając nadpisywanie szyny danych!
    workflow.add_edge("execute_mcp_tools", "reflect_and_finalize")
    
    # Wyjście z syntezy kończy działanie systemu
    workflow.add_edge("reflect_and_finalize", END)

    return workflow.compile()

# Eksport skompilowanej instancji mózgu dla bramy FastAPI
agent_brain = build_cognitive_graph()
