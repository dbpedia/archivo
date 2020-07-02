import sys
import os
from datetime import datetime
from dateutil.parser import parse as parsedate
import random
import rdflib
import crawlURIs
from utils import ontoFiles, generatePoms, inspectVocabs, archivoConfig, stringTools, queryDatabus
from utils.validation import TestSuite
import json
import shutil
from urllib.parse import urldefrag



def crawlNewOntologies(hashUris, prefixUris, voidPath, testSuite, indexFilePath, falloutFilePath):
    index = ontoFiles.loadIndexJsonFromFile(indexFilePath)
    fallout = ontoFiles.loadFalloutIndexFromFile(falloutFilePath)
    for uri in crawlURIs.getLovUrls():
        crawlURIs.handleNewUri(uri, index, rootdir, fallout, "LOV", False, testSuite=testSuite)
        ontoFiles.writeIndexJsonToFile(index, indexFilePath)
        ontoFiles.writeFalloutIndexToFile(fallout, falloutFilePath)

    for uri in hashUris:
        crawlURIs.handleNewUri(uri, index, rootdir, fallout, "spoHashUris", False, testSuite=testSuite)
        ontoFiles.writeIndexJsonToFile(index, indexFilePath)
        ontoFiles.writeFalloutIndexToFile(fallout, falloutFilePath)

    for uri in prefixUris:
        crawlURIs.handleNewUri(uri, index, rootdir, fallout, "prefix.cc", False, testSuite=testSuite)
        ontoFiles.writeIndexJsonToFile(index, indexFilePath)
        ontoFiles.writeFalloutIndexToFile(fallout, falloutFilePath)

    #for uri in getVoidUris(voidPath):
        #crawlURIs.handleNewUri(uri, index, rootdir, fallout, "voidUris", False, testSuite=testSuite)
        #ontoFiles.writeIndexJsonToFile(index, indexFilePath)
        #ontoFiles.writeFalloutIndexToFile(fallout, falloutFilePath)

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

def checkDatabusIndexReleases(index):
    for uri in index:
        group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
        success, databusLink, databusVersionUri,  metadata = queryDatabus.getLatestMetaFile(group, artifact)
        if success:
            try:
                print("Found latest release:")
                print(databusLink)
                print(metadata["http-data"]["accessed"])
            except KeyError:
                print("No current data for:", uri)
        else:
            print("No data found for:", uri)


def updateIndex(index, dataPath, newPath,testSuite):
    for uri in index:
        group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
        oldArtifactDir = os.path.join(dataPath, group, artifact)
        newGroupDir = os.path.join(newPath, group)
        newArtifactDir = os.path.join(newPath, group, artifact)
        if not os.path.isdir(oldArtifactDir):
            print(f"No data for {uri}")
            continue
        if os.path.isfile(os.path.join(newArtifactDir, "pom.xml")):
            print("Already Updated:", uri)
        latestVersionDir = ontoFiles.getLatestVersionFromArtifactDir(oldArtifactDir)
        originalFile = [f for f in os.listdir(latestVersionDir) if "_type=orig" in f][0]
        with open(os.path.join(latestVersionDir, artifact + "_type=meta.json"), "r")as jsonFile:
            metadata = json.load(jsonFile)
        version = os.path.split(latestVersionDir)[1]
        updatedVersionDir = os.path.join(newArtifactDir, version)
        os.makedirs(updatedVersionDir, exist_ok=True)
        fileExt = os.path.splitext(originalFile)[1]
        shutil.copyfile(os.path.join(latestVersionDir, originalFile), os.path.join(updatedVersionDir, artifact+"_type=orig" + fileExt))
        if not os.path.isfile(os.path.join(updatedVersionDir, artifact+"_type=orig" + fileExt)):
            print("Copy doesnt work")
            sys.exit(1)

        print(os.path.join(newGroupDir, "pom.xml"))
        if not os.path.isfile(os.path.join(newGroupDir, "pom.xml")):
            pomString=generatePoms.generateParentPom(groupId=group,
                                            packaging="pom",
                                            modules=[],
                                            packageDirectory=archivoConfig.packDir,
                                            downloadUrlPath=archivoConfig.downloadUrl,
                                            publisher=archivoConfig.pub,
                                            maintainer=archivoConfig.pub,
                                            groupdocu=archivoConfig.groupDoc.format(group),
                                            )
            with open(os.path.join(newGroupDir, "pom.xml"), "w+") as parentPomFile:
                print(pomString, file=parentPomFile)
        crawlURIs.updateFromOldFile(uri, updatedVersionDir, artifact, os.path.join(updatedVersionDir, artifact+"_type=orig" + fileExt), metadata["http-data"]["best-header"], metadata, metadata["http-data"]["accessed"], testSuite, "1.0.0")






rootdir=sys.argv[1]

index = ontoFiles.loadIndexJson()
new_uris = [] 

newDir = sys.argv[2]

fallout = ontoFiles.loadFalloutIndex()

#checkDatabusIndexReleases(index)

#voidClasses = getVoidUris(archivoConfig.voidResults)

testSuite = TestSuite(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "shacl"))

updateIndex(index, rootdir, newDir,testSuite)

#for i in range(20):
    #uri = random.choice(potentialUris)
    #while uri in new_uris:
        #uri = random.choice(potentialUris)
    #new_uris.append(uri)



generatePoms.updateParentPoms(newDir, index)
