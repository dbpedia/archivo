import atexit
from typing import List, Iterable

import databusclient

import models.data_writer
from models.databus_identifier import (
    DatabusFileMetadata,
    DatabusVersionIdentifier,
)
from models.user_interaction import ProcessStepLog, check_is_nir_based_on_log
from utils import graphing
from update import update_archivo
import json
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from crawling import discovery, sources
from utils import archivo_config, string_tools, database_utils
from querying import query_databus
from utils.archivoLogs import (
    discovery_logger,
    diff_logger,
    dev_diff_logger,
)
from utils.validation import TestSuite
from webservice import app, db, dbModels

cron = BackgroundScheduler(daemon=True)
# Explicitly kick off the background thread
cron.start()


# Check whether the uri is in archivo uris or an archivo uri is a substring of it
# True returned when already contained, False otherwise
def check_uri_containment(uri: str, archivo_uris: List[str]) -> bool:
    for au in archivo_uris:
        if uri == au or au in uri:
            return True
    return False


# This is the discovery process
def ontology_discovery():
    # init parameters
    test_suite: TestSuite = TestSuite()

    for source, access_function in sources.SOURCES_GETFUN_MAPPING.items():
        discovery_logger.info(f"Started discovery of {source} URIs...")
        run_discovery(
            lst=access_function(),
            source=source,
            test_suite=test_suite,
        )
    discovery_logger.info("Started discovery of Databus SPOs...")
    for uri_list in query_databus.get_SPOs(logger=discovery_logger):
        run_discovery(lst=uri_list, source="SPOs", test_suite=test_suite)


def run_discovery(
    lst: Iterable[str], source: str, test_suite: TestSuite, logger=discovery_logger
):
    if lst is None:
        return
    all_onts = [ont.uri for ont in db.session.query(dbModels.Ontology.uri).all()]
    logger.info(f"Starting the discovery of URIs from {source}")
    for uri in lst:
        if check_uri_containment(uri, all_onts):
            continue
        output: List[ProcessStepLog] = []
        logger.info(f"Crawling the URI {uri}")
        try:
            archivo_version = discovery.discover_new_uri(
                uri=uri,
                vocab_uri_cache=all_onts,
                test_suite=test_suite,
                source=source,
                logger=logger,
                process_log=output,
            )
        except Exception:
            discovery_logger.exception(
                f"Problem during validating {uri}", exc_info=True
            )
            continue
        if archivo_version:
            logger.info(f"Successfully crawled the URI {uri}: {output[-1].message}")
            dev_version = archivo_version.handle_dev_version()
            dbOnt, dbVersion = database_utils.get_database_entries(archivo_version)
            if dev_version:
                dev_ont, dev_version = database_utils.get_database_entries(dev_version)
                db.session.add(dev_ont)
                db.session.add(dev_version)
                dbOnt.devel = dev_ont.uri
            db.session.add(dbOnt)
            db.session.add(dbVersion)
            try:
                db.session.commit()
                all_onts.append(archivo_version.nir)
            except Exception:
                db.session.rollback()
        elif check_is_nir_based_on_log(output):
            logger.info(f"No feasible result for URI {uri}: {output[-1].message}")
            fallout = dbModels.Fallout(
                uri=uri,
                source=source,
                inArchivo=False,
                error=json.dumps([step.to_dict() for step in output]),
            )
            db.session.add(fallout)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()


def ontology_official_update():
    all_ontologies_info = query_databus.nir_to_latest_version_files()
    if all_ontologies_info is None:
        diff_logger.warning(
            "There seems to be an error with the databus, no official diff possible"
        )
        return
    diff_logger.info("Started diff at " + datetime.now().strftime("%Y.%m.%d; %H:%M:%S"))
    test_suite = TestSuite()
    for i, ont in enumerate(db.session.query(dbModels.OfficialOntology).all()):

        # skip problematic ontologies
        if ont.uri in archivo_config.diff_skip_onts:
            diff_logger.info(
                f"{str(i + 1)}: Skipped ontology {ont.uri} due to earlier problems..."
            )
            continue

        data_writer = models.data_writer.FileWriter(
            path_base=archivo_config.localPath,
            target_url_base=archivo_config.DOWNLOAD_URL_BASE,
            logger=diff_logger,
        )

        diff_logger.info(f"{str(i + 1)}: Handling ontology: {ont.uri}")
        group, artifact = string_tools.generate_databus_identifier_from_uri(ont.uri)
        databusURL = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        try:
            urlInfo = all_ontologies_info[databusURL]
        except KeyError:
            diff_logger.error(f"Could't find databus artifact for {ont.uri}")
            continue
        try:
            success, message, archivo_version = update_archivo.update_for_ontology_uri(
                uri=ont.uri,
                last_version_timestamp=urlInfo["version"],
                test_suite=test_suite,
                source=ont.source,
                data_writer=data_writer,
                logger=diff_logger,
            )
        except Exception:
            diff_logger.exception(f"There was an error handling {str(ont)}")
            continue

        if success is None:
            dbFallout = dbModels.Fallout(
                uri=ont.uri,
                source=ont.source,
                inArchivo=True,
                error=message,
                ontology=ont.uri,
            )
            ont.crawling_status = False
            db.session.add(dbFallout)
        elif success:
            if message is None:
                ont.crawling_status = True
            else:
                dbFallout = dbModels.Fallout(
                    uri=ont.uri,
                    source=ont.source,
                    inArchivo=True,
                    error=message,
                    ontology=ont.uri,
                )
                ont.crawling_status = False
                db.session.add(dbFallout)

            # check for new trackThis URI
            dev_version = archivo_version.handle_dev_version()
            _, dbVersion = database_utils.get_database_entries(archivo_version)
            db.session.add(dbVersion)
            if dev_version:
                dev_ont, dev_version = database_utils.get_database_entries(dev_version)
                # update with new trackThis URI
                if ont.devel is not None and ont.devel != dev_ont.uri:
                    old_dev_obj = (
                        db.session.query(dbModels.DevelopOntology)
                        .filter_by(uri=ont.devel)
                        .first()
                    )
                    db.session.add(dev_ont)
                    db.session.add(dev_version)
                    # change old dev versions to new one
                    for v in (
                        db.session.query(dbModels.Version)
                        .filter_by(ontology=ont.devel)
                        .all()
                    ):
                        v.ontology = dev_ont.uri
                    #
                    ont.devel = dev_ont.uri
                    db.session.delete(old_dev_obj)
                # when new trackThis was found
                else:
                    db.session.add(dev_ont)
                    db.session.add(dev_version)
                    ont.devel = dev_ont.uri
        else:
            ont.crawling_status = True
        # commit changes to database
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


def ontology_dev_update():
    allOntologiesInfo = query_databus.nir_to_latest_version_files()
    if allOntologiesInfo is None:
        dev_diff_logger.warning(
            "There seems to be an error with the databus, no dev diff possible"
        )
        return
    dev_diff_logger.info(
        "Started diff at " + datetime.now().strftime("%Y.%m.%d; %H:%M:%S")
    )
    testSuite = TestSuite()
    for ont in db.session.query(dbModels.DevelopOntology).all():
        dev_diff_logger.info(f"Handling ontology: {ont.official} (DEV)")
        group, artifact = string_tools.generate_databus_identifier_from_uri(
            ont.official, dev=True
        )
        databusURL = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        try:
            urlInfo = allOntologiesInfo[databusURL]
        except KeyError:
            dev_diff_logger.error(f"Could't find databus artifact for {ont.uri}")
            continue

        data_writer = models.data_writer.FileWriter(
            path_base=archivo_config.localPath,
            target_url_base=archivo_config.DOWNLOAD_URL_BASE,
            logger=dev_diff_logger,
        )

        try:
            success, message, archivo_version = update_archivo.update_for_ontology_uri(
                uri=ont.official,
                last_version_timestamp=urlInfo["version"],
                test_suite=testSuite,
                source=ont.source,
                data_writer=data_writer,
                logger=diff_logger,
                dev_uri=ont.uri,
            )
        except Exception:
            dev_diff_logger.exception(f"Problem handling {str(ont)}")
            continue
        if success is None:
            dbFallout = dbModels.Fallout(
                uri=ont.uri,
                source=ont.source,
                inArchivo=True,
                error=message,
                ontology=ont.uri,
            )
            ont.crawling_status = False
            db.session.add(dbFallout)
        elif success:
            ont.crawling_status = True
            _, dev_version = database_utils.get_database_entries(archivo_version)
            db.session.add(dev_version)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        else:
            ont.crawling_status = True
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        # commit changes to database


# updates the star graph json every midnight
def update_star_graph():
    stats_path = os.path.join(string_tools.get_local_directory(), "stats")
    graphing.generate_star_graph(
        db.session.query(dbModels.OfficialOntology).all(), stats_path
    )


def update_ontology_index():
    old_officials = query_databus.get_last_official_index()
    old_official_uris = [uri for uri, src, date in old_officials]
    new_officials = db.session.query(dbModels.OfficialOntology).all()

    old_devs = query_databus.get_last_dev_index()
    old_dev_uris = [uri for uri, _, _, _ in old_devs]
    new_devs = db.session.query(dbModels.DevelopOntology).all()
    official_diff = [
        onto.uri for onto in new_officials if onto.uri not in old_official_uris
    ]
    develop_diff = [onto.uri for onto in new_devs if onto.uri not in old_dev_uris]
    if len(official_diff) <= 0 and len(develop_diff) <= 0:
        return
    else:
        discovery_logger.info(
            "New Ontologies:" + "\n".join(official_diff + develop_diff)
        )
        deploy_index()


def deploy_index():
    new_version_timestamp = datetime.now().strftime("%Y.%m.%d-%H%M%S")

    version_id = DatabusVersionIdentifier(
        user=archivo_config.DATABUS_USER,
        group="archivo-indices",
        artifact="ontologies",
        version=new_version_timestamp,
    )

    data_writer = models.data_writer.FileWriter(
        path_base=archivo_config.localPath,
        target_url_base=archivo_config.DOWNLOAD_URL_BASE,
        logger=diff_logger,
    )

    indices = {
        "official": database_utils.get_official_index_as_csv,
        "dev": database_utils.get_dev_index_as_csv,
    }

    for label, getfun in indices.items():

        content = getfun()
        shasum, content_length = string_tools.get_content_stats(bytes(content, "utf-8"))

        index_metadata = DatabusFileMetadata(
            version_identifier=version_id,
            content_variants={"type": label},
            sha_256_sum=shasum,
            content_length=content_length,
            file_extension="csv",
            compression=None,
        )

        data_writer.write_databus_file(content, index_metadata)

    distributions = data_writer.generate_distributions()

    dataset = databusclient.create_dataset(
        version_id=f"{archivo_config.DATABUS_BASE}/{version_id}",
        title="Archivo Ontologies",
        abstract="A complete list of all ontologies in DBpedia Archivo.",
        description="# All Ontologies\nThere are two different Files:\n- **official**: All Official Ontologies discovered.\n- **dev**: All develop stage URIs of ontologies related to **official**.",
        license_url="http://creativecommons.org/licenses/by-sa/3.0/",
        distributions=distributions,
        group_title="Archivo Indices",
        group_abstract="This group contains all the indices Archivo produces",
        group_description="This group contains all the indices Archivo produces",
    )

    try:
        databusclient.deploy(dataset, archivo_config.DATABUS_API_KEY)
        discovery_logger.info("Deployed new index to databus")
    except Exception as e:
        discovery_logger.error(f"Failed deploying to databus: {e}")


# checks if everything is configured correctly
def startup_check():
    available_files = [
        archivo_config.pelletPath,
        os.path.join(
            string_tools.get_local_directory(), "helpingBinaries", "DisplayAxioms.jar"
        ),
    ]
    available_dirs = [archivo_config.localPath]

    for f in available_files:
        if not os.path.isfile(f):
            return False, f"Unavailable File: {f}"

    for d in available_dirs:
        if not os.path.isdir(d):
            return False, f"Unavailable Directory: {d}"

    return True, None


if __name__ == "__main__":
    db.create_all()
    app.run(debug=True)
elif __name__ == "archivo":
    # checks if all resources are properly available
    correct, reason = startup_check()
    if not correct:
        import sys

        sys.exit(reason)
    # runs the cronjob when run with gunicorn
    cron = BackgroundScheduler(daemon=True)
    # add the archivo cronjobs:
    cron.add_job(
        update_ontology_index,
        "cron",
        id="index-backup-deploy",
        hour="22",
        day_of_week="mon-sun",
    )
    cron.add_job(
        update_star_graph,
        "cron",
        id="update_archivo_star_graph",
        hour="5,13,21",
        day_of_week="mon-sun",
    )
    cron.add_job(
        ontology_dev_update,
        "cron",
        id="archivo_dev_ontology_update",
        minute="*/10",
        day_of_week="mon-sun",
    )
    cron.add_job(
        ontology_official_update,
        "cron",
        id="archivo_official_ontology_update",
        hour="2,10,18",
        day_of_week="mon-sun",
    )
    cron.add_job(
        ontology_discovery,
        "cron",
        id="archivo_ontology_discovery",
        hour="15",
        minute="48",
        day_of_week="sat",
    )
    # Explicitly kick off the background thread
    cron.start()

    # Shutdown your cron thread if the web process is stopped
    atexit.register(lambda: cron.shutdown(wait=False))
