import sys
import os
import diffOntologies
from utils import ontoFiles
from datetime import datetime
from utils.validation import TestSuite

rootdir = sys.argv[1]

localDiffDir = ".tmpDiffDir"

fallout_index = ontoFiles.loadFalloutIndex()

index = ontoFiles.loadIndexJson()

print("Started diff at", datetime.now().strftime("%Y.%m.%d; %H:%M:%S"))
testSuite = TestSuite(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "shacl"))

for uri in index:
    print("Handling ontology:", uri)
    diffOntologies.handleDiffForUri(uri, rootdir, fallout_index, testSuite)
    ontoFiles.writeFalloutIndex(fallout_index)