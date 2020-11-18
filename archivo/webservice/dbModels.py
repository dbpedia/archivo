from webservice import db
from datetime import datetime


class Ontology(db.Model):
    __tablename__ = "ontology"
    uri = db.Column(db.String(120), primary_key=True)
    title = db.Column(db.String(300))
    source = db.Column(db.String(64))
    accessDate = db.Column(db.DateTime)
    versions = db.relationship("Version", backref="vocab", lazy="dynamic")
    crawlingFallout = db.relationship(
        "Fallout", backref="crawlingFallout", lazy="dynamic"
    )
    crawling_status = db.Column(db.Boolean)
    type = db.Column("type", db.String(50))  # discriminator
    __mapper_args__ = {"polymorphic_on": type}

    def __repr__(self):
        return "<Ontology {}>".format(self.uri)


class Version(db.Model):
    __tablename__ = "version"
    _id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.DateTime, index=True)
    semanticVersion = db.Column(db.String(64))
    triples = db.Column(db.Integer)
    stars = db.Column(db.Integer)
    parsing = db.Column(db.Boolean)
    licenseI = db.Column(db.Boolean)
    licenseII = db.Column(db.Boolean)
    consistency = db.Column(db.Boolean)
    lodeSeverity = db.Column(db.String(32))
    ontology = db.Column(db.String(120), db.ForeignKey("ontology.uri"))

    def __repr__(self):
        return "<Version {}>".format(self.version)


class OfficialOntology(Ontology):
    __tablename__ = "officialOntology"
    uri = db.Column(db.String(120), db.ForeignKey("ontology.uri"), primary_key=True)
    __mapper_args__ = {
        "polymorphic_identity": "officialOntology",
        "inherit_condition": (uri == Ontology.uri),
    }
    devel = db.relationship(
        "DevelopOntology",
        primaryjoin="(OfficialOntology.uri==DevelopOntology.official)",
        uselist=False,
        backref=db.backref("original"),
    )


class DevelopOntology(Ontology):
    __tablename__ = "developOntology"
    uri = db.Column(db.String(120), db.ForeignKey("ontology.uri"), primary_key=True)
    __mapper_args__ = {
        "polymorphic_identity": "developOntology",
        "inherit_condition": (uri == Ontology.uri),
    }
    official = db.Column(db.String(120), db.ForeignKey("officialOntology.uri"))


class Fallout(db.Model):
    _id = db.Column(db.Integer, primary_key=True)
    uri = db.Column(db.String(120), index=True)
    source = db.Column(db.String(64), index=True)
    date = db.Column(db.DateTime, index=True, default=datetime.now)
    inArchivo = db.Column(db.Boolean, index=True)
    error = db.Column(db.String(250))
    ontology = db.Column(db.String(120), db.ForeignKey("ontology.uri"))


class LatestOntologyMetadata(db.Model):
    uri = db.Column(db.String(120), primary_key=True)
    source = db.Column(db.String(64))
    accessDate = db.Column(db.DateTime)
    version = db.Column(db.DateTime, index=True)
    semanticVersion = db.Column(db.String(64))
    stars = db.Column(db.Integer)
    parsing = db.Column(db.Boolean)
    licenseI = db.Column(db.Boolean)
    licenseII = db.Column(db.Boolean)
    consistency = db.Column(db.Boolean)
    lodeSeverity = db.Column(db.String(32))
    ontology = db.Column(db.String(120), db.ForeignKey("ontology.uri"))
    crawlingStatus = db.Column(db.Boolean)
    crawlingError = db.Column(db.String(120))

    def __repr__(self):
        return "<Ontology {}>".format(self.uri)
