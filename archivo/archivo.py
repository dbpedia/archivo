from webservice import app, db, dbModels
from apscheduler.schedulers.background import BackgroundScheduler
import atexit, os, crawlURIs, diffOntologies
from utils import ontoFiles, archivoConfig, stringTools, queryDatabus
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
#@cron.scheduled_job("cron", id="archivo_ontology_discovery", hour="12", minute="57")
def ontology_discovery():
    # init parameters
    dataPath = archivoConfig.localPath


    testSuite = TestSuite(os.path.join(os.path.split(app.instance_path)[0]))
    # load the other sources
    #hashUris = ontoFiles.loadListFile(archivoConfig.hashUriPath)

    #prefixUris = ontoFiles.secondColumnOfTSV(archivoConfig.prefixUrisPath)

    for uri in crawlURIs.getLovUrls():
        success, isNir, message, dbOnt, dbVersion = crawlURIs.handleNewUri(uri, ontoIndex, dataPath, "LOV", False, testSuite=testSuite, logger=discovery_logger)
        if success:
            db.session.add(dbOnt)
            db.session.add(dbVersion)
            db.session.commit()
        elif not success and isNir:
            fallout = dbModels.Fallout(
                uri=uri,
                source="user-suggestion",
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

def updateDatabase():
    urisInDatabase = db.session.query(Ontology.uri).all()
    urisInDatabase = [t[0] for t in urisInDatabase]
    for uri in ontoIndex:
        if uri in urisInDatabase:
            print(f"Already listed: {uri}")
            continue
        print("Handling URI "+ uri)
        group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
        title, comment, versions_info = queryDatabus.getInfoForArtifact(group, artifact)
        ontology = Ontology(
            uri=uri,
            title=title,
            source=ontoIndex[uri]["source"],
            accessDate=datetime.strptime(ontoIndex[uri]["accessed"], "%Y-%m-%d %H:%M:%S"),
        )
        db.session.add(ontology)
        for info_dict in versions_info:
            db.session.add(Version(
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


if __name__ == "__main__":
    db.create_all()
    app.run(debug=False)