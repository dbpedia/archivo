from webservice import app, db, dbModels
from apscheduler.schedulers.background import BackgroundScheduler
import atexit, os, crawlURIs, diffOntologies, dbUtils
from utils import ontoFiles, archivoConfig, stringTools, queryDatabus, generatePoms
from utils.validation import TestSuite
from utils.archivoLogs import discovery_logger, diff_logger
from datetime import datetime
from webservice.dbModels import Ontology, Version
from sqlalchemy.exc import IntegrityError

cron = BackgroundScheduler(daemon=True)
# Explicitly kick off the background thread
cron.start()

indexFilePath = os.path.join(os.path.split(app.instance_path)[0], "indices", "vocab_index.json")
falloutFilePath = os.path.join(os.path.split(app.instance_path)[0], "indices", "fallout_index.csv")

# This is the discovery process
@cron.scheduled_job("cron", id="archivo_ontology_discovery", hour="11", minute="11", day_of_week="sun")
def ontology_discovery():
    # init parameters
    dataPath = archivoConfig.localPath


    testSuite = TestSuite(os.path.join(os.path.split(app.instance_path)[0]))
    # load the other sources
    #hashUris = ontoFiles.loadListFile(archivoConfig.hashUriPath)

    #prefixUris = ontoFiles.secondColumnOfTSV(archivoConfig.prefixUrisPath)

    for uri in crawlURIs.getLovUrls():
        allOnts = [ont.uri for ont in db.session.query(dbModels.Ontology.uri).all()]
        success, isNir, message, dbOnt, dbVersion = crawlURIs.handleNewUri(uri, allOnts, dataPath, "LOV", False, testSuite=testSuite, logger=discovery_logger)
        if success:
            db.session.add(dbOnt)
            db.session.add(dbVersion)
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
        success, isNir, message, dbOnt, dbVersion = crawlURIs.handleNewUri(uri, allOnts, dataPath, "prefix.cc", False, testSuite=testSuite, logger=discovery_logger)
        if success:
            db.session.add(dbOnt)
            db.session.add(dbVersion)
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


@cron.scheduled_job("cron", id="archivo_ontology_update", hour="2,10,18", day_of_week="mon-sun")
def ontology_update():
    dataPath = archivoConfig.localPath
    allOntologiesInfo = queryDatabus.latestNtriples()
    diff_logger.info("Started diff at "+datetime.now().strftime("%Y.%m.%d; %H:%M:%S"))
    testSuite = TestSuite(os.path.join(os.path.split(app.instance_path)[0]))
    for ont in db.session.query(dbModels.Ontology).all():
        diff_logger.info(f"Handling ontology: {ont.uri}")
        group, artifact = stringTools.generateGroupAndArtifactFromUri(ont.uri)
        databusURL = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        try:
            urlInfo = allOntologiesInfo[databusURL]
        except KeyError:
            diff_logger.error(f"Could't find databus artifact for {ont.uri}")
            continue
        success, message, dbVersion = diffOntologies.handleDiffForUri(ont.uri, dataPath, urlInfo["meta"], urlInfo["ntFile"], urlInfo["version"], testSuite)
        if success == None:
            dbFallout = dbModels.Fallout(
                uri=ont.uri,
                source=ont.source,
                inArchivo=True,
                error=message
            )
            ont.crawlingStatus = False
            ont.crawlingError = message
            db.session.add(dbFallout)
        elif success:
            ont.crawlingStatus = True
            ont.crawlingError = message
            db.session.add(dbVersion)
        else:
            ont.crawlingStatus = True
            ont.crawlingError = message
        # commit changes to database
        db.session.commit()



# Shutdown your cron thread if the web process is stopped
atexit.register(lambda: cron.shutdown(wait=False))

def rebuildDatabase():
    db.create_all()
    urisInDatabase = db.session.query(dbModels.Ontology).all()
    urisInDatabase = [ont.uri for ont in urisInDatabase]
    oldIndex = queryDatabus.loadLastIndex()
    for uri, source, date in oldIndex:
        if uri in urisInDatabase:
            print(f"Already listed: {uri}")
            continue
        try:
            timestamp = datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            timestamp = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
        print("Handling URI "+ uri)
        group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
        title, comment, versions_info = queryDatabus.getInfoForArtifact(group, artifact)
        ontology = dbModels.Ontology(
            uri=uri,
            title=title,
            source=source,
            accessDate=timestamp,
        )
        db.session.add(ontology)
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
        print(len(Ontology.query.all()))

@cron.scheduled_job("cron", id="index-backup-deploy", hour="22", day_of_week="mon-sun")
def updateOntologyIndex():
    oldOntoIndex = queryDatabus.loadLastIndex()
    newOntoIndex = db.session.query(dbModels.Ontology).all()
    diff = [onto.uri for onto in newOntoIndex if onto.uri not in [uri for uri, src, date in oldOntoIndex]]
    print(diff)
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


if __name__ == "__main__":
    db.create_all()
    app.run(debug=False)