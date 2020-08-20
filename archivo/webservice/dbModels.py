from webservice import db

class Ontology(db.Model):
    uri = db.Column(db.String(120), primary_key=True)
    source = db.Column(db.String(64), index=True, unique=False)
    accessDate = db.Column(db.String(64))
    versions = db.relationship('Version', backref='author', lazy='dynamic')
    latestVersion = db.Column(db.String(120), index=True, unique=False)
    latestSemanticVersion = db.Column(db.String(64))
    stars = db.Column(db.Integer)
    parsing = db.Column(db.Boolean)
    licenseI = db.Column(db.Boolean)
    licenseII = db.Column(db.Boolean)
    consistency = db.Column(db.Boolean)
    lodeMetadataLevel = db.Column(db.String(32))
    crawlingStatus = db.Column(db.Boolean)
    crawlingError = db.Column(db.String(120))

    def __repr__(self):
        return '<Ontology {}>'.format(self.uri)


class Fallout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    

class Version(db.Model):
    id = db.Column(db.Integer, primary_key=True)