from webservice import app, db, dbModels
from apscheduler.schedulers.background import BackgroundScheduler
import atexit, os, crawlURIs, diffOntologies, dbUtils
from utils import (
    ontoFiles,
    archivoConfig,
    stringTools,
    queryDatabus,
    generatePoms,
    inspectVocabs,
)
from utils.validation import TestSuite
from utils.archivoLogs import discovery_logger, diff_logger, dev_diff_logger, webservice_logger
from datetime import datetime
import graphing
import json

cron = BackgroundScheduler(daemon=True)
# Explicitly kick off the background thread
cron.start()


def get_correct_path() -> str:
    archivo_path = os.path.split(app.instance_path)[0]
    if os.path.isdir(os.path.join(archivo_path, "shacl")) and os.path.isfile(os.path.join(archivo_path, "helpingBinaries", "DisplayAxioms.jar")):
        return archivo_path
    else:
        webservice_logger.error(f"{archivo_path} is not the correct path")
        exit(1)


archivo_path = get_correct_path()


# This is the discovery process
# @cron.scheduled_job("cron", id="archivo_ontology_discovery", hour="15", minute="48", day_of_week="sat")
def ontology_discovery():
    # init parameters
    dataPath = archivoConfig.localPath
    testSuite = TestSuite(archivo_path)

    discovery_logger.info("Started discovery of LOV URIs...")
    run_discovery(crawlURIs.getLovUrls(), "LOV", dataPath, testSuite)
    discovery_logger.info("Started discovery of prefix.cc URIs...")
    run_discovery(crawlURIs.getPrefixURLs(), "prefix.cc", dataPath, testSuite)
    discovery_logger.info("Started discovery of VOID URIs...")
    run_discovery(crawlURIs.get_VOID_URIs(), "VOID mod", dataPath, testSuite)
    discovery_logger.info("Started discovery of Databus SPOs...")
    for uri_list in queryDatabus.get_SPOs():
        run_discovery(uri_list, "SPOs", dataPath, testSuite)


def run_discovery(lst, source, dataPath, testSuite, logger=discovery_logger):
    if lst is None:
        return
    for uri in lst:
        allOnts = [ont.uri for ont in db.session.query(dbModels.Ontology.uri).all()]
        output = []
        try:
            success, isNir, archivo_version = crawlURIs.handleNewUri(
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
            discovery_logger.exception(f"Problem during validating {uri}", exc_info=True)
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


# @cron.scheduled_job("cron", id="archivo_official_ontology_update", hour="2,10,18", day_of_week="mon-sun")
def ontology_official_update():
    dataPath = archivoConfig.localPath
    allOntologiesInfo = queryDatabus.latestNtriples()
    if allOntologiesInfo is None:
        diff_logger.warning(
            "There seems to be an error with the databus, no official diff possible"
        )
        return
    diff_logger.info("Started diff at " + datetime.now().strftime("%Y.%m.%d; %H:%M:%S"))
    testSuite = TestSuite(archivo_path)
    for i, ont in enumerate(db.session.query(dbModels.OfficialOntology).all()):
        diff_logger.info(f"{str(i+1)}: Handling ontology: {ont.uri}")
        group, artifact = stringTools.generateGroupAndArtifactFromUri(ont.uri)
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
            ont.crawling_status = True

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


# @cron.scheduled_job("cron", id="archivo_dev_ontology_update", minute="*/10", day_of_week="mon-sun")
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
    testSuite = TestSuite(archivo_path)
    for ont in db.session.query(dbModels.DevelopOntology).all():
        dev_diff_logger.info(f"Handling ontology: {ont.official} (DEV)")
        group, artifact = stringTools.generateGroupAndArtifactFromUri(
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
# @cron.scheduled_job("cron", id="update_archivo_star_graph", hour="4,12,20", day_of_week="mon-sun")
def update_star_graph():
    stats_path = os.path.join(os.path.split(app.instance_path)[0], "stats")
    graphing.generate_star_graph(
        db.session.query(dbModels.OfficialOntology).all(), stats_path
    )


# @cron.scheduled_job("cron", id="index-backup-deploy", hour="22", day_of_week="mon-sun")
def updateOntologyIndex():
    old_officials = queryDatabus.get_last_official_index()
    new_officials = db.session.query(dbModels.OfficialOntology).all()

    old_devs = queryDatabus.get_last_dev_index()
    new_devs = db.session.query(dbModels.DevelopOntology).all()
    official_diff = [
        onto.uri
        for onto in new_officials
        if onto.uri not in [uri for uri, src, date in old_officials]
    ]
    develop_diff = [
        onto.uri
        for onto in new_devs
        if onto.uri not in [uri for uri, _, _, _ in old_devs]
    ]
    discovery_logger.info("New Ontologies:" + "\n".join(official_diff + develop_diff))
    if len(official_diff) <= 0 and len(develop_diff) <= 0:
        return
    else:
        deploy_index()


def deploy_index():
    newVersionString = datetime.now().strftime("%Y.%m.%d-%H%M%S")
    artifactPath = os.path.join(
        archivoConfig.localPath, "archivo-indices", "ontologies"
    )
    indexpath = os.path.join(artifactPath, newVersionString)
    os.makedirs(indexpath, exist_ok=True)
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
    status, log = generatePoms.callMaven(
        os.path.join(artifactPath, "pom.xml"), "deploy"
    )
    if status:
        discovery_logger.info("Deployed new index to databus")
    else:
        discovery_logger.warning("Failed deploying to databus")
        discovery_logger.warning(log)


# Shutdown your cron thread if the web process is stopped
atexit.register(lambda: cron.shutdown(wait=False))



if __name__ == "__main__":
    db.create_all()
    app.run(debug=True)
