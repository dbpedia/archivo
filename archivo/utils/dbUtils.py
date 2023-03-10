from archivo.webservice import db
from archivo.webservice.dbModels import OfficialOntology, DevelopOntology, Version
from archivo.utils import stringTools, queryDatabus, ontoFiles
from datetime import datetime
import csv
from archivo.crawling.discovery import ArchivoVersion


def buildDatabaseObjectFromDatabus(uri, source, timestamp, dev=""):
    group, artifact = stringTools.generate_databus_identifier_from_uri(
        uri, dev=True if dev != "" else False
    )
    title, comment, versions_info = queryDatabus.getInfoForArtifact(group, artifact)
    if title is None:
        return None, None
    if type(timestamp) != datetime and type(timestamp) == str:
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
    # urisInDatabase = [ont.uri for ont in db.session.query(OfficialOntology).all()]
    oldIndex = queryDatabus.get_last_official_index()
    print(f"Loaded last index. Found {len(oldIndex)} ontology URIs.")

    for i, tp in enumerate(oldIndex):
        uri, source, date = tp
        try:
            # if uri in urisInDatabase:
            # print(f"Already listed: {uri}")
            # continue
            if source == "DEV":
                continue
            try:
                timestamp = datetime.strptime(date, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                timestamp = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
            # print("Handling URI " + uri)
            group, artifact = stringTools.generate_databus_identifier_from_uri(uri)
            ontology, versions = buildDatabaseObjectFromDatabus(uri, source, timestamp)
            db.session.add(ontology)
            for v in versions:
                db.session.add(v)
            try:
                db.session.commit()
            except Exception as e:
                print(str(e))
                db.session.rollback()
            # print(len(Ontology.query.all()))
        except Exception as e:
            print(f"Error in handling {uri}", e)
            continue

    # rebuild dev data
    dev_index = queryDatabus.get_last_dev_index()
    print(f"Rebuilding dev data. Found {len(dev_index)} DEV URIs.")
    for dev_uri, source, date, official_uri in dev_index:
        try:
            try:
                timestamp = datetime.strptime(date, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                timestamp = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")

            group, artifact = stringTools.generate_databus_identifier_from_uri(
                official_uri, dev=True
            )
            ontology, versions = buildDatabaseObjectFromDatabus(
                official_uri, source, timestamp, dev=dev_uri
            )
            db.session.add(ontology)
            for v in versions:
                db.session.add(v)
            try:
                db.session.commit()
            except Exception as e:
                print(str(e))
                db.session.rollback()
        except Exception as e:
            print(f"Error in handling {dev_uri}", e)
            continue


def update_database():

    all_onts = db.session.query(OfficialOntology).all()
    listed_uris = [ont.uri for ont in all_onts]
    print(f"Current index size: {len(all_onts)}")
    oldIndex = queryDatabus.get_last_official_index()
    print(f"Loaded last index. Found {len(oldIndex)} ontology URIs.")

    missing_ontologies = [
        (uri, source, date)
        for (uri, source, date) in oldIndex
        if uri not in listed_uris
    ]
    print(f"Found {len(missing_ontologies)} missing ontologies, trying to update")

    for i, tp in enumerate(missing_ontologies):

        uri, source, date = tp
        try:
            # if uri in urisInDatabase:
            # print(f"Already listed: {uri}")
            # continue
            if source == "DEV":
                continue
            try:
                timestamp = datetime.strptime(date, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                timestamp = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
            # print("Handling URI " + uri)
            group, artifact = stringTools.generate_databus_identifier_from_uri(uri)
            ontology, versions = buildDatabaseObjectFromDatabus(uri, source, timestamp)
            db.session.add(ontology)
            for v in versions:
                db.session.add(v)
            try:
                db.session.commit()
            except Exception as e:
                print(str(e))
                db.session.rollback()
            # print(len(Ontology.query.all()))
        except Exception as e:
            print(f"Error in handling {uri}", e)
            continue


def write_official_index(filepath):
    with open(filepath, "w+") as csvIndex:
        writer = csv.writer(csvIndex)
        for uri, source, accessDate in db.session.query(
            OfficialOntology.uri, OfficialOntology.source, OfficialOntology.accessDate
        ):
            writer.writerow((uri, source, accessDate.strftime("%Y-%m-%d %H:%M:%S")))


def write_dev_index(filepath):
    with open(filepath, "w+") as csvIndex:
        writer = csv.writer(csvIndex)
        for uri, source, accessDate, official in db.session.query(
            DevelopOntology.uri,
            DevelopOntology.source,
            DevelopOntology.accessDate,
            DevelopOntology.official,
        ):
            writer.writerow(
                (uri, source, accessDate.strftime("%Y-%m-%d %H:%M:%S"), official)
            )


def update_info_for_ontology(ontology: OfficialOntology):

    group, artifact = stringTools.generate_databus_identifier_from_uri(ontology.uri)
    _, versions = buildDatabaseObjectFromDatabus(
        ontology.uri, ontology.source, ontology.accessDate
    )
    for v in [
        vers
        for vers in versions
        if vers.versionID
        not in [available_v.versionID for available_v in ontology.versions]
    ]:
        db.session.add(v)
        try:
            db.session.commit()
            print("Adds version for", ontology.uri, ":", v)
        except Exception as e:
            print(f"Problem handling update for {ontology.uri}: {str(e)}")

    if ontology.devel is not None:
        dev_ont = ontology.devel
        group, artifact = stringTools.generate_databus_identifier_from_uri(
            ontology.uri, dev=True
        )
        _, versions = buildDatabaseObjectFromDatabus(
            ontology.uri,
            dev_ont.source,
            dev_ont.accessDate,
            dev=dev_ont.uri,
        )
        for v in [
            vers
            for vers in versions
            if vers.versionID
            not in [available_v.versionID for available_v in dev_ont.versions]
        ]:
            print("Adds DEV version for", dev_ont.uri, ":", v)
            db.session.add(v)
            try:
                db.session.commit()
            except Exception as e:
                print(f"Problem handling update for {dev_ont.uri}: {str(e)}")
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
        parsing=True
        if archivo_version.rapper_errors == "" or archivo_version.rapper_errors == []
        else False,
        licenseI=archivo_version.conforms_licenseI,
        licenseII=archivo_version.conforms_licenseII,
        consistency=consistencyCheck(archivo_version.is_consistent),
        lodeSeverity=archivo_version.lode_severity,
        ontology=archivo_version.reference_uri,
    )
    return dbOntology, dbVersion
