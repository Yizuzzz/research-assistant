"""
Filtro de alcance (guardrail).

Antes de gastar búsquedas y llamadas al modelo, se valida que:
- el tema sea realmente un tema de investigación, y
- el feedback sea solo sobre el equipo de analistas.
Cualquier otra petición (código, traducciones, charla, etc.) se rechaza.
"""
from langchain_core.messages import HumanMessage, SystemMessage

from .config import get_llm
from .prompts import FEEDBACK_GUARD_INSTRUCTIONS, TOPIC_GUARD_INSTRUCTIONS
from .schemas import Analyst, GuardDecision

# Límite de longitud: los textos muy largos suelen ser intentos de meter instrucciones
MAX_INPUT_CHARS = 400


def _too_long(text: str) -> GuardDecision | None:
    if len(text) > MAX_INPUT_CHARS:
        return GuardDecision(
            is_valid=False,
            message=f"El texto es demasiado largo (máximo {MAX_INPUT_CHARS} caracteres). "
                    "Escribe solo el tema o el ajuste que quieres.",
        )
    return None


def check_topic(topic: str) -> GuardDecision:
    """Valida que el texto sea un tema de investigación permitido."""
    if rejected := _too_long(topic):
        return rejected
    guard = get_llm().with_structured_output(GuardDecision)
    return guard.invoke([
        SystemMessage(content=TOPIC_GUARD_INSTRUCTIONS),
        HumanMessage(content=topic),
    ])


def check_feedback(topic: str, analysts: list[Analyst], feedback: str) -> GuardDecision:
    """Valida que el feedback sea únicamente sobre el equipo de analistas."""
    if rejected := _too_long(feedback):
        return rejected
    analysts_text = "\n".join(a.persona for a in analysts)
    guard = get_llm().with_structured_output(GuardDecision)
    return guard.invoke([
        SystemMessage(content=FEEDBACK_GUARD_INSTRUCTIONS.format(topic=topic, analysts=analysts_text)),
        HumanMessage(content=feedback),
    ])
