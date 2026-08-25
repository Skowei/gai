"""
==============================================================================
AI Ecosystem V2.0 - LangGraph Workflow
START -> fetch_memory -> router -> (kod|logika|tekst) -> tools -> odpowiedź
Uruchomienie dry-run:  python3 -m src.graph.workflow "Twoje pytanie"
==============================================================================
"""

import os
import sys

sys.path.insert(0, "/home/maciei/dev/ai")

from dotenv import load_dotenv

try:
    from .state import AgentState
    from .nodes import (
        fetch_memory_node,
        router_node,
        route_next,
        code_analysis_node,
        reasoning_node,
        text_processing_node,
        execute_tools_node,
        generate_final_response_node,
    )
except ImportError:
    from src.graph.state import AgentState
    from src.graph.nodes import (
        fetch_memory_node,
        router_node,
        route_next,
        code_analysis_node,
        reasoning_node,
        text_processing_node,
        execute_tools_node,
        generate_final_response_node,
    )


def build_graph():
    """Budowanie i kompilacja workflowu LangGraph (pełny przepływ)."""
    from langgraph.graph import StateGraph, START, END

    graph_builder = StateGraph(AgentState)

    graph_builder.add_node("fetch_memory", fetch_memory_node)
    graph_builder.add_node("router", router_node)
    graph_builder.add_node("code_analysis", code_analysis_node)
    graph_builder.add_node("reasoning_node", reasoning_node)
    graph_builder.add_node("text_processing", text_processing_node)
    graph_builder.add_node("execute_tools", execute_tools_node)
    graph_builder.add_node("generate_final_response", generate_final_response_node)

    # Przepływ główny:
    # START -> pamięć -> routing -> wybrany model -> narzędzia -> odpowiedź
    graph_builder.add_edge(START, "fetch_memory")
    graph_builder.add_edge("fetch_memory", "router")
    graph_builder.add_conditional_edges(
        "router",
        route_next,
        {
            "code_analysis": "code_analysis",
            "reasoning_node": "reasoning_node",
            "text_processing": "text_processing",
        },
    )

    # Każda gałąź modelu trafia do narzędzi, potem do finalnej odpowiedzi
    for node_name in ("code_analysis", "reasoning_node", "text_processing"):
        graph_builder.add_edge(node_name, "execute_tools")

    graph_builder.add_edge("execute_tools", "generate_final_response")
    graph_builder.add_edge("generate_final_response", END)

    return graph_builder.compile()


def _default_graph():
    """Stwórenie grafu bez dotenv/redis (czyste budowanie)."""
    return build_graph()


if __name__ == "__main__":
    load_dotenv()
    user_message = sys.argv[1] if len(sys.argv) > 1 else "Cześć! Opowiedz po polsku."

    print("\n▶ Testing AI Ecosystem V2.0 Workflow...")
    print(f"  Query: '{user_message}'\n")

    # Rozwiąż automatyśny graf (bez wywołania zdanych usług zewnątre)
    try:
        graph = build_graph()
        print("  ✅ Workflow skompilowano (dry-run)")
        print()
        print("  Przebudowny przepływ:")
        print("    START -> fetch_memory -> router")
        print("      ├─ kod      ─► code_analysis ─► execute_tools")
        print("      ├─ logika   ─► reasoning     ─► execute_tools")
        print("      └─ tekst    ─► text          ─► execute_tools")
        print("                                ▼")
        print("              generate_final_response -> END")
        print()
        print("  (Z apogini: w pełnym środowizie Docker każdof")
        print("   węzeł woła prawdziwą modelia Ollama + bazy)")
    except Exception as exc:
        import traceback
        traceback.print_exc()
        sys.exit(1)