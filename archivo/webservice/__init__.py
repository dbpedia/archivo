from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from webservice.config import Config

app = Flask(__name__)
app.config['SECRET_KEY'] = b'7\x1f\xfb\xe7\xc1\x7f\xf1\xcd\xd6G\xfa\t\xdd\x0b\xd5\xcd'
app.config.from_object(Config)
db = SQLAlchemy(app)



from webservice import routes, dbModels