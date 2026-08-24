
"""AI Ecosystem V2.0 - LangGraph Workflow
Kompilacja grafu i endpointy API
"""

import os
import sys

# Dodanie root projektu do sys.path dla importów względnych
sys.path.insert(0, '/home/maciei/dev/ai')

from langgraph.graph import MessagesState, START, END
import redis
from dotenv import load_dotenv

# Try module imports first, fall back to absolute imports for script execution
try:
    from .state import AgentState
    from .nodes import (
        route_to_code_analysis,
        route_to_reasoning,
        route_to_text_handling,
        code_analysis_node,
        reasoning_node,
        text_processing_node,
        vision_processing_node,
        fetch_memory_node,
        execute_tools_node,
        generate_final_response_node,
    )
except ImportError:
    # Fallback for running as a script directly
    from src.graph.state import AgentState
    from src.graph.nodes import (
        route_to_code_analysis,
        route_to_reasoning,
        route_to_text_handling,
        code_analysis_node,
        reasoning_node,
        text_processing_node,
        vision_processing_node,
        fetch_memory_node,
        execute_tools_node,
        generate_final_response_node,
    )


def build_graph() -> "StateGraph":
    """Budowanie i kompilacja workflowu LangGraph."""

    from langgraph.graph import StateGraph

    graph_builder = (
        StateGraph(AgentState)
        .add_node("router", route_to_code_analysis)
        .add_node("code_analysis", code_analysis_node)
        .add_node("reasoning_node", reasoning_node)
        .add_node("text_processing", text_processing_node)
        .add_node("fetch_memory", fetch_memory_node)
        .add_node("execute_tools", execute_tools_node)
        .add_node("generate_final_response", generate_final_response_node)
        .add_edge(START, "router")
        .add_conditional_edges("router", route_to_code_analysis, {"code_analysis": "code_analysis", "reasoning_node": "reasoning_node", "text_processing": "text_processing"})
    )

    return graph_builder.compile()
if __name__ == '__main__':
    import sys
    from dotenv import load_dotenv
    
    # Załadowanie zmiennych środowiskowych
    load_dotenv()
    
    # Pobranie komunikatu od użytkownika (jeśli podano jako argument)
    user_message = sys.argv[1] if len(sys.argv) > 1 else "Hello"
    
    ollama_host = os.getenv("OLLAMA_HOST", "host.docker.internal")
    
    # Inicjalizacja Redis
    redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    
    # Inicjalizacja MemoryClient (PostgreSQL) - ujednolicony format connection string
    pg_connection_string = (
        f"postgresql://{os.getenv('MEMORY_PG_USER', 'agent')}:"
        f"{os.getenv('MEMORY_PG_PASSWORD', 'your_secure_password')}@"
        f"{os.getenv('MEMORY_PG_HOST', 'host.docker.internal')}/"
        f"{os.getenv('MEMORY_PG_DATABASE', 'ai_memory')}?port={os.getenv('MEMORY_PG_PORT', 5432)}"
    )

    from src.memory.client import MemoryClient, MemoryConfig

    config = MemoryConfig(
        pg_connection_string=pg_connection_string,
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0")
    )
    memory_client = MemoryClient(config)
    
    # Inicjalizacja workflowu LangGraph (test dry-run)
    print("\n▶ Testing AI Ecosystem V2.0 Workflow...\n")
    
    from langgraph.graph import StateGraph
    graph_state = AgentState(messages=[{"role": "user", "content": user_message}])
    
    # Budowanie i kompilacja grafu
    workflow_graph = build_graph()
    
    # Dry-run test z przykładowym query
    print(f"  [1] Uruchomienie dry-run testu z query: '{user_message}'\n")
    
    try:
        result_state = workflow_graph.invoke(graph_state)
        
        print(f"  ✅ Test zakończony pomyślnie!")
        print(f"\n📊 Wyniki testu:")
        print(f"   - final_response: {result_state.get('final_response', 'N/A')[:200]}")
        print(f"   - tool_responses: {len(result_state.get('tool_responses', []))} narzędzi")
        
        result = {
            "status": "AI Ecosystem V2.0 initialized",
            "ollama_host": ollama_host,
            "redis_status": "Connected" if redis_client.ping() else "Disconnected",
            "test_result": "dry-run_success",
            "final_response_preview": result_state.get('final_response', ''),
        }
    except Exception as e:
        print(f"\n❌ Test dry-run nieudany: {str(e)}")
        import traceback
        traceback.print_exc()
        
        result = {
            "status": "AI Ecosystem V2.0 initialized",
            "ollama_host": ollama_host,
            "redis_status": "Connected" if redis_client.ping() else "Disconnected",
            "test_result": f"dry-run_error: {str(e)}",
        }
    
    print(f"\nStatus: {result['status']}")
    print(f"Test: {result['test_result']}")

