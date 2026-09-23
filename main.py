"""
Punto de entrada: asistente de investigación interactivo en terminal.

Uso:
    python main.py                  # pide el nombre de usuario al iniciar
    python main.py --user jesus     # usuario definido desde la línea de comandos
    python main.py --debug          # muestra cada nodo del grafo y más detalle de errores

Flujo de cada investigación:
    1. Escribes un tema (se valida que sea un tema de investigación).
    2. Eliges cuántos analistas quieres (1 a 5).
    3. Revisas a los analistas: puedes pedir ajustes o aprobarlos con Enter.
    4. Los analistas entrevistan a expertos (web + Wikipedia) en paralelo.
    5. Se muestra el reporte final, se guarda en el historial y puedes exportarlo.

El programa se queda esperando nuevos temas hasta que escribas "salir".
"""
import argparse
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from assistant.config import setup_environment

console = Console()

HELP_TEXT = """
Escribe un tema para investigar, en español o en inglés. El reporte se genera
en el mismo idioma en que escribas el tema. Por ejemplo:
  Impacto de la inteligencia artificial en la educación en México
  The benefits of adopting LangGraph as an agent framework

Comandos disponibles:
  /historial      Lista tus investigaciones anteriores
  /ver <id>       Muestra un reporte del historial
  /exportar <id>  Guarda un reporte del historial como archivo .md en ./reports
  /debug          Activa o desactiva el modo depuración
  /ayuda          Muestra esta ayuda
  salir           Termina el programa (también: exit, quit, Ctrl+C)
"""

EXIT_WORDS = {"salir", "exit", "quit", "/salir"}
REPORTS_DIR = Path("reports")

# Nombres legibles de los nodos del grafo principal (para mostrar el progreso)
NODE_LABELS = {
    "create_analysts": "Equipo de analistas creado",
    "write_report": "Cuerpo del reporte redactado",
    "write_introduction": "Introducción redactada",
    "write_conclusion": "Conclusión redactada",
    "finalize_report": "Reporte final ensamblado",
}


# --------------------------------------------------------------------------
# Utilidades de entrada/salida
# --------------------------------------------------------------------------
def normalize_user_id(raw: str) -> str:
    """Normaliza el usuario para que "Jesus" y " jesus " apunten al mismo historial."""
    return raw.strip().lower() or "default"


def ask_int(prompt: str, low: int, high: int, default: int) -> int:
    """Pide un número entero dentro de un rango; Enter usa el valor por defecto."""
    while True:
        raw = input(prompt).strip()
        if not raw:
            return default
        if raw.isdigit() and low <= int(raw) <= high:
            return int(raw)
        print(f"  Escribe un número entre {low} y {high}.")


def show_analysts(analysts) -> None:
    """Imprime el equipo de analistas generado."""
    print()
    for i, analyst in enumerate(analysts, 1):
        print(f"  Analista {i}: {analyst.name}")
        print(f"    Afiliación:  {analyst.affiliation}")
        print(f"    Rol:         {analyst.role}")
        print(f"    Enfoque:     {analyst.description}")
        print("  " + "-" * 60)


def export_report(topic: str, report: str) -> Path:
    """Guarda el reporte en ./reports/<tema>-<fecha>.md y devuelve la ruta."""
    REPORTS_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:50] or "reporte"
    path = REPORTS_DIR / f"{slug}-{datetime.now():%Y%m%d-%H%M%S}.md"
    path.write_text(report, encoding="utf-8")
    return path


def parse_report_id(command: str) -> int | None:
    """Extrae el id de comandos como '/ver 3'."""
    parts = command.split()
    if len(parts) == 2 and parts[1].isdigit():
        return int(parts[1])
    print("  Indica el número del reporte, por ejemplo: /ver 3")
    return None


# --------------------------------------------------------------------------
# Ejecución del grafo
# --------------------------------------------------------------------------
def stream_graph(graph, graph_input, thread, debug: bool, total_interviews: int = 0) -> None:
    """
    Ejecuta el grafo hasta la siguiente pausa o hasta el final, mostrando el progreso.
    subgraphs=True permite ver también los nodos internos de cada entrevista en modo debug.
    """
    done_interviews = 0
    for namespace, update in graph.stream(graph_input, thread, stream_mode="updates", subgraphs=True):
        for node in update:
            if node.startswith("__"):  # eventos internos, como __interrupt__
                continue
            if debug:
                where = " > ".join(ns.split(":")[0] for ns in namespace) or "main"
                print(f"  [debug] {where} > {node}")
            # Solo mostramos el progreso de los nodos del grafo principal
            if namespace:
                continue
            if node == "conduct_interview":
                done_interviews += 1
                print(f"  [entrevista {done_interviews}/{total_interviews} completada]")
            elif node in NODE_LABELS and not debug:
                print(f"  [{NODE_LABELS[node]}]")


def run_research(graph, topic: str, max_analysts: int, language: str, debug: bool):
    """
    Ejecuta una investigación completa con revisión humana de los analistas.
    Devuelve un dict con los resultados, o None si el usuario la cancela.
    """
    from assistant.guard import check_feedback

    # Cada investigación usa su propio thread para no mezclar estados
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}}
    feedback_history: list[str] = []

    # Fase 1: crear analistas (el grafo se pausa antes de human_feedback)
    print("\n  [creando equipo de analistas...]")
    graph_input = {"topic": topic, "max_analysts": max_analysts, "language": language}
    stream_graph(graph, graph_input, thread, debug)

    # Fase 2: revisión humana (se repite hasta que el usuario apruebe)
    while True:
        analysts = graph.get_state(thread).values.get("analysts", [])
        show_analysts(analysts)
        feedback = input("\nAjustes a los analistas (Enter para aprobar, /cancelar para salir): ").strip()

        if feedback.lower() == "/cancelar":
            print("  [investigación cancelada]")
            return None

        if not feedback:
            # Aprobado: sin feedback, el grafo lanza las entrevistas
            graph.update_state(thread, {"human_analyst_feedback": None}, as_node="human_feedback")
            break

        # El feedback también pasa por el filtro de alcance
        decision = check_feedback(topic, analysts, feedback)
        if not decision.is_valid:
            print(f"\n  [no permitido] {decision.message}")
            continue

        # Se envía todo el feedback acumulado para no perder ajustes anteriores
        feedback_history.append(feedback)
        graph.update_state(
            thread, {"human_analyst_feedback": "\n".join(feedback_history)}, as_node="human_feedback"
        )
        print("\n  [ajustando equipo de analistas...]")
        stream_graph(graph, None, thread, debug)

    # Fase 3: entrevistas en paralelo y redacción del reporte
    print(f"\n  [investigando con {len(analysts)} analistas en paralelo, puede tardar unos minutos...]")
    stream_graph(graph, None, thread, debug, total_interviews=len(analysts))

    return {
        "analysts": [a.model_dump() for a in analysts],
        "feedback": feedback_history,
        "final_report": graph.get_state(thread).values.get("final_report"),
    }


# --------------------------------------------------------------------------
# Comandos del historial
# --------------------------------------------------------------------------
def show_history(repo, user_id: str) -> None:
    rows = repo.list(user_id)
    if not rows:
        print("  (sin investigaciones guardadas)")
        return
    for row in rows:
        fecha = row["created_at"].astimezone().strftime("%Y-%m-%d %H:%M")
        print(f"  #{row['id']:<4} {fecha}  [{row.get('language', 'en')}]  {row['topic']}")


def handle_command(command: str, repo, user_id: str) -> None:
    """Ejecuta los comandos /historial, /ver y /exportar."""
    if command == "/historial":
        show_history(repo, user_id)
        return

    report_id = parse_report_id(command)
    if report_id is None:
        return
    row = repo.get(user_id, report_id)
    if not row:
        print(f"  No existe el reporte #{report_id} en tu historial.")
        return

    if command.startswith("/ver"):
        console.print(Markdown(row["final_report"]))
    else:
        path = export_report(row["topic"], row["final_report"])
        print(f"  [reporte exportado a {path}]")


# --------------------------------------------------------------------------
# Bucle principal
# --------------------------------------------------------------------------
def research_loop(graph, repo, user_id: str, debug: bool) -> None:
    """Atiende temas de investigación hasta que el usuario decide salir."""
    from assistant.guard import check_topic

    while True:
        try:
            user_input = input("\nTema de investigación: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n¡Hasta luego!")
            break

        if not user_input:
            continue

        command = user_input.lower()
        if command in EXIT_WORDS:
            print("¡Hasta luego!")
            break
        if command == "/ayuda":
            print(HELP_TEXT)
            continue
        if command == "/debug":
            debug = not debug
            logging.getLogger("research_assistant").setLevel(logging.DEBUG if debug else logging.WARNING)
            print(f"  [modo debug: {'activado' if debug else 'desactivado'}]")
            continue
        if command == "/historial" or command.startswith(("/ver", "/exportar")):
            try:
                handle_command(command, repo, user_id)
            except Exception as e:
                print(f"  [error] {type(e).__name__}: {e}")
            continue
        if command.startswith("/"):
            print("  Comando no reconocido. Escribe /ayuda para ver los comandos.")
            continue

        # Cualquier error en una investigación se muestra pero no detiene el programa
        try:
            # 1) Filtro de alcance: solo se aceptan temas de investigación
            decision = check_topic(user_input)
            if not decision.is_valid:
                print(f"\n  [no permitido] {decision.message}")
                continue

            # 2) Investigación completa, en el idioma en que se escribió el tema
            language = decision.language
            print(f"  [idioma del reporte: {'español' if language == 'es' else 'inglés'}]")
            max_analysts = ask_int("Número de analistas (1-5) [3]: ", 1, 5, 3)
            result = run_research(graph, user_input, max_analysts, language, debug)
            if not result or not result["final_report"]:
                continue

            # 3) Mostrar, guardar en el historial y ofrecer exportar
            print()
            console.print(Markdown(result["final_report"]))
            report_id = repo.save(
                user_id, user_input, max_analysts, language,
                result["analysts"], result["feedback"], result["final_report"],
            )
            print(f"\n  [reporte guardado en tu historial como #{report_id}]")

            if input("¿Exportar el reporte a un archivo .md? (s/N): ").strip().lower() in {"s", "si", "sí", "y"}:
                path = export_report(user_input, result["final_report"])
                print(f"  [reporte exportado a {path}]")
        except KeyboardInterrupt:
            print("\n  [investigación cancelada]")
        except Exception as e:
            print(f"\n  [error] {type(e).__name__}: {e}")
            if debug:
                import traceback
                traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="Research Assistant: reportes de investigación con analistas IA")
    parser.add_argument("--user", help="ID del usuario (para su historial)")
    parser.add_argument("--debug", action="store_true", help="Muestra cada nodo del grafo y detalle de errores")
    args = parser.parse_args()

    # Avisos de búsquedas fallidas; en debug también las consultas generadas
    logging.basicConfig(format="  [%(levelname)s] %(message)s")
    logging.getLogger("research_assistant").setLevel(logging.DEBUG if args.debug else logging.WARNING)

    # Las claves deben cargarse ANTES de construir el grafo
    setup_environment()
    from assistant.graph import build_research_graph
    from assistant.storage import open_repository

    try:
        # El `with` garantiza que la conexión a Supabase se cierre al salir
        with open_repository() as repo:
            graph = build_research_graph()
            user_id = normalize_user_id(args.user or input("¿Cuál es tu nombre de usuario? "))

            previous = repo.list(user_id, limit=1)
            if previous:
                print(f"\n=== Bienvenido de nuevo, {user_id}. Escribe /historial para ver tus investigaciones ===")
            else:
                print(f"\n=== Research Assistant listo (usuario: {user_id}) ===")
            print(HELP_TEXT)

            research_loop(graph, repo, user_id, args.debug)
    except ConnectionError as e:
        print(f"\n[error] {e}")
    except KeyboardInterrupt:
        print("\n¡Hasta luego!")


if __name__ == "__main__":
    main()
