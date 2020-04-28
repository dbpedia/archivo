import sys
import ontoFiles
import diffOntologies

rootdir = sys.argv[1]

localDiffDir = ".tmpDiffDir"

fallout_index = ontoFiles.loadFalloutIndex()

index = ontoFiles.loadSimpleIndex()

for uri in index:
    diffOntologies.handleDiffForUri(uri, rootdir, fallout_index)
    ontoFiles.writeFalloutIndex(fallout_index)