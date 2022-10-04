from sqlalchemy import create_engine
import os

basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


DB_URI = os.environ.get(
        "DATABASE_URL"
    ) or "sqlite:///" + os.path.join(basedir, "archivo.db")

db_engine = create_engine(DB_URI)

