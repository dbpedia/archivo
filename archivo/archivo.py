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
from utils.archivoLogs import discovery_logger, diff_logger
from datetime import datetime
import requests
import graphing
import json

cron = BackgroundScheduler(daemon=True)
# Explicitly kick off the background thread
cron.start()


# This is the discovery process
# @cron.scheduled_job("cron", id="archivo_ontology_discovery", hour="15", minute="48", day_of_week="sat")
def ontology_discovery():
    # init parameters
    dataPath = archivoConfig.localPath
    testSuite = TestSuite(os.path.join(os.path.split(app.instance_path)[0]))

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
    if lst == None:
        return
    for uri in lst:
        allOnts = [ont.uri for ont in db.session.query(dbModels.Ontology.uri).all()]
        output = []
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
        if success:
            succ, message, dev_version = archivo_version.handleTrackThis()
            dbOnt, dbVersion = dbUtils.getDatabaseEntry(archivo_version)
            if succ:
                dev_ont, dev_version = dbUtils.getDatabaseEntry(dev_version)
                db.session.add(dev_ont)
                db.session.add(dev_version)
                dbOnt.devel = dev_ont.uri
            db.session.add(dbOnt)
            db.session.add(dbVersion)
            db.session.commit()
        elif not success and isNir:
            fallout = dbModels.Fallout(
                uri=uri, source=source, inArchivo=False, error=json.dumps(output)
            )
            db.session.add(fallout)
            db.session.commit()


# @cron.scheduled_job("cron", id="archivo_official_ontology_update", hour="2,10,18", day_of_week="mon-sun")
def ontology_official_update():
    dataPath = archivoConfig.localPath
    allOntologiesInfo = queryDatabus.latestNtriples()
    if allOntologiesInfo == None:
        diff_logger.warning(
            "There seems to be an error with the databus, no official diff possible"
        )
        return
    diff_logger.info("Started diff at " + datetime.now().strftime("%Y.%m.%d; %H:%M:%S"))
    testSuite = TestSuite(os.path.join(os.path.split(app.instance_path)[0]))
    for ont in db.session.query(dbModels.OfficialOntology).all():
        diff_logger.info(f"Handling ontology: {ont.uri}")
        group, artifact = stringTools.generateGroupAndArtifactFromUri(ont.uri)
        databusURL = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        try:
            urlInfo = allOntologiesInfo[databusURL]
        except KeyError:
            diff_logger.error(f"Could't find databus artifact for {ont.uri}")
            continue
        success, message, archivo_version = diffOntologies.handleDiffForUri(
            ont.uri,
            dataPath,
            urlInfo["meta"],
            urlInfo["ntFile"],
            urlInfo["version"],
            testSuite,
            ont.source,
        )
        if success == None:
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
            succ, message, dev_version = archivo_version.handleTrackThis()
            dbOnt, dbVersion = dbUtils.getDatabaseEntry(archivo_version)
            if succ:
                dev_ont, dev_version = dbUtils.getDatabaseEntry(dev_version)
                # update with new trackThis URI
                if ont.devel != None and ont.devel != dev_ont.uri:
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
        db.session.commit()


def scanForTrackThisURIs():
    dataPath = archivoConfig.localPath
    allOntologiesInfo = queryDatabus.latestNtriples()
    testSuite = TestSuite(os.path.join(os.path.split(app.instance_path)[0]))
    for ont in db.session.query(dbModels.OfficialOntology).all():
        group, artifact = stringTools.generateGroupAndArtifactFromUri(ont.uri)
        databusURL = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        oldDevURI = ont.devel
        try:
            urlInfo = allOntologiesInfo[databusURL]
        except KeyError:
            diff_logger.error(f"Could't find databus artifact for {ont.uri}")
            continue
        filename = urlInfo["ntFile"].split("/")[-1]
        latest_version_dir = os.path.join(dataPath, group, artifact, urlInfo["version"])
        filepath = os.path.join(latest_version_dir, filename)
        if not os.path.isfile(filepath):
            os.makedirs(latest_version_dir, exist_ok=True)
            oldOntologyResponse = requests.get(urlInfo["ntFile"])
            oldOntologyResponse.encoding = "utf-8"
            if oldOntologyResponse.status_code > 400:
                print(f"Couldnt download ntriples file for {ont.uri}")
            with open(filepath, "w") as latestNtriples:
                print(oldOntologyResponse.text, file=latestNtriples)
        graph = inspectVocabs.getGraphOfVocabFile(filepath)
        if graph == None:
            print(f"Error loading graph of {ont.uri}")
        trackURI = inspectVocabs.getTrackThisURI(graph)
        if trackURI != oldDevURI:
            success, message, onto, version = crawlURIs.handleDevURI(
                ont.uri, trackURI, dataPath, testSuite, diff_logger
            )


# @cron.scheduled_job("cron", id="archivo_dev_ontology_update", minute="*/10", day_of_week="mon-sun")
def ontology_dev_update():
    dataPath = archivoConfig.localPath
    allOntologiesInfo = queryDatabus.latestNtriples()
    if allOntologiesInfo == None:
        diff_logger.warning(
            "There seems to be an error with the databus, no dev diff possible"
        )
        return
    diff_logger.info("Started diff at " + datetime.now().strftime("%Y.%m.%d; %H:%M:%S"))
    testSuite = TestSuite(os.path.join(os.path.split(app.instance_path)[0]))
    for ont in db.session.query(dbModels.DevelopOntology).all():
        diff_logger.info(f"Handling ontology: {ont.official} (DEV)")
        group, artifact = stringTools.generateGroupAndArtifactFromUri(
            ont.official, dev=True
        )
        databusURL = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        try:
            urlInfo = allOntologiesInfo[databusURL]
        except KeyError:
            diff_logger.error(f"Could't find databus artifact for {ont.uri}")
            continue
        success, message, archivo_version = diffOntologies.handleDiffForUri(
            ont.official,
            dataPath,
            urlInfo["meta"],
            urlInfo["ntFile"],
            urlInfo["version"],
            testSuite,
            ont.source,
            devURI=ont.uri,
        )
        if success == None:
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
            db.session.commit()
        else:
            ont.crawling_status = True
            db.session.commit()
        # commit changes to database


# updates the star graph json every midnight
# @cron.scheduled_job("cron", id="update_archivo_star_graph", hour="0", day_of_week="mon-sun")
def update_star_graph():
    stats_path = os.path.join(os.path.split(app.instance_path)[0], "stats")
    graphing.generate_star_graph(
        db.session.query(dbModels.OfficialOntology).all(), stats_path
    )


# @cron.scheduled_job("cron", id="index-backup-deploy", hour="22", day_of_week="mon-sun")
def updateOntologyIndex():
    oldOntoIndex = queryDatabus.loadLastIndex()
    newOntoIndex = db.session.query(dbModels.OfficialOntology).all()
    diff = [
        onto.uri
        for onto in newOntoIndex
        if onto.uri not in [uri for uri, src, date in oldOntoIndex]
    ]
    discovery_logger.info("New Ontologies:" + "\n".join(diff))
    if len(diff) <= 0:
        return
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
    dbUtils.writeIndexAsCSV(os.path.join(indexpath, "ontologies.csv"))
    # deploy
    status, log = generatePoms.callMaven(
        os.path.join(artifactPath, "pom.xml"), "deploy"
    )


# Shutdown your cron thread if the web process is stopped
atexit.register(lambda: cron.shutdown(wait=False))

if __name__ == "__main__":
    db.create_all()
    app.run(debug=True)
