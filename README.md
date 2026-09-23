# Research Assistant

Asistente de investigación en terminal construido con LangGraph.
Para un tema, crea un equipo de analistas IA. Tú revisas y ajustas ese equipo.
Cada analista entrevista a un "experto" que responde con información de la web (Tavily) y Wikipedia.
Al final se genera un reporte en Markdown con introducción, hallazgos, conclusión y fuentes.

El reporte sale en el idioma del tema, español o inglés. El asistente solo acepta temas de investigación: rechaza peticiones de código, traducciones, conversación y otros usos.

## Demo

![Demo del Research Assistant](demo/demo.gif)

Sesión real con el tema *Impacto de la inteligencia artificial en la educación en México* y 2 analistas. Las esperas largas se recortaron y se aceleró la reproducción. La grabación original está en [`demo/demo.cast`](demo/demo.cast) y se reproduce con `asciinema play demo/demo.cast`.

## Instalación

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # y coloca tus claves
```

Necesitas una clave de [OpenAI](https://platform.openai.com) y una de [Tavily](https://tavily.com) (tiene plan gratuito).

## Uso

```bash
python main.py
python main.py --user jesus --debug
```

1. Escribe un tema, por ejemplo `Impacto de la inteligencia artificial en la educación en México`.
2. Elige cuántos analistas quieres, de 1 a 5.
3. Revisa a los analistas. Escribe un ajuste, por ejemplo `agrega a un docente de escuela pública`, o pulsa Enter para aprobarlos.
4. Espera el reporte. Se guarda en tu historial y puedes exportarlo a `reports/`.

Comandos: `/historial`, `/ver <id>`, `/exportar <id>`, `/debug`, `/ayuda` y `salir`.

## Historial persistente con Supabase (opcional)

Sin configuración, el historial vive en RAM y se borra al salir. Para conservarlo:

1. Crea un proyecto gratuito en [supabase.com](https://supabase.com).
2. Pulsa **Connect** y copia la cadena de conexión de **Session pooler**.
3. Pégala en tu `.env` como `SUPABASE_DB_URL`, reemplazando `[YOUR-PASSWORD]` por la contraseña de la base de datos.

La primera vez se crea la tabla `research_reports` automáticamente, con Row Level Security activado.

## Estructura

```
main.py                 # bucle interactivo en terminal
assistant/config.py     # variables de entorno, modelo y buscador web
assistant/schemas.py    # analistas, consultas y estados de los grafos
assistant/prompts.py    # prompts de investigación y del filtro de alcance
assistant/guard.py      # filtro que valida temas y ajustes
assistant/analysts.py   # creación de analistas y revisión humana
assistant/interview.py  # subgrafo de entrevista con búsqueda web y Wikipedia
assistant/report.py     # redacción del reporte final
assistant/graph.py      # construcción de los grafos
assistant/storage.py    # historial: Supabase o RAM
```

## Notas

- Wikipedia limita las peticiones de clientes anónimos. Si bloquea, el asistente la omite dos minutos y sigue con la búsqueda web.
- El usuario solo es un nombre, sin contraseña: quien use el mismo nombre en la misma base de datos verá el mismo historial.
- El reporte se genera en el idioma en que escribes el tema: español o inglés.
