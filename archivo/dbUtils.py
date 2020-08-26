from webservice import db
from webservice.dbModels import Ontology, Version
from utils import stringTools, queryDatabus, ontoFiles, archivoConfig
from datetime import datetime


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