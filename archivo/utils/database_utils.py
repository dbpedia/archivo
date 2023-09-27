from io import StringIO
from typing import Tuple, List, Optional

from webservice import db
from webservice.dbModels import (
    OfficialOntology,
    DevelopOntology,
    Version,
    Ontology,
)
from utils import string_tools, validation
from querying import query_databus
from datetime import datetime
import csv
from crawling.discovery import ArchivoVersion


def db_objects_from_databus(
    uri: str, source: str, timestamp, dev=""
) -> Tuple[Optional[Ontology], Optional[List[Version]]]:
    """Builds the database objects for a certain ontology by uri"""

    group, artifact = string_tools.generate_databus_identifier_from_uri(
        uri, dev=True if dev != "" else False
    )
    artifact_info = query_databus.get_info_for_artifact(group, artifact)
    if artifact_info is None:
        return None, None
    if type(timestamp) != datetime and type(timestamp) == str:
        timestamp = datetime.strptime(timestamp, "%Y.%m.%d-%H%M%S")
    if dev != "":
        ontology = DevelopOntology(
            uri=dev,
            title=artifact_info.title,
            source=source,
            accessDate=timestamp,
            official=uri,
        )
    else:
        ontology = OfficialOntology(
            uri=uri,
            title=artifact_info.title,
            source=source,
            accessDate=timestamp,
        )
    versions = []
    for version_info in artifact_info.version_infos:
        versions.append(Version.build_from_version_info(ontology.uri, version_info))
    return ontology, versions


def rebuild_database():
    db.create_all()
    # urisInDatabase = [ont.uri for ont in db.session.query(OfficialOntology).all()]
    oldIndex = query_databus.get_last_official_index()
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
            group, artifact = string_tools.generate_databus_identifier_from_uri(uri)
            ontology, versions = db_objects_from_databus(uri, source, timestamp)
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
    dev_index = query_databus.get_last_dev_index()
    print(f"Rebuilding dev data. Found {len(dev_index)} DEV URIs.")
    for dev_uri, source, date, official_uri in dev_index:
        try:
            try:
                timestamp = datetime.strptime(date, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                timestamp = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")

            ontology, versions = db_objects_from_databus(
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


def safely_remove_ontology_from_db(ontology_uri: str) -> None:

    db_ont = db.session.query(Ontology).filter_by(uri=ontology_uri).first()

    db_versions = db_ont.versions.all()

    print(f"Found database object: {db_ont.uri} with {len(db_versions)} Versions")

    for v in db_versions:
        db.session.delete(v)

    db.session.delete(db_ont)

    try:
        db.session.commit()
    except Exception as e:
        print(str(e))
        db.session.rollback()
    new_result = db.session.query(Ontology).filter_by(uri=ontology_uri).first()
    if new_result is None:
        print(f"Database object safely deletet!")
    else:
        print(
            f"There was an error, there is still something in the database: {new_result}"
        )


def update_database():

    all_onts = db.session.query(OfficialOntology).all()
    listed_uris = [ont.uri for ont in all_onts]
    print(f"Current index size: {len(all_onts)}")
    oldIndex = query_databus.get_last_official_index()
    print(f"Loaded last index. Found {len(oldIndex)} ontology URIs.")

    missing_ontologies = [
        (uri, source, date)
        for (uri, source, date) in oldIndex
        if uri not in listed_uris
    ]
    print(f"Found {len(missing_ontologies)} missing ontologies, trying to update")

    for i, tp in enumerate(missing_ontologies):

        uri, source, date = tp
        print(f"Handling ontology: {uri}")
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
            ontology, versions = db_objects_from_databus(uri, source, timestamp)
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


def get_official_index_as_csv() -> str:

    output = StringIO()
    writer = csv.writer(output)
    for uri, source, accessDate in db.session.query(
        OfficialOntology.uri, OfficialOntology.source, OfficialOntology.accessDate
    ):
        writer.writerow((uri, source, accessDate.strftime("%Y-%m-%d %H:%M:%S")))

    return str(output)


def get_dev_index_as_csv() -> str:

    output = StringIO()
    writer = csv.writer(output)
    for uri, source, accessDate, official in db.session.query(
        DevelopOntology.uri,
        DevelopOntology.source,
        DevelopOntology.accessDate,
        DevelopOntology.official,
    ):
        writer.writerow(
            (uri, source, accessDate.strftime("%Y-%m-%d %H:%M:%S"), official)
        )
    return str(output)


def update_info_for_ontology(ontology: OfficialOntology):

    _, versions = db_objects_from_databus(
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
        group, artifact = string_tools.generate_databus_identifier_from_uri(
            ontology.uri, dev=True
        )
        _, versions = db_objects_from_databus(
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


def get_database_entries(archivo_version: ArchivoVersion) -> Tuple[Ontology, Version]:
    if archivo_version.isDev:
        dbOntology = DevelopOntology(
            uri=archivo_version.reference_uri,
            source="DEV",
            accessDate=archivo_version.access_date,
            title=archivo_version.get_label(),
            official=archivo_version.nir,
        )
    else:
        dbOntology = OfficialOntology(
            uri=archivo_version.reference_uri,
            source=archivo_version.source,
            accessDate=archivo_version.access_date,
            title=archivo_version.get_label(),
            devel=None,
        )

    dbVersion = Version(
        version=archivo_version.access_date,
        semanticVersion=archivo_version.semantic_version,
        stars=archivo_version.metadata_dict["ontology-info"]["stars"],
        triples=archivo_version.parsing_result.parsing_info.triple_number,
        parsing=True
        if len(archivo_version.parsing_result.parsing_info.errors) == 0
        else False,
        licenseI=archivo_version.metadata_dict["test-results"]["License-I"],
        licenseII=archivo_version.metadata_dict["test-results"]["License-II"],
        consistency=validation.check_if_consistent(
            archivo_version.metadata_dict["test-results"]["consistent"],
            archivo_version.metadata_dict["test-results"]["consistent-without-imports"],
        ),
        lodeSeverity=archivo_version.metadata_dict["test-results"]["lode-conform"],
        ontology=archivo_version.reference_uri,
    )
    return dbOntology, dbVersion
