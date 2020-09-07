from webservice import db
from webservice.dbModels import Ontology, Version
from utils import stringTools, queryDatabus, ontoFiles, archivoConfig
from datetime import datetime
import csv


ontoIndex = ontoFiles.loadIndexJsonFromFile(archivoConfig.ontoIndexPath)

def updateDatabase():
    urisInDatabase = db.session.query(Ontology.uri).all()
    urisInDatabase = [t[0] for t in urisInDatabase]
    for uri in ontoIndex:
        if uri in urisInDatabase:
            print(f"Already listed: {uri}")
            continue
        print("Handling URI "+ uri)
        ontology, versions = generateEntryForUri(uri)
        db.session.add(ontology)
        for v in versions:
            db.session.add(v)
        try:
            db.session.commit()
        except IntegrityError as e:
            print(str(e))
            db.session.rollback() 
        print(len(Ontology.query.all()))



def generateEntryForUri(uri, source=None, accessDate=None):
    group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
    title, comment, versions_info = queryDatabus.getInfoForArtifact(group, artifact)
    versions = []
    source = source if source != None else ontoIndex[uri]["source"]
    accessDate = datetime.strptime(accessDate, "%Y-%m-%d %H:%M:%S") if accessDate != None else datetime.strptime(ontoIndex[uri]["accessed"], "%Y-%m-%d %H:%M:%S")

    ontology = Ontology(
            uri=uri,
            title=title,
            source=source,
            accessDate=accessDate,
        )
    db.session.add(ontology)
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

def writeIndexAsCSV(filepath):
    with open(filepath, "w+") as csvIndex:
        writer = csv.writer(csvIndex)
        for uri, source, accessDate in db.session.query(Ontology.uri, Ontology.source, Ontology.accessDate):
            writer.writerow((uri, source, accessDate.strftime("%Y-%m-%d %H:%M:%S")))

def updateInfoForOntology(uri):
    urisInDatabase = db.session.query(dbModels.Ontology.uri).all()
    urisInDatabase = [t[0] for t in urisInDatabase]
    group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
    title, comment, versions_info = queryDatabus.getInfoForArtifact(group, artifact)
    if not uri in urisInDatabase:
        webservice_logger.error("Not in database")
        return
    else:
        ontology = db.session.query(dbModels.Ontology).filter_by(uri=uri).first()
    for info_dict in versions_info:
        db.session.add(dbModels.Version(
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