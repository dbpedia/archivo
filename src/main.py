import inspectVocabs
import generatePoms
import sys
import os
import crawlURIs
from datetime import datetime
from dateutil.parser import parse as parsedate
import ontoFiles
import random


def checkIndexForUri(uri, index):
    for indexUri in index:
        if crawlURIs.checkUriEquality(uri, index):
            return True
    return False


rootdir=sys.argv[1]

index = ontoFiles.loadIndexJson()
new_uris = [] 

fallout = ontoFiles.loadFalloutIndex()

hashUris = ontoFiles.loadListFile("src/all_hash_uris.lst")

prefixUris = ontoFiles.readTsvFile("src/prefixCC-uris.tsv")

for uri in crawlURIs.getLovUrls():
    if not checkIndexForUri(uri, index):
        crawlURIs.handleNewUri(uri, index, rootdir, fallout, "LOV", False)

#for i in range(20):
    #uri = random.choice(potentialUris)
    #while uri in new_uris:
        #uri = random.choice(potentialUris)
    #new_uris.append(uri)

for uri in hashUris:
    if not checkIndexForUri(uri, index):
        crawlURIs.handleNewUri(uri, index, rootdir, fallout, "spoHashUris", False)

for uri in prefixUris:
    if not checkIndexForUri(uri, index):
        crawlURIs.handleNewUri(uri, index, rootdir, fallout, "prefix.cc", False)
