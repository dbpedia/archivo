from webservice import app

from apscheduler.scheduler import Scheduler
import atexit, os, crawlURIs, diffOntologies
from utils import ontoFiles, archivoConfig
from utils.validation import TestSuite
from utils.archivoLogs import discovery_logger




cron = Scheduler(daemon=True)
# Explicitly kick off the background thread
cron.start()

indexFilePath = os.path.join(os.path.split(app.instance_path)[0], "indices", "vocab_index.json")
falloutFilePath = os.path.join(os.path.split(app.instance_path)[0], "indices", "fallout_index.csv")
testSuite = TestSuite(os.path.join(os.path.split(app.instance_path)[0], "shacl"))

# This is the discovery process
@cron.scheduled_job("cron", id="archivo_ontology_discovery", hours="1", day_of_week="sun")
def ontology_discovery():
    # init parameters
    dataPath = archivoConfig.localPath
    index = ontoFiles.loadIndexJsonFromFile(indexFilePath)
    fallout = ontoFiles.loadFalloutIndexFromFile(falloutFilePath)

    # load the other sources
    hashUris = ontoFiles.loadListFile(archivoConfig.hashUriPath)

    prefixUris = ontoFiles.secondColumnOfTSV(archivoConfig.prefixUrisPath)

    for uri in crawlURIs.getLovUrls():
        crawlURIs.handleNewUri(uri, index, dataPath, fallout, "LOV", False, testSuite=testSuite, logger=discovery_logger)
        ontoFiles.writeIndexJsonToFile(index, indexFilePath)
        ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)

    for uri in hashUris:
        crawlURIs.handleNewUri(uri, index, dataPath, fallout, "spoHashUris", False, testSuite=testSuite, logger=discovery_logger)
        ontoFiles.writeIndexJsonToFile(index, indexFilePath)
        ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)

    for uri in prefixUris:
        crawlURIs.handleNewUri(uri, index, dataPath, fallout, "prefix.cc", False, testSuite=testSuite, logger=discovery_logger)
        ontoFiles.writeIndexJsonToFile(index, indexFilePath)
        ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)

    #for uri in getVoidUris(voidPath):
        #crawlURIs.handleNewUri(uri, index, dataPath, fallout, "voidUris", False, testSuite=testSuite)
        #ontoFiles.writeIndexJsonToFile(index, indexFilePath)
        #ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)


@cron.interval_schedule("cron", id="archivo_ontology_update", hours="2,10,18", day_of_week="mon-sat")
def ontology_update():
    index = ontoFiles.loadIndexJsonFromFile(indexFilePath)
    fallout = ontoFiles.loadFalloutIndexFromFile(falloutFilePath)
    dataPath = archivoConfig.localPath
    for uri in index:
        diffOntologies.handleDiffForUri(uri, dataPath, fallout, testSuite)
        ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)


# Shutdown your cron thread if the web process is stopped
atexit.register(lambda: cron.shutdown(wait=False))


if __name__ == "__main__":
    app.run(debug=True)