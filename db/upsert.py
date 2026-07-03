from sqlalchemy.dialects.postgresql import insert as _pg_insert
from sqlalchemy.dialects.sqlite import insert as _sqlite_insert

from db.base import engine

_insert_fn = _pg_insert if engine.dialect.name == "postgresql" else _sqlite_insert


def upsert(model):
    """Dialektga mos (PostgreSQL/SQLite) `INSERT ... ON CONFLICT` statement quruvchisi.
    Qaytgan obyektda `.on_conflict_do_update(index_elements=[...], set_={...})` chaqiring."""
    return _insert_fn(model)
