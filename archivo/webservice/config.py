import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config(object):
    # ...
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL"
    ) or "sqlite:///" + os.path.join(basedir, "archivo.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = b"uhhh mystery..."
    VOCAB_FOLDER = os.path.join(basedir, "static", "vocabulary")
