from webservice import app
from webservice.routes import ontoIndex, fallout
from apscheduler.schedulers.background import BackgroundScheduler
import atexit, os, crawlURIs, diffOntologies
from utils import ontoFiles, archivoConfig, stringTools, queryDatabus
from utils.validation import TestSuite
from utils.archivoLogs import discovery_logger, diff_logger
from datetime import datetime




cron = BackgroundScheduler(daemon=True)
# Explicitly kick off the background thread
cron.start()

indexFilePath = os.path.join(os.path.split(app.instance_path)[0], "indices", "vocab_index.json")
falloutFilePath = os.path.join(os.path.split(app.instance_path)[0], "indices", "fallout_index.csv")


# This is the discovery process
#@cron.scheduled_job("cron", id="archivo_ontology_discovery", hour="1", day_of_week="sun")
def ontology_discovery():
    # init parameters
    dataPath = archivoConfig.localPath


    testSuite = TestSuite(os.path.join(os.path.split(app.instance_path)[0]))
    # load the other sources
    hashUris = ontoFiles.loadListFile(archivoConfig.hashUriPath)

    prefixUris = ontoFiles.secondColumnOfTSV(archivoConfig.prefixUrisPath)

    for uri in crawlURIs.getLovUrls():
        crawlURIs.handleNewUri(uri, ontoIndex, dataPath, fallout, "LOV", False, testSuite=testSuite, logger=discovery_logger)
        ontoFiles.writeIndexJsonToFile(ontoIndex, indexFilePath)
        ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)

    for uri in hashUris:
        crawlURIs.handleNewUri(uri, ontoIndex, dataPath, fallout, "spoHashUris", False, testSuite=testSuite, logger=discovery_logger)
        ontoFiles.writeIndexJsonToFile(ontoIndex, indexFilePath)
        ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)

    for uri in prefixUris:
        crawlURIs.handleNewUri(uri, ontoIndex, dataPath, fallout, "prefix.cc", False, testSuite=testSuite, logger=discovery_logger)
        ontoFiles.writeIndexJsonToFile(ontoIndex, indexFilePath)
        ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)

    #for uri in getVoidUris(voidPath):
        #crawlURIs.handleNewUri(uri, index, dataPath, fallout, "voidUris", False, testSuite=testSuite)
        #ontoFiles.writeIndexJsonToFile(index, indexFilePath)
        #ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)


@cron.scheduled_job("cron", id="archivo_ontology_update", hour="2,10,18", day_of_week="mon-sun")
def ontology_update():
    index = ontoFiles.loadIndexJsonFromFile(indexFilePath)
    fallout = ontoFiles.loadFalloutIndexFromFile(falloutFilePath)
    dataPath = archivoConfig.localPath
    allOntologiesInfo = queryDatabus.latestOriginalOntlogies()
    diff_logger.info("Started diff at "+datetime.now().strftime("%Y.%m.%d; %H:%M:%S"))
    testSuite = TestSuite(os.path.join(os.path.split(app.instance_path)[0]))
    for uri in index:
        source = index[uri]["source"]
        diff_logger.info(f"Handling ontology: {uri}")
        group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
        databusURL = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        try:
            urlInfo = allOntologiesInfo[databusURL]
        except KeyError:
            diff_logger.error(f"Could't find databus artifact for {uri}")
            continue
        diffOntologies.handleDiffForUri(uri, dataPath, urlInfo["meta"], urlInfo["origFile"], urlInfo["version"], fallout, testSuite, source)
        ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)


# Shutdown your cron thread if the web process is stopped
atexit.register(lambda: cron.shutdown(wait=False))

if __name__ == "__main__":
    app.run(debug=False)