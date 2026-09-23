"""
Historial de investigaciones.

- Si existe SUPABASE_DB_URL en el .env, cada reporte se guarda en Supabase
  (tabla public.research_reports) y se conserva entre sesiones.
- Si no existe, el historial vive en RAM y se pierde al salir.

La tabla se crea automáticamente la primera vez, con Row Level Security
activado para que no quede expuesta por la API web de Supabase.
"""
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

# SQL para crear la tabla (idempotente: se puede ejecutar siempre)
CREATE_TABLE_SQL = """
create table if not exists public.research_reports (
    id            bigserial primary key,
    user_id       text        not null,
    topic         text        not null,
    max_analysts  integer     not null,
    analysts      jsonb       not null default '[]'::jsonb,
    feedback      jsonb       not null default '[]'::jsonb,
    final_report  text        not null,
    created_at    timestamptz not null default now()
);
create index if not exists research_reports_user_idx
    on public.research_reports (user_id, created_at desc);
alter table public.research_reports add column if not exists language text not null default 'en';
alter table public.research_reports enable row level security;
"""


class MemoryReportRepository:
    """Historial en RAM (se usa cuando no hay Supabase configurado)."""

    persistent = False

    def __init__(self):
        self._rows: list[dict] = []

    def save(self, user_id, topic, max_analysts, language, analysts, feedback, final_report) -> int:
        row = {
            "id": len(self._rows) + 1,
            "user_id": user_id,
            "topic": topic,
            "max_analysts": max_analysts,
            "language": language,
            "analysts": analysts,
            "feedback": feedback,
            "final_report": final_report,
            "created_at": datetime.now(timezone.utc),
        }
        self._rows.append(row)
        return row["id"]

    def list(self, user_id, limit=20) -> list[dict]:
        rows = [r for r in self._rows if r["user_id"] == user_id]
        return sorted(rows, key=lambda r: r["created_at"], reverse=True)[:limit]

    def get(self, user_id, report_id) -> Optional[dict]:
        return next((r for r in self._rows if r["user_id"] == user_id and r["id"] == report_id), None)


class PostgresReportRepository:
    """Historial en Supabase (Postgres)."""

    persistent = True

    def __init__(self, pool):
        self.pool = pool

    def setup(self):
        with self.pool.connection() as conn:
            conn.execute(CREATE_TABLE_SQL)

    def save(self, user_id, topic, max_analysts, language, analysts, feedback, final_report) -> int:
        from psycopg.types.json import Jsonb
        with self.pool.connection() as conn:
            row = conn.execute(
                """insert into public.research_reports
                       (user_id, topic, max_analysts, language, analysts, feedback, final_report)
                   values (%s, %s, %s, %s, %s, %s, %s)
                   returning id""",
                (user_id, topic, max_analysts, language, Jsonb(analysts), Jsonb(feedback), final_report),
            ).fetchone()
        return row["id"]

    def list(self, user_id, limit=20) -> list[dict]:
        with self.pool.connection() as conn:
            return conn.execute(
                """select id, topic, max_analysts, language, created_at
                   from public.research_reports
                   where user_id = %s
                   order by created_at desc
                   limit %s""",
                (user_id, limit),
            ).fetchall()

    def get(self, user_id, report_id) -> Optional[dict]:
        # Se filtra también por user_id para que nadie vea reportes de otro usuario
        with self.pool.connection() as conn:
            return conn.execute(
                "select * from public.research_reports where user_id = %s and id = %s",
                (user_id, report_id),
            ).fetchone()


@contextmanager
def open_repository() -> Iterator[MemoryReportRepository | PostgresReportRepository]:
    """Abre el historial adecuado y cierra la conexión al terminar (usar con `with`)."""
    db_url = os.environ.get("SUPABASE_DB_URL")

    if not db_url:
        print("  [aviso] SUPABASE_DB_URL no está definida: el historial se guardará solo en RAM.")
        yield MemoryReportRepository()
        return

    # Imports aquí para que el modo RAM funcione aunque no estén instalados
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    # Prueba rápida de conexión: si la URL o la contraseña están mal, falla aquí
    try:
        psycopg.connect(db_url, connect_timeout=10).close()
    except Exception as e:
        raise ConnectionError(
            "No se pudo conectar a Supabase. Revisa SUPABASE_DB_URL en tu .env "
            f"(usuario, contraseña y host del pooler). Detalle: {e}"
        ) from e

    # Pool de conexiones:
    # - prepare_threshold=None: compatible con el pooler de Supabase (session y transaction)
    # - check: valida la conexión antes de usarla (Supabase cierra conexiones inactivas)
    pool = ConnectionPool(
        db_url,
        min_size=1,
        max_size=3,
        kwargs={"autocommit": True, "prepare_threshold": None, "row_factory": dict_row},
        check=ConnectionPool.check_connection,
        open=False,
    )
    pool.open(wait=True, timeout=15)

    try:
        repo = PostgresReportRepository(pool)
        repo.setup()
        print("  [ok] Conectado a Supabase: tu historial de investigaciones se conserva.")
        yield repo
    finally:
        pool.close()
