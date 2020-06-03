import sys
import os
from datetime import datetime
from dateutil.parser import parse as parsedate
import random
import rdflib
import crawlURIs
from utils import ontoFiles, generatePoms, inspectVocabs
import archivoConfig
from utils import TestSuite


def checkIndexForUri(uri, index):
    for indexUri in index:
        if crawlURIs.checkUriEquality(uri, indexUri):
            return True
    return False


def getVoidUris(datapath):

    resultSet = set()
    for dirpath, dirname, filenames in os.walk(datapath):
        for filename in filenames:
            if filename.endswith(".ttl"):
                print("Handling file: ", os.path.join(dirpath, filename))
                dataGraph = inspectVocabs.getGraphOfVocabFile(os.path.join(dirpath, filename))
                print("Triples:", len(dataGraph))
                classUris = inspectVocabs.getAllPropsAndClasses(dataGraph)
                print("Done, appending to list...")
                for uri in classUris:
                    resultSet.add(uri)
    return resultSet
 
rootdir=sys.argv[1]

index = ontoFiles.loadIndexJson()
new_uris = [] 

fallout = ontoFiles.loadFalloutIndex()

#hashUris = ontoFiles.loadListFile("src/all_hash_uris.lst")

#prefixUris = ontoFiles.readTsvFile("src/prefixCC-uris.tsv")

voidClasses = getVoidUris(archivoConfig.voidResults)

testSuite = TestSuite(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "shacl"))

with open("./void-classes.txt", "w+") as classesFile:
    print("\n".join(voidClasses), file=classesFile)

print(len(voidClasses))

sys.exit(0)

for uri in crawlURIs.getLovUrls():
    if not checkIndexForUri(uri, index):
        crawlURIs.handleNewUri(uri, index, rootdir, fallout, "LOV", False, testSuite=testSuite)

#for i in range(20):
    #uri = random.choice(potentialUris)
    #while uri in new_uris:
        #uri = random.choice(potentialUris)
    #new_uris.append(uri)

#for uri in hashUris:
    #if not checkIndexForUri(uri, index):
        #crawlURIs.handleNewUri(uri, index, rootdir, fallout, "spoHashUris", False)

#for uri in prefixUris:
    #if not checkIndexForUri(uri, index):
        #crawlURIs.handleNewUri(uri, index, rootdir, fallout, "prefix.cc", False)

generatePoms.updateParentPoms(rootdir, index)
