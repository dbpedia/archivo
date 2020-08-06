import sys
import os
import diffOntologies
from utils import ontoFiles, queryDatabus, stringTools
from datetime import datetime
from utils.validation import TestSuite
from utils.archivoLogs import diff_logger

rootdir = sys.argv[1]

localDiffDir = ".tmpDiffDir"

fallout_index = ontoFiles.loadFalloutIndex()

index = ontoFiles.loadIndexJson()

print("Started diff at", datetime.now().strftime("%Y.%m.%d; %H:%M:%S"))
testSuite = TestSuite(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "shacl"))

allOntologiesInfo = queryDatabus.latestOriginalOntlogies()
if allOntologiesInfo == None:
    diff_logger.error("Problem loading most recent data from the Databus")
    exit(1)
    
for uri in ["http://ldf.fi/void-ext"]:
    diff_logger.info(f"Handling ontology: {uri}")
    group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
    databusURL = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
    try:
        urlInfo = allOntologiesInfo[databusURL]
    except KeyError:
        diff_logger.error(f"Could't find databus artifact for {uri}")
        continue
    diffOntologies.handleDiffForUri(uri, rootdir, urlInfo["meta"], urlInfo["origFile"], urlInfo["version"], fallout_index, testSuite)
    ontoFiles.writeFalloutIndex(fallout_index)