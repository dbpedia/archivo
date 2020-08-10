import sys
import os
from datetime import datetime
from dateutil.parser import parse as parsedate
import random
import rdflib
import crawlURIs
from utils import ontoFiles, generatePoms, inspectVocabs, archivoConfig, stringTools, queryDatabus
from utils.validation import TestSuite
from utils.archivoLogs import discovery_logger



def crawlNewOntologies(dataPath, hashUris, prefixUris, voidPath, testSuite, indexFilePath, falloutFilePath):
    index = ontoFiles.loadIndexJsonFromFile(indexFilePath)
    fallout = ontoFiles.loadFalloutIndexFromFile(falloutFilePath)
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


rootdir=sys.argv[1]

index = ontoFiles.loadIndexJson()

fallout = ontoFiles.loadFalloutIndex()

testSuite = TestSuite(os.path.abspath(os.path.dirname(sys.argv[0])))

hashUris = ontoFiles.loadListFile("/home/denis/all_hash_uris.lst")

prefixUris = ontoFiles.secondColumnOfTSV("/home/denis/prefix-cc-uris.tsv")

crawlNewOntologies(dataPath=rootdir, hashUris=hashUris, prefixUris=prefixUris, voidPath="", testSuite=testSuite, indexFilePath=archivoConfig.ontoIndexPath, falloutFilePath=archivoConfig.falloutIndexPath)
