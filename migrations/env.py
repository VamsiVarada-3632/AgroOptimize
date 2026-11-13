import os, sys
from pathlib import Path
from alembic import context
from sqlalchemy import create_engine
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.schema import metadata  # noqa: E402
from app.db.session import db_url  # noqa: E402

def run():
    url = context.config.get_main_option("sqlalchemy.url") or db_url()
    eng = create_engine(url)
    with eng.connect() as cx:
        context.configure(connection=cx, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
run()
