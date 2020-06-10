from flask import Flask

app = Flask(__name__)
app.config['SECRET_KEY'] = 'you-will-never-guess'

localPath = "/home/denis/Workspace/Job/Archivo/testdir"

from webservice import routes