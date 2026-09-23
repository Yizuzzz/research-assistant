"""
Nodos para crear el equipo de analistas y el punto de revisión humana.

Flujo:
    create_analysts -> human_feedback (el grafo se PAUSA aquí)
        - si hay feedback  -> vuelve a create_analysts
        - si no hay        -> lanza una entrevista en paralelo por analista (Send API)
"""
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Send

from .config import get_llm
from .prompts import ANALYST_INSTRUCTIONS, output_language
from .schemas import Perspectives, ResearchGraphState


def create_analysts(state: ResearchGraphState):
    """ Create analysts """
    topic = state['topic']
    max_analysts = state['max_analysts']
    human_analyst_feedback = state.get('human_analyst_feedback', '')

    # Salida estructurada: el modelo devuelve directamente una lista de Analyst
    structured_llm = get_llm().with_structured_output(Perspectives)

    system_message = ANALYST_INSTRUCTIONS.format(
        topic=topic,
        human_analyst_feedback=human_analyst_feedback,
        max_analysts=max_analysts,
    ) + output_language(state.get("language", "en"))  # analistas en el idioma del usuario
    analysts = structured_llm.invoke(
        [SystemMessage(content=system_message)] + [HumanMessage(content="Generate the set of analysts.")]
    )
    return {"analysts": analysts.analysts}


def human_feedback(state: ResearchGraphState):
    """ No-op node that should be interrupted on """
    # No hace nada: el grafo se detiene ANTES de este nodo para que el usuario
    # revise a los analistas. main.py escribe el feedback con graph.update_state().
    pass


def initiate_all_interviews(state: ResearchGraphState):
    """ This is the "map" step where we run each interview sub-graph using Send API """
    # Si hay feedback, se regeneran los analistas
    if state.get('human_analyst_feedback'):
        return "create_analysts"

    # Si no, se lanza una entrevista por analista, todas en paralelo
    topic = state["topic"]
    return [
        Send("conduct_interview", {
            "analyst": analyst,
            "report_language": state.get("language", "en"),
            "messages": [HumanMessage(content=f"So you said you were writing an article on {topic}?")],
        })
        for analyst in state["analysts"]
    ]
