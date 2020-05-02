import sys
import ontoFiles
import diffOntologies
from datetime import datetime

rootdir = sys.argv[1]

localDiffDir = ".tmpDiffDir"

fallout_index = ontoFiles.loadFalloutIndex()

index = ontoFiles.loadSimpleIndex()

print("Started diff at", datetime.now().strftime("%Y.%m.%d; %H:%M:%S"))

for uri in index:
    diffOntologies.handleDiffForUri(uri, rootdir, fallout_index)
    ontoFiles.writeFalloutIndex(fallout_index)