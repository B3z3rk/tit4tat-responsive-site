from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = Path(__file__).resolve().parent.parent / "tit4tat.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Base.metadata.create_all() only creates tables that don't exist yet - it
# never adds a new column to a table that's already there. For a table this
# small that's normally handled by deleting tit4tat.db and letting seed_if_empty
# reseed from scratch, but that would also wipe out real data (sessions,
# reports, MFA enrollments, etc.) that's since accumulated. This adds any
# columns added to models.py after the table already existed, in place,
# without touching existing rows.
_NEW_COLUMNS = [
    ("users", "mfa_required", "BOOLEAN DEFAULT 0"),
]


def run_lightweight_migrations() -> None:
    with engine.connect() as conn:
        for table, column, ddl_type in _NEW_COLUMNS:
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
                conn.commit()
