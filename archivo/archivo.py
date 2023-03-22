import atexit
from typing import List

from archivo.utils import dbUtils, graphing
from archivo.update import update_archivo
import json
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from archivo.crawling import discovery, sources
from utils import archivoConfig, stringTools, queryDatabus, generatePoms
from utils.archivoLogs import (
    discovery_logger,
    diff_logger,
    dev_diff_logger,
    webservice_logger,
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
    dataPath = archivoConfig.localPath
    testSuite = TestSuite()

    discovery_logger.info("Started discovery of LOV URIs...")
    run_discovery(sources.getLovUrls(), "LOV", dataPath, testSuite)
    discovery_logger.info("Started discovery of prefix.cc URIs...")
    run_discovery(sources.getPrefixURLs(), "prefix.cc", dataPath, testSuite)
    discovery_logger.info("Started discovery of VOID URIs...")
    run_discovery(queryDatabus.get_VOID_URIs(), "VOID mod", dataPath, testSuite)
    discovery_logger.info("Started discovery of Databus SPOs...")
    for uri_list in queryDatabus.get_SPOs(logger=discovery_logger):
        run_discovery(uri_list, "SPOs", dataPath, testSuite)


def run_discovery(lst, source, dataPath, testSuite, logger=discovery_logger):
    logger.info(f"Crunching {len(lst)} ontologies....")
    if lst is None:
        return
    allOnts = [ont.uri for ont in db.session.query(dbModels.Ontology.uri).all()]
    for uri in lst:
        if check_uri_containment(uri, allOnts):
            continue
        output = []
        try:
            success, isNir, archivo_version = discovery.handleNewUri(
                uri,
                allOnts,
                dataPath,
                source,
                False,
                testSuite=testSuite,
                logger=logger,
                user_output=output,
            )
        except Exception:
            discovery_logger.exception(
                f"Problem during validating {uri}", exc_info=True
            )
            continue
        if success:
            succ, dev_version = archivo_version.handleTrackThis()
            dbOnt, dbVersion = dbUtils.getDatabaseEntry(archivo_version)
            if succ:
                dev_ont, dev_version = dbUtils.getDatabaseEntry(dev_version)
                db.session.add(dev_ont)
                db.session.add(dev_version)
                dbOnt.devel = dev_ont.uri
            db.session.add(dbOnt)
            db.session.add(dbVersion)
            try:
                db.session.commit()
                allOnts.append(archivo_version.nir)
            except Exception:
                db.session.rollback()
        elif not success and isNir:
            fallout = dbModels.Fallout(
                uri=uri, source=source, inArchivo=False, error=json.dumps(output)
            )
            db.session.add(fallout)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()


def ontology_official_update():
    dataPath = archivoConfig.localPath
    allOntologiesInfo = queryDatabus.latestNtriples()
    if allOntologiesInfo is None:
        diff_logger.warning(
            "There seems to be an error with the databus, no official diff possible"
        )
        return
    diff_logger.info("Started diff at " + datetime.now().strftime("%Y.%m.%d; %H:%M:%S"))
    testSuite = TestSuite()
    for i, ont in enumerate(db.session.query(dbModels.OfficialOntology).all()):

        # skip problematic ontologies
        if ont.uri in archivoConfig.diff_skip_onts:
            diff_logger.info(
                f"{str(i + 1)}: Skipped ontology {ont.uri} due to earlier problems..."
            )
            continue

        diff_logger.info(f"{str(i + 1)}: Handling ontology: {ont.uri}")
        group, artifact = stringTools.generate_databus_identifier_from_uri(ont.uri)
        databusURL = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        try:
            urlInfo = allOntologiesInfo[databusURL]
        except KeyError:
            diff_logger.error(f"Could't find databus artifact for {ont.uri}")
            continue
        try:
            success, message, archivo_version = diffOntologies.handleDiffForUri(
                ont.uri,
                dataPath,
                urlInfo["meta"],
                urlInfo["ntFile"],
                urlInfo["version"],
                testSuite,
                ont.source,
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
            succ, dev_version = archivo_version.handleTrackThis()
            _, dbVersion = dbUtils.getDatabaseEntry(archivo_version)
            db.session.add(dbVersion)
            if succ:
                dev_ont, dev_version = dbUtils.getDatabaseEntry(dev_version)
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
    dataPath = archivoConfig.localPath
    allOntologiesInfo = queryDatabus.latestNtriples()
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
        group, artifact = stringTools.generate_databus_identifier_from_uri(
            ont.official, dev=True
        )
        databusURL = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        try:
            urlInfo = allOntologiesInfo[databusURL]
        except KeyError:
            dev_diff_logger.error(f"Could't find databus artifact for {ont.uri}")
            continue
        try:
            success, message, archivo_version = diffOntologies.handleDiffForUri(
                ont.official,
                dataPath,
                urlInfo["meta"],
                urlInfo["ntFile"],
                urlInfo["version"],
                testSuite,
                ont.source,
                devURI=ont.uri,
                logger=dev_diff_logger,
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
            _, dev_version = dbUtils.getDatabaseEntry(archivo_version)
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
    stats_path = os.path.join(stringTools.get_local_directory(), "stats")
    graphing.generate_star_graph(
        db.session.query(dbModels.OfficialOntology).all(), stats_path
    )


def updateOntologyIndex():
    old_officials = queryDatabus.get_last_official_index()
    old_official_uris = [uri for uri, src, date in old_officials]
    new_officials = db.session.query(dbModels.OfficialOntology).all()

    old_devs = queryDatabus.get_last_dev_index()
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
    newVersionString = datetime.now().strftime("%Y.%m.%d-%H%M%S")
    artifactPath = os.path.join(
        archivoConfig.localPath, "archivo-indices", "ontologies"
    )
    indexpath = os.path.join(artifactPath, newVersionString)
    os.makedirs(indexpath, exist_ok=True)
    # write parent pom if not existent
    if not os.path.isfile(
            os.path.join(archivoConfig.localPath, "archivo-indices", "pom.xml")
    ):
        pomString = generatePoms.generateParentPom(
            groupId="archivo-indices",
            packaging="pom",
            modules=[],
            packageDirectory=archivoConfig.packDir,
            downloadUrlPath=archivoConfig.downloadUrl,
            publisher=archivoConfig.pub,
            maintainer=archivoConfig.pub,
            groupdocu="This dataset contains the index of all ontologies from DBpedia Archivo",
        )
        with open(
                os.path.join(archivoConfig.localPath, "archivo-indices", "pom.xml"), "w+"
        ) as parentPomFile:
            print(pomString, file=parentPomFile)
    # write new md description of artifact
    if not os.path.isfile(
            os.path.join(
                archivoConfig.localPath, "archivo-indices", "ontologies", "ontologies.md"
            )
    ):
        generatePoms.writeMarkdownDescription(
            artifactPath,
            "ontologies",
            "Archivo Ontologies",
            "A complete list of all ontologies in DBpedia Archivo.",
            "# All Ontologies\nThere are two different Files:\n- **official**: All Official Ontologies discovered.\n- **dev**: All develop stage URIs of ontologies related to **official**.",
        )
    # update pom
    with open(os.path.join(artifactPath, "pom.xml"), "w+") as pomfile:
        pomstring = generatePoms.generateChildPom(
            groupId="archivo-indices",
            artifactId="ontologies",
            version=newVersionString,
            license="http://creativecommons.org/licenses/by-sa/3.0/",
            packaging="jar",
        )
        print(pomstring, file=pomfile)
    # write new index
    dbUtils.write_official_index(
        os.path.join(indexpath, "ontologies_type=official.csv")
    )
    dbUtils.write_dev_index(os.path.join(indexpath, "ontologies_type=dev.csv"))
    # deploy
    status_code, log = generatePoms.callMaven(
        os.path.join(artifactPath, "pom.xml"), "deploy"
    )
    if status_code == 0:
        discovery_logger.info("Deployed new index to databus")
    else:
        discovery_logger.warning("Failed deploying to databus")
        discovery_logger.warning(log)


# checks if everything is configured correctly
def startup_check():
    available_files = [
        archivoConfig.pelletPath,
        os.path.join(stringTools.get_local_directory(), "helpingBinaries", "DisplayAxioms.jar"),
    ]
    available_dirs = [archivoConfig.localPath]

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
        updateOntologyIndex,
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
