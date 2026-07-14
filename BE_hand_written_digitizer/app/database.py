import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = (
    f"mysql+pymysql://"
    f"{os.getenv('DB_USER')}:"
    f"{os.getenv('DB_PASSWORD')}@"
    f"{os.getenv('DB_HOST')}:"
    f"{os.getenv('DB_PORT')}/"
    f"{os.getenv('DB_NAME')}"
)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def ensure_history_summary_column() -> None:
    """Apply the small idempotent schema migration used by this project."""
    inspector = inspect(engine)
    if "history" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("history")}
    if "summary" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE history ADD COLUMN summary LONGTEXT NULL"))
