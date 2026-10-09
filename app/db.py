from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def garantir_colunas() -> None:
    """Migração mínima: adiciona colunas novas em bancos já criados (create_all não altera tabelas existentes)."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.begin() as con:
        for tabela in Base.metadata.sorted_tables:
            if not insp.has_table(tabela.name):
                continue
            existentes = {c["name"] for c in insp.get_columns(tabela.name)}
            for col in tabela.columns:
                if col.name in existentes:
                    continue
                tipo = col.type.compile(engine.dialect)
                padrao = ""
                if col.default is not None and getattr(col.default, "is_scalar", False):
                    v = col.default.arg
                    padrao = f" DEFAULT {int(v) if isinstance(v, bool) else repr(v)}"
                con.execute(text(f'ALTER TABLE {tabela.name} ADD COLUMN {col.name} {tipo}{padrao}'))
