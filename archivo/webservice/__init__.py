from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from webservice.config import Config

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)

# from webservice import routes, dbModels
