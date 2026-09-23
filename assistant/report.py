"""
Nodos que redactan el reporte final (paso "reduce").

Cuando terminan todas las entrevistas se ejecutan en paralelo:
    write_report, write_introduction, write_conclusion
y después finalize_report las une en un solo documento Markdown.
"""
import re

from langchain_core.messages import HumanMessage, SystemMessage

from .config import get_llm
from .prompts import INTRO_CONCLUSION_INSTRUCTIONS, REPORT_WRITER_INSTRUCTIONS, report_language
from .schemas import ResearchGraphState


def _join_sections(state: ResearchGraphState) -> str:
    """Une las secciones de todas las entrevistas en un solo texto."""
    return "\n\n".join(f"{section}" for section in state["sections"])


def _language(state: ResearchGraphState) -> str:
    """Instrucción de idioma para los redactores (inglés si no se indicó)."""
    return report_language(state.get("language", "en"))


def write_report(state: ResearchGraphState):
    """ Write the body of the report from all the analyst memos """
    system_message = REPORT_WRITER_INSTRUCTIONS.format(
        topic=state["topic"], context=_join_sections(state)
    ) + _language(state)
    report = get_llm().invoke(
        [SystemMessage(content=system_message)] + [HumanMessage(content="Write a report based upon these memos.")]
    )
    return {"content": report.content}


def write_introduction(state: ResearchGraphState):
    """ Write the report introduction """
    instructions = INTRO_CONCLUSION_INSTRUCTIONS.format(
        topic=state["topic"], formatted_str_sections=_join_sections(state)
    ) + _language(state)
    intro = get_llm().invoke([instructions] + [HumanMessage(content="Write the report introduction")])
    return {"introduction": intro.content}


def write_conclusion(state: ResearchGraphState):
    """ Write the report conclusion """
    instructions = INTRO_CONCLUSION_INSTRUCTIONS.format(
        topic=state["topic"], formatted_str_sections=_join_sections(state)
    ) + _language(state)
    conclusion = get_llm().invoke([instructions] + [HumanMessage(content="Write the report conclusion")])
    return {"conclusion": conclusion.content}


# Encabezados que se traducen al ensamblar el reporte
HEADER_TRANSLATIONS = {
    "es": {"Introduction": "Introducción", "Conclusion": "Conclusión", "Sources": "Fuentes"},
    "en": {},
}

# Variantes aceptadas, por si el modelo ya tradujo el encabezado por su cuenta
_INSIGHTS_HEADER = re.compile(r"^\s*##\s*(Insights|Hallazgos|Perspectivas|Ideas clave)\s*\n", re.IGNORECASE)
_SOURCES_HEADER = re.compile(r"\n##\s*(Sources|Fuentes)\s*\n", re.IGNORECASE)


def _translate_headers(text: str, language: str) -> str:
    """Traduce los encabezados '## X' fijos al idioma del reporte."""
    for english, translated in HEADER_TRANSLATIONS.get(language, {}).items():
        text = re.sub(rf"^##\s*{english}\s*$", f"## {translated}", text, flags=re.MULTILINE)
    return text


def finalize_report(state: ResearchGraphState):
    """ The is the "reduce" step where we gather all the sections, combine them, and reflect on them to write the intro/conclusion """
    language = state.get("language", "en")
    content = state["content"]

    # Quitamos el título "## Insights" que genera write_report
    # (el notebook usaba strip(), que quitaba letras sueltas del inicio y del final)
    content = _INSIGHTS_HEADER.sub("", content, count=1)

    # Separamos las fuentes para ponerlas al final del documento
    sources = None
    parts = _SOURCES_HEADER.split(content, maxsplit=1)
    if len(parts) == 3:  # [contenido, nombre del encabezado, fuentes]
        content, _, sources = parts

    final_report = state["introduction"] + "\n\n---\n\n" + content + "\n\n---\n\n" + state["conclusion"]
    if sources is not None:
        final_report += "\n\n## Sources\n" + sources
    return {"final_report": _translate_headers(final_report, language)}
