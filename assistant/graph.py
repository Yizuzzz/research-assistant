"""
Construcción de los grafos.

Grafo principal:
    START -> create_analysts -> [PAUSA] human_feedback
        -> (feedback) create_analysts
        -> (aprobado) conduct_interview x N en paralelo
        -> write_report + write_introduction + write_conclusion (en paralelo)
        -> finalize_report -> END

El checkpointer (MemorySaver) es necesario para poder pausar el grafo
en human_feedback y reanudarlo después.
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

from .analysts import create_analysts, human_feedback, initiate_all_interviews
from .interview import (
    generate_answer,
    generate_question,
    route_messages,
    save_interview,
    search_web,
    search_wikipedia,
    write_section,
)
from .report import finalize_report, write_conclusion, write_introduction, write_report
from .schemas import InterviewState, ResearchGraphState


def build_interview_graph():
    """Subgrafo que ejecuta la entrevista de UN analista."""
    builder = StateGraph(InterviewState)
    builder.add_node("ask_question", generate_question)
    builder.add_node("search_web", search_web)
    builder.add_node("search_wikipedia", search_wikipedia)
    builder.add_node("answer_question", generate_answer)
    builder.add_node("save_interview", save_interview)
    builder.add_node("write_section", write_section)

    builder.add_edge(START, "ask_question")
    builder.add_edge("ask_question", "search_web")
    builder.add_edge("ask_question", "search_wikipedia")
    builder.add_edge("search_web", "answer_question")
    builder.add_edge("search_wikipedia", "answer_question")
    builder.add_conditional_edges("answer_question", route_messages, ['ask_question', 'save_interview'])
    builder.add_edge("save_interview", "write_section")
    builder.add_edge("write_section", END)

    return builder.compile()


def build_research_graph():
    """Grafo principal que orquesta analistas, entrevistas y reporte."""
    builder = StateGraph(ResearchGraphState)
    builder.add_node("create_analysts", create_analysts)
    builder.add_node("human_feedback", human_feedback)
    builder.add_node("conduct_interview", build_interview_graph())
    builder.add_node("write_report", write_report)
    builder.add_node("write_introduction", write_introduction)
    builder.add_node("write_conclusion", write_conclusion)
    builder.add_node("finalize_report", finalize_report)

    builder.add_edge(START, "create_analysts")
    builder.add_edge("create_analysts", "human_feedback")
    builder.add_conditional_edges("human_feedback", initiate_all_interviews, ["create_analysts", "conduct_interview"])
    builder.add_edge("conduct_interview", "write_report")
    builder.add_edge("conduct_interview", "write_introduction")
    builder.add_edge("conduct_interview", "write_conclusion")
    builder.add_edge(["write_conclusion", "write_report", "write_introduction"], "finalize_report")
    builder.add_edge("finalize_report", END)

    # El checkpointer guarda el estado entre pausas. Registramos Analyst como tipo
    # permitido para que LangGraph pueda restaurarlo sin avisos de seguridad.
    checkpointer = MemorySaver(
        serde=JsonPlusSerializer(allowed_msgpack_modules=[("assistant.schemas", "Analyst")])
    )

    # interrupt_before: el grafo se detiene antes de human_feedback para revisar analistas
    return builder.compile(interrupt_before=['human_feedback'], checkpointer=checkpointer)
