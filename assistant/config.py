"""
Configuración general: variables de entorno, modelo de lenguaje y buscador web.

- Lee las claves desde un archivo .env (si existe) o las pide por terminal.
- El modelo y el buscador se crean de forma "perezosa" (lazy) para que las
  claves ya estén cargadas cuando se instancien.
"""
import getpass
import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Modelo por defecto (se puede cambiar con la variable OPENAI_MODEL en el .env)
DEFAULT_MODEL = "gpt-4o-mini"


def _set_env(var: str) -> None:
    """Si la variable no existe en el entorno, se pide al usuario de forma oculta."""
    value = os.environ.get(var)
    if not value:
        value = getpass.getpass(f"{var}: ")
    os.environ[var] = value


def setup_environment() -> None:
    """Carga el .env y asegura que las claves necesarias estén definidas."""
    load_dotenv()

    # Obligatorias: OpenAI (modelo) y Tavily (búsqueda web)
    _set_env("OPENAI_API_KEY")
    _set_env("TAVILY_API_KEY")

    # LangSmith es opcional: solo activamos el tracing si hay clave configurada.
    if os.environ.get("LANGSMITH_API_KEY"):
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", "research-assistant")
    else:
        # Sin clave, desactivamos el tracing para evitar errores 401 en consola
        for var in ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2",
                    "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2"):
            os.environ[var] = "false"


@lru_cache(maxsize=1)
def get_llm() -> ChatOpenAI:
    """Devuelve una única instancia del modelo (se reutiliza en todos los nodos)."""
    model_name = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    return ChatOpenAI(model=model_name, temperature=0)


@lru_cache(maxsize=1)
def get_tavily():
    """Buscador web Tavily (máximo 3 resultados por búsqueda)."""
    from langchain_tavily import TavilySearch
    return TavilySearch(max_results=3)
