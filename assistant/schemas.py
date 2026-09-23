"""
Esquemas de datos y estados de los grafos.

- Analyst / Perspectives -> salida estructurada al crear el equipo de analistas
- SearchQuery            -> consulta de búsqueda generada a partir de la entrevista
- GuardDecision          -> resultado del filtro que valida temas y feedback
- InterviewState         -> estado del subgrafo de entrevista (uno por analista)
- ResearchGraphState     -> estado del grafo principal
"""
import operator
from typing import Annotated, List, Literal

from langgraph.graph import MessagesState
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class Analyst(BaseModel):
    affiliation: str = Field(
        description="Primary affiliation of the analyst.",
    )
    name: str = Field(
        description="Name of the analyst."
    )
    role: str = Field(
        description="Role of the analyst in the context of the topic.",
    )
    description: str = Field(
        description="Description of the analyst focus, concerns, and motives.",
    )

    @property
    def persona(self) -> str:
        return f"Name: {self.name}\nRole: {self.role}\nAffiliation: {self.affiliation}\nDescription: {self.description}\n"


class Perspectives(BaseModel):
    analysts: List[Analyst] = Field(
        description="Comprehensive list of analysts with their roles and affiliations.",
    )


class SearchQuery(BaseModel):
    search_query: str = Field(None, description="Search query for retrieval.")


class GuardDecision(BaseModel):
    """Decision on whether the user's input is allowed."""
    is_valid: bool = Field(description="True only if the input is allowed.")
    message: str = Field(
        description="Short message for the user, written in the same language as the user's input. "
                    "If the input is not valid, explain briefly why and what the assistant can do."
    )
    language: Literal["es", "en"] = Field(
        description="Language of the user's input: 'es' if it is written in Spanish, 'en' otherwise."
    )


class InterviewState(MessagesState):
    max_num_turns: int  # Número de turnos pregunta/respuesta
    context: Annotated[list, operator.add]  # Documentos encontrados (se acumulan)
    analyst: Analyst  # Analista que hace las preguntas
    interview: str  # Transcripción de la entrevista
    sections: list  # Clave que se copia al estado principal (Send API)
    # Idioma del reporte. Se llama distinto que en el estado principal a propósito:
    # si compartieran nombre, las entrevistas en paralelo intentarían escribir la
    # misma clave del grafo principal a la vez y LangGraph lanzaría un error.
    report_language: str


class ResearchGraphState(TypedDict):
    topic: str  # Tema de investigación
    max_analysts: int  # Número de analistas
    language: str  # Idioma del reporte: "es" o "en"
    human_analyst_feedback: str  # Feedback humano sobre los analistas
    analysts: List[Analyst]  # Analistas que hacen las entrevistas
    sections: Annotated[list, operator.add]  # Secciones de cada entrevista (Send API)
    introduction: str  # Introducción del reporte final
    content: str  # Cuerpo del reporte final
    conclusion: str  # Conclusión del reporte final
    final_report: str  # Reporte final completo
