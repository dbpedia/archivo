import os
basedir = os.path.abspath(os.path.dirname(__file__))

class Config(object):
    # ...
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'archivo.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = b'\xb2\xd8\xa58\x02\xf1\x92\xcdX\x7f\xd6w\x906\xb1\x94'


