from webservice import db
from webservice.dbModels import OfficialOntology, DevelopOntology, Version, Ontology
from utils import stringTools, queryDatabus, ontoFiles, archivoConfig
from datetime import datetime
import csv
from crawlURIs import ArchivoVersion


def buildDatabaseObjectFromDatabus(uri, group, artifact, source, timestamp, dev=""):
    title, comment, versions_info = queryDatabus.getInfoForArtifact(group, artifact)
    if title == None:
        return None, None
    if type(timestamp) != datetime.datetime and type(timestamp) == str:
        timestamp = datetime.strptime(timestamp, "%Y.%m.%d-%H%M%S")
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
        versions.append(
            Version(
                version=datetime.strptime(
                    info_dict["version"]["label"], "%Y.%m.%d-%H%M%S"
                ),
                semanticVersion=info_dict["semversion"],
                stars=info_dict["stars"],
                triples=info_dict["triples"],
                parsing=info_dict["parsing"]["conforms"],
                licenseI=info_dict["minLicense"]["conforms"],
                licenseII=info_dict["goodLicense"]["conforms"],
                consistency=info_dict["consistent"]["conforms"],
                lodeSeverity=str(info_dict["lode"]["severity"]),
                ontology=ontology.uri,
            )
        )
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
            timestamp = datetime.strptime(date, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            timestamp = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        print("Handling URI " + uri)
        group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
        ontology, versions = buildDatabaseObjectFromDatabus(
            uri, group, artifact, source, timestamp
        )
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
        for uri, source, accessDate in db.session.query(
            Ontology.uri, Ontology.source, Ontology.accessDate
        ):
            writer.writerow((uri, source, accessDate.strftime("%Y-%m-%d %H:%M:%S")))


def updateInfoForOntology(uri, orig_uri=None):
    urisInDatabase = db.session.query(Ontology.uri).all()
    urisInDatabase = [t[0] for t in urisInDatabase]
    if orig_uri == None:
        group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
    else:
        group, artifact = stringTools.generateGroupAndArtifactFromUri(
            orig_uri, dev=True
        )
    title, comment, versions_info = queryDatabus.getInfoForArtifact(group, artifact)
    if not uri in urisInDatabase:
        webservice_logger.error("Not in database")
        return
    else:
        ontology = db.session.query(Ontology).filter_by(uri=uri).first()
    for info_dict in versions_info:
        db.session.add(
            Version(
                version=datetime.strptime(
                    info_dict["version"]["label"], "%Y.%m.%d-%H%M%S"
                ),
                semanticVersion=info_dict["semversion"],
                stars=info_dict["stars"],
                triples=info_dict["triples"],
                parsing=info_dict["parsing"]["conforms"],
                licenseI=info_dict["minLicense"]["conforms"],
                licenseII=info_dict["goodLicense"]["conforms"],
                consistency=info_dict["consistent"]["conforms"],
                lodeSeverity=str(info_dict["lode"]["severity"]),
                ontology=ontology.uri,
            )
        )
    try:
        db.session.commit()
    except IntegrityError as e:
        print(str(e))
        db.session.rollback()


def getDatabaseEntry(archivo_version: ArchivoVersion):
    if archivo_version.isDev:
        dbOntology = DevelopOntology(
            uri=archivo_version.reference_uri,
            source="DEV",
            accessDate=archivo_version.access_date,
            title=archivo_version.md_label,
            official=archivo_version.nir,
        )
    else:
        dbOntology = OfficialOntology(
            uri=archivo_version.reference_uri,
            source=archivo_version.source,
            accessDate=archivo_version.access_date,
            title=archivo_version.md_label,
            devel=None,
        )
    consistencyCheck = lambda s: True if s == "Yes" else False
    dbVersion = Version(
        version=datetime.strptime(archivo_version.version, "%Y.%m.%d-%H%M%S"),
        semanticVersion=archivo_version.semantic_version,
        stars=ontoFiles.measureStars(
            archivo_version.rapper_errors,
            archivo_version.conforms_licenseI,
            archivo_version.is_consistent,
            archivo_version.is_consistent_noimports,
            archivo_version.conforms_licenseII,
        ),
        triples=archivo_version.triples,
        parsing=True if archivo_version.rapper_errors == "" else False,
        licenseI=archivo_version.conforms_licenseI,
        licenseII=archivo_version.conforms_licenseII,
        consistency=consistencyCheck(archivo_version.is_consistent),
        lodeSeverity=archivo_version.lode_severity,
        ontology=archivo_version.reference_uri,
    )
    return dbOntology, dbVersion
