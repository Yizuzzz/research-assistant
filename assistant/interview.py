"""
Subgrafo de entrevista: un analista entrevista a un "experto" que responde
usando únicamente lo que encuentra en la web (Tavily) y en Wikipedia.

Flujo por cada analista:
    ask_question -> (search_web + search_wikipedia en paralelo) -> answer_question
        -> se repite hasta max_num_turns o hasta que el analista agradece
    -> save_interview -> write_section
"""
import logging
import threading
import time
from datetime import timedelta

import wikipedia
from langchain_community.document_loaders import WikipediaLoader
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, get_buffer_string

from .config import get_llm, get_tavily
from .prompts import (
    ANSWER_INSTRUCTIONS,
    QUESTION_INSTRUCTIONS,
    SEARCH_INSTRUCTIONS,
    SECTION_WRITER_INSTRUCTIONS,
    report_language,
)
from .schemas import InterviewState, SearchQuery

logger = logging.getLogger("research_assistant")

# Wikipedia limita las peticiones de clientes anónimos (error 429) y puede pedir
# esperas de casi un minuto. Para que eso no frene la investigación:
# - identificamos al cliente y espaciamos las peticiones,
# - hacemos una búsqueda a la vez (las entrevistas corren en paralelo),
# - si Wikipedia bloquea, la omitimos un rato y seguimos solo con la búsqueda web.
wikipedia.set_user_agent("research-assistant/1.0 (LangGraph research assistant; python-wikipedia)")
wikipedia.set_rate_limiting(True, min_wait=timedelta(milliseconds=500))
_WIKI_LOCK = threading.Lock()
_WIKI_COOLDOWN_SECONDS = 120
_wiki_blocked_until = 0.0


def _load_wikipedia(query: str):
    """Busca en Wikipedia; si está bloqueada temporalmente devuelve [] sin esperar."""
    global _wiki_blocked_until
    with _WIKI_LOCK:
        if time.monotonic() < _wiki_blocked_until:
            logger.debug("Wikipedia en pausa por límite de peticiones; se omite: %s", query)
            return []
        try:
            return WikipediaLoader(query=query, load_max_docs=2).load()
        except Exception:
            # Un 429 llega como JSONDecodeError desde la librería: pausamos Wikipedia
            _wiki_blocked_until = time.monotonic() + _WIKI_COOLDOWN_SECONDS
            logger.warning(
                "Wikipedia limitó las peticiones; se usará solo la búsqueda web durante %s s.",
                _WIKI_COOLDOWN_SECONDS,
            )
            return []


def generate_question(state: InterviewState):
    """ Node to generate a question """
    analyst = state["analyst"]
    messages = state["messages"]

    system_message = QUESTION_INSTRUCTIONS.format(goals=analyst.persona)
    question = get_llm().invoke([SystemMessage(content=system_message)] + messages)
    return {"messages": [question]}


def _generate_search_query(state: InterviewState) -> str:
    """Convierte la última pregunta del analista en una consulta de búsqueda."""
    structured_llm = get_llm().with_structured_output(SearchQuery)
    search_query = structured_llm.invoke([SystemMessage(content=SEARCH_INSTRUCTIONS)] + state['messages'])
    logger.debug("Consulta de búsqueda: %s", search_query.search_query)
    return search_query.search_query


def search_web(state: InterviewState):
    """ Retrieve docs from web search """
    try:
        query = _generate_search_query(state)
        data = get_tavily().invoke({"query": query})
        search_docs = data.get("results", []) if isinstance(data, dict) else data

        formatted_search_docs = "\n\n---\n\n".join(
            f'<Document href="{doc["url"]}"/>\n{doc["content"]}\n</Document>'
            for doc in search_docs
        )
        return {"context": [formatted_search_docs]}
    except Exception as e:
        # Un fallo en la búsqueda no debe detener toda la investigación
        logger.warning("Falló la búsqueda web: %s", e)
        return {"context": []}


def search_wikipedia(state: InterviewState):
    """ Retrieve docs from wikipedia """
    try:
        query = _generate_search_query(state)
        search_docs = _load_wikipedia(query)

        formatted_search_docs = "\n\n---\n\n".join(
            f'<Document source="{doc.metadata["source"]}" page="{doc.metadata.get("page", "")}"/>\n{doc.page_content}\n</Document>'
            for doc in search_docs
        )
        return {"context": [formatted_search_docs]}
    except Exception as e:
        logger.warning("Falló la búsqueda en Wikipedia: %s", e)
        return {"context": []}


def generate_answer(state: InterviewState):
    """ Node to answer a question """
    analyst = state["analyst"]
    messages = state["messages"]
    context = state["context"]

    system_message = ANSWER_INSTRUCTIONS.format(goals=analyst.persona, context=context)
    answer = get_llm().invoke([SystemMessage(content=system_message)] + messages)

    # Marcamos el mensaje como del experto (lo usa route_messages para contar turnos)
    answer.name = "expert"
    return {"messages": [answer]}


def save_interview(state: InterviewState):
    """ Save interviews """
    interview = get_buffer_string(state["messages"])
    return {"interview": interview}


def route_messages(state: InterviewState, name: str = "expert"):
    """ Route between question and answer """
    messages = state["messages"]
    max_num_turns = state.get('max_num_turns', 2)

    # Termina si el experto ya respondió el máximo de turnos
    num_responses = len(
        [m for m in messages if isinstance(m, AIMessage) and m.name == name]
    )
    if num_responses >= max_num_turns:
        return 'save_interview'

    # Termina si la última pregunta del analista cierra la entrevista
    last_question = messages[-2]
    if "Thank you so much for your help" in last_question.content:
        return 'save_interview'
    return "ask_question"


def write_section(state: InterviewState):
    """ Node to write a report section from the interview sources """
    context = state["context"]
    analyst = state["analyst"]

    system_message = SECTION_WRITER_INSTRUCTIONS.format(focus=analyst.description) \
        + report_language(state.get("report_language", "en"))
    section = get_llm().invoke(
        [SystemMessage(content=system_message)]
        + [HumanMessage(content=f"Use this source to write your section: {context}")]
    )
    return {"sections": [section.content]}
