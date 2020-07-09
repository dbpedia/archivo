from flask import Flask

app = Flask(__name__)
app.config['SECRET_KEY'] = b'7\x1f\xfb\xe7\xc1\x7f\xf1\xcd\xd6G\xfa\t\xdd\x0b\xd5\xcd'

from webservice import routes
