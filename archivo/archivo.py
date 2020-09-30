from webservice import app, db, dbModels
from apscheduler.schedulers.background import BackgroundScheduler
import atexit, os, crawlURIs, diffOntologies, dbUtils
from utils import ontoFiles, archivoConfig, stringTools, queryDatabus, generatePoms, inspectVocabs
from utils.validation import TestSuite
from utils.archivoLogs import discovery_logger, diff_logger
from datetime import datetime
from webservice.dbModels import Ontology, Version
from sqlalchemy.exc import IntegrityError
from urllib.parse import urlparse
import requests

cron = BackgroundScheduler(daemon=True)
# Explicitly kick off the background thread
cron.start()

indexFilePath = os.path.join(os.path.split(app.instance_path)[0], "indices", "vocab_index.json")
falloutFilePath = os.path.join(os.path.split(app.instance_path)[0], "indices", "fallout_index.csv")

# This is the discovery process
#@cron.scheduled_job("cron", id="archivo_ontology_discovery", hour="11", minute="11", day_of_week="sun")
def ontology_discovery():
    # init parameters
    dataPath = archivoConfig.localPath
    testSuite = TestSuite(os.path.join(os.path.split(app.instance_path)[0]))

    for uri in crawlURIs.getLovUrls():
        allOnts = [ont.uri for ont in db.session.query(dbModels.Ontology.uri).all()]
        success, isNir, message, dbOnts, dbVersions = crawlURIs.handleNewUri(uri, allOnts, dataPath, "LOV", False, testSuite=testSuite, logger=discovery_logger)
        if success:
            for ont in dbOnts:
                db.session.add(ont)
            for version in dbVersions:
                db.session.add(version)
            db.session.commit()
        elif not success and isNir:
            fallout = dbModels.Fallout(
                uri=uri,
                source="LOV",
                inArchivo=False,
                error = message
            )
            db.session.add(fallout)
            db.session.commit()

    for uri in crawlURIs.getPrefixURLs():
        allOnts = [ont.uri for ont in db.session.query(dbModels.Ontology.uri).all()]
        success, isNir, message, dbOnts, dbVersions = crawlURIs.handleNewUri(uri, allOnts, dataPath, "prefix.cc", False, testSuite=testSuite, logger=discovery_logger)
        if success:
            for ont in dbOnts:
                db.session.add(ont)
            for version in dbVersions:
                db.session.add(version)
            db.session.commit()
        elif not success and isNir:
            fallout = dbModels.Fallout(
                uri=uri,
                source="prefix.cc",
                inArchivo=False,
                error = message
            )
            db.session.add(fallout)
            db.session.commit()


    #for uri in hashUris:
        #crawlURIs.handleNewUri(uri, ontoIndex, dataPath, fallout, "spoHashUris", False, testSuite=testSuite, logger=discovery_logger)
        #ontoFiles.writeIndexJsonToFile(ontoIndex, indexFilePath)
        #ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)

    #for uri in prefixUris:
        #crawlURIs.handleNewUri(uri, ontoIndex, dataPath, fallout, "prefix.cc", False, testSuite=testSuite, logger=discovery_logger)
        #ontoFiles.writeIndexJsonToFile(ontoIndex, indexFilePath)
        #ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)

    #for uri in getVoidUris(voidPath):
        #crawlURIs.handleNewUri(uri, index, dataPath, fallout, "voidUris", False, testSuite=testSuite)
        #ontoFiles.writeIndexJsonToFile(index, indexFilePath)
        #ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)


#@cron.scheduled_job("cron", id="archivo_official_ontology_update", hour="2,10,18", day_of_week="mon-sun")
def ontology_official_update():
    dataPath = archivoConfig.localPath
    allOntologiesInfo = queryDatabus.latestNtriples()
    if allOntologiesInfo == None:
        diff_logger.warning("There seems to be an error with the databus, no official diff possible")
        return
    diff_logger.info("Started diff at "+datetime.now().strftime("%Y.%m.%d; %H:%M:%S"))
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
        success, message, dbTrackOntology, dbVersions = diffOntologies.handleDiffForUri(ont.uri, dataPath, urlInfo["meta"], urlInfo["ntFile"], urlInfo["version"], testSuite)
        if success == None:
            dbFallout = dbModels.Fallout(
                uri=ont.uri,
                source=ont.source,
                inArchivo=True,
                error=message,
                ontology=ont.uri
            )
            ont.crawling_status = False
            db.session.add(dbFallout)
        elif success:
            ont.crawling_status = True
            if dbTrackOntology != None:
                if ont.devel != None and ont.devel != dbTrackOntology.uri:
                    old_dev_obj = db.session.query(dbModels.DevelopOntology).filter_by(uri=ont.devel)
                    db.session.add(dbTrackOntology)
                    for v in db.session.query(dbModels.Version).filter_by(ontology=ont.devel).all():
                        v.ontology = dbTrackOntology.uri
                    db.session.delete(old_dev_obj)
                else:
                    db.session.add(dbTrackOntology)
            for dbV in dbVersions:
                db.session.add(dbV)
        else:
            ont.crawling_status = True
        # commit changes to database
        db.session.commit()

def makeDiffForURI(uri):
    dataPath = archivoConfig.localPath
    allOntologiesInfo = queryDatabus.latestNtriples()
    ont = db.session.query(dbModels.OfficialOntology).filter_by(uri=uri).first()
    testSuite = TestSuite(os.path.join(os.path.split(app.instance_path)[0]))
    diff_logger.info(f"Handling ontology: {ont.uri}")
    group, artifact = stringTools.generateGroupAndArtifactFromUri(ont.uri)
    databusURL = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
    try:
        urlInfo = allOntologiesInfo[databusURL]
    except KeyError:
        diff_logger.error(f"Could't find databus artifact for {ont.uri}")
        return
    success, message, dbTrackOntology, dbVersions = diffOntologies.handleDiffForUri(ont.uri, dataPath, urlInfo["meta"], urlInfo["ntFile"], urlInfo["version"], testSuite)
    if success == None:
        dbFallout = dbModels.Fallout(
            uri=ont.uri,
            source=ont.source,
            inArchivo=True,
            error=message,
            ontology=ont.uri
            ) 
        ont.crawling_status = False
        db.session.add(dbFallout)
    elif success:
        ont.crawling_status = True
        if dbTrackOntology != None:
            if ont.devel != None and ont.devel != dbTrackOntology.uri:
                old_dev_obj = db.session.query(dbModels.DevelopOntology).filter_by(uri=ont.devel)
                db.session.add(dbTrackOntology)
                for v in db.session.query(dbModels.Version).filter_by(ontology=ont.devel).all():
                    v.ontology = dbTrackOntology.uri
                db.session.delete(old_dev_obj)
            else:
                db.session.add(dbTrackOntology)
        for dbV in dbVersions:
            db.session.add(dbV)
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
        filename = urlInfo['ntFile'].split('/')[-1]
        latest_version_dir = os.path.join(dataPath, group, artifact, urlInfo['version'])
        filepath = os.path.join(latest_version_dir, filename)
        if not os.path.isfile(filepath):
            os.makedirs(latest_version_dir, exist_ok=True)
            oldOntologyResponse = requests.get(urlInfo['ntFile'])
            oldOntologyResponse.encoding = "utf-8"
            if oldOntologyResponse.status_code > 400:
                print(f'Couldnt download ntriples file for {ont.uri}')
            with open(filepath, "w") as latestNtriples:
                print(oldOntologyResponse.text, file=latestNtriples)
        graph = inspectVocabs.getGraphOfVocabFile(filepath)
        if graph == None:
            print(f'Error loading graph of {ont.uri}')
        trackURI = inspectVocabs.getTrackThisURI(graph)
        if trackURI != oldDevURI:
            success, message, onto, version = crawlURIs.handleDevURI(ont.uri, trackURI, dataPath, testSuite, diff_logger)
            


#@cron.scheduled_job("cron", id="archivo_dev_ontology_update", minute="*/10", day_of_week="mon-sun")
def ontology_dev_update():
    dataPath = archivoConfig.localPath
    allOntologiesInfo = queryDatabus.latestNtriples()
    if allOntologiesInfo == None:
        diff_logger.warning("There seems to be an error with the databus, no dev diff possible")
        return
    diff_logger.info("Started diff at "+datetime.now().strftime("%Y.%m.%d; %H:%M:%S"))
    testSuite = TestSuite(os.path.join(os.path.split(app.instance_path)[0]))
    for ont in db.session.query(dbModels.DevelopOntology).all():
        diff_logger.info(f"Handling ontology: {ont.official} (DEV)")
        group, artifact = stringTools.generateGroupAndArtifactFromUri(ont.official, dev=True)
        databusURL = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        try:
            urlInfo = allOntologiesInfo[databusURL]
        except KeyError:
            diff_logger.error(f"Could't find databus artifact for {ont.uri}")
            continue
        success, message, dbVersion = diffOntologies.handleDiffForUri(ont.official, dataPath, urlInfo["meta"], urlInfo["ntFile"], urlInfo["version"], testSuite, devURI=ont.uri)
        if success == None:
            dbFallout = dbModels.Fallout(
                uri=ont.uri,
                source=ont.source,
                inArchivo=True,
                error=message,
                ontology=ont.uri
            )
            ont.crawling_status = False
            db.session.add(dbFallout)
        elif success:
            ont.crawling_status = True
            db.session.add(dbVersion)
            db.session.commit()
        else:
            ont.crawling_status = True
            db.session.commit()
        # commit changes to database
        



#@cron.scheduled_job("cron", id="index-backup-deploy", hour="22", day_of_week="mon-sun")
def updateOntologyIndex():
    oldOntoIndex = queryDatabus.loadLastIndex()
    newOntoIndex = db.session.query(dbModels.Ontology).all()
    diff = [onto.uri for onto in newOntoIndex if onto.uri not in [uri for uri, src, date in oldOntoIndex]]
    discovery_logger.info("New Ontologies:" + "\n".join(diff))
    if len(oldOntoIndex) != len(newOntoIndex):
        newVersionString = datetime.now().strftime("%Y.%m.%d-%H%M%S")
        artifactPath = os.path.join(archivoConfig.localPath, "archivo-indices", "ontologies")
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
        status, log = generatePoms.callMaven(os.path.join(artifactPath, "pom.xml"), "deploy")


# Shutdown your cron thread if the web process is stopped
atexit.register(lambda: cron.shutdown(wait=False))

if __name__ == "__main__":
    db.create_all()
    app.run(debug=True)