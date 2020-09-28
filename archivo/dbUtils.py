from webservice import db
from webservice.dbModels import OfficialOntology, DevelopOntology, Version, Ontology
from utils import stringTools, queryDatabus, ontoFiles, archivoConfig
from datetime import datetime
import csv


def buildDatabaseObjectFromDatabus(uri, group, artifact, source, timestamp, dev=""):
    title, comment, versions_info = queryDatabus.getInfoForArtifact(group, artifact)
    if title == None:
        return None, None
    if dev != "":
        ontology = DevelopOntology(
        uri=dev,
        title=title,
        source=source,
        accessDate=timestamp,
        official=uri,
        )
    else:
        ontology = OfficialOntology(
        uri=uri,
        title=title,
        source=source,
        accessDate=timestamp,
        )
    
    versions = []
    for info_dict in versions_info:
        versions.append(Version(
                version=datetime.strptime(info_dict["version"]["label"], "%Y.%m.%d-%H%M%S"),
                semanticVersion=info_dict["semversion"],
                stars=info_dict["stars"],
                triples=info_dict["triples"],
                parsing=info_dict["parsing"]["conforms"],
                licenseI=info_dict["minLicense"]["conforms"],
                licenseII=info_dict["goodLicense"]["conforms"],
                consistency=info_dict["consistent"]["conforms"],
                lodeSeverity=str(info_dict["lode"]["severity"]),
                ontology=ontology.uri,
        ))
    return ontology, versions


def rebuildDatabase():
    db.create_all()
    urisInDatabase = [ont.uri for ont in db.session.query(dbModels.Ontology).all()]
    oldIndex = queryDatabus.loadLastIndex()
    for uri, source, date in oldIndex:
        if uri in urisInDatabase:
            print(f"Already listed: {uri}")
            continue
        try:
            timestamp = datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            timestamp = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
        print("Handling URI "+ uri)
        group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
        ontology, versions = buildDatabaseObjectFromDatabus(uri, group, artifact, source, timestamp)
        db.session.add(ontology)
        for v in versions:
            db.session.add(v)
        try:
            db.session.commit()
        except IntegrityError as e:
            print(str(e))
            db.session.rollback() 
        print(len(Ontology.query.all()))

def writeIndexAsCSV(filepath):
    with open(filepath, "w+") as csvIndex:
        writer = csv.writer(csvIndex)
        for uri, source, accessDate in db.session.query(Ontology.uri, Ontology.source, Ontology.accessDate):
            writer.writerow((uri, source, accessDate.strftime("%Y-%m-%d %H:%M:%S")))

def updateInfoForOntology(uri):
    urisInDatabase = db.session.query(OfficialOntology.uri).all()
    urisInDatabase = [t[0] for t in urisInDatabase]
    group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
    title, comment, versions_info = queryDatabus.getInfoForArtifact(group, artifact)
    if not uri in urisInDatabase:
        webservice_logger.error("Not in database")
        return
    else:
        ontology = db.session.query(OfficialOntology).filter_by(uri=uri).first()
    for info_dict in versions_info:
        db.session.add(Version(
                version=datetime.strptime(info_dict["version"]["label"], "%Y.%m.%d-%H%M%S"),
                semanticVersion=info_dict["semversion"],
                stars=info_dict["stars"],
                triples=info_dict["triples"],
                parsing=info_dict["parsing"]["conforms"],
                licenseI=info_dict["minLicense"]["conforms"],
                licenseII=info_dict["goodLicense"]["conforms"],
                consistency=info_dict["consistent"]["conforms"],
                lodeSeverity=str(info_dict["lode"]["severity"]),
                ontology=ontology.uri,
        ))
    try:
        db.session.commit()
    except IntegrityError as e:
        print(str(e))
        db.session.rollback() 