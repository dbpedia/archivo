import sys
import os
from datetime import datetime
from dateutil.parser import parse as parsedate
import random
import rdflib
import crawlURIs
from utils import ontoFiles, generatePoms, inspectVocabs, archivoConfig, stringTools, queryDatabus, docTemplates
from utils.validation import TestSuite
import json
import shutil
from urllib.parse import urldefrag
from string import Template
import pyshacl


def crawlNewOntologies(hashUris, prefixUris, voidPath, testSuite, indexFilePath, falloutFilePath):
    index = ontoFiles.loadIndexJsonFromFile(indexFilePath)
    fallout = ontoFiles.loadFalloutIndexFromFile(falloutFilePath)
    for uri in crawlURIs.getLovUrls():
        crawlURIs.handleNewUri(uri, index, rootdir, fallout, "LOV", False, testSuite=testSuite)
        ontoFiles.writeIndexJsonToFile(index, indexFilePath)
        ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)

    for uri in hashUris:
        crawlURIs.handleNewUri(uri, index, rootdir, fallout, "spoHashUris", False, testSuite=testSuite)
        ontoFiles.writeIndexJsonToFile(index, indexFilePath)
        ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)

    for uri in prefixUris:
        crawlURIs.handleNewUri(uri, index, rootdir, fallout, "prefix.cc", False, testSuite=testSuite)
        ontoFiles.writeIndexJsonToFile(index, indexFilePath)
        ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)

    #for uri in getVoidUris(voidPath):
        #crawlURIs.handleNewUri(uri, index, rootdir, fallout, "voidUris", False, testSuite=testSuite)
        #ontoFiles.writeIndexJsonToFile(index, indexFilePath)
        #ontoFiles.writeFalloutIndexToFile(falloutFilePath, fallout)

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
            continue
        latestVersionDir = ontoFiles.getLatestVersionFromArtifactDir(oldArtifactDir)
        originalFile = [f for f in os.listdir(latestVersionDir) if "_type=orig" in f][0]
        with open(os.path.join(latestVersionDir, artifact + "_type=meta.json"), "r")as jsonFile:
            metadata = json.load(jsonFile)
        version = os.path.split(latestVersionDir)[1]
        updatedVersionDir = os.path.join(newArtifactDir, version)
        os.makedirs(updatedVersionDir, exist_ok=True)
        fileExt = os.path.splitext(originalFile)[1]
        shutil.copyfile(os.path.join(latestVersionDir, originalFile), os.path.join(updatedVersionDir, artifact+"_type=orig" + fileExt))
        if os.path.isfile(os.path.join(latestVersionDir, artifact + "_type=OOPS.rdf")):
            print("Copy OOPS report...")
            shutil.copyfile(os.path.join(latestVersionDir, artifact + "_type=OOPS.rdf"), os.path.join(updatedVersionDir, artifact + "_type=OOPS.rdf"))
        if os.path.isfile(os.path.join(latestVersionDir, artifact + "_type=generatedDocu.html")):
            print("Copy docu..")
            shutil.copyfile(os.path.join(latestVersionDir, artifact + "_type=generatedDocu.html"), os.path.join(updatedVersionDir, artifact + "_type=generatedDocu.html"))
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
                                            groupdocu=Template(docTemplates.groupDoc).safe_substitute(groupid=group),
                                            )
            with open(os.path.join(newGroupDir, "pom.xml"), "w+") as parentPomFile:
                print(pomString, file=parentPomFile)
        crawlURIs.updateFromOldFile(urldefrag(uri)[0], updatedVersionDir, artifact, os.path.join(updatedVersionDir, artifact+"_type=orig" + fileExt), metadata["http-data"]["best-header"], metadata, metadata["http-data"]["accessed"], testSuite, "1.0.0")

def checkAllLicenses(dataPath, index):
    resultDict={"None": 0, "Error":0, "Literal":0}
    for uri in index:
        group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
        oldArtifactDir = os.path.join(dataPath, group, artifact)
        if not os.path.isdir(oldArtifactDir):
            print("ERROR: Couldn't find artifact for", uri)
            resultDict["Error"] = resultDict["Error"] + 1
            continue
        latestVersionDir = ontoFiles.getLatestVersionFromArtifactDir(oldArtifactDir)
        parsedFile = os.path.join(latestVersionDir, artifact + "_type=parsed.ttl")
        
        graph = inspectVocabs.getGraphOfVocabFile(parsedFile)
        license = inspectVocabs.getLicense(graph)
        if license == None:
            resultDict["None"] = resultDict["None"] + 1
        elif type(license) == rdflib.Literal:
            resultDict["Literal"] = resultDict["Literal"] + 1
        elif str(license) in resultDict:
            resultDict[str(license)] = resultDict[str(license)] + 1
        else:
            resultDict[str(license)] = 1

    return json.dumps(resultDict, indent=4, sort_keys=True)


def checkLOVOntologies(dataPath):
    resultDict = {"No RDF available":0, "RDF available":0}
    lov_uris = crawlURIs.getLovUrls()
    for uri in lov_uris:
        bestHeader, errors = crawlURIs.determineBestAccHeader(uri, dataPath)
        if bestHeader == None:
            resultDict["No RDF available"] = resultDict["No RDF available"] + 1
        else:
            resultDict["RDF available"] = resultDict["RDF available"] + 1

    return json.dumps(resultDict, indent=4, sort_keys=True)



def checkAllRobots(index):
    for uri in index:
        isCrawlable, problem = crawlURIs.checkRobot(uri)
        if not isCrawlable:
            print("Uncrawlable uri ", uri, "Problem:", problem)

def interpretIndex(index):
    resultDict = {}
    for uri in index:
        source = index[uri]["source"]
        if not source in resultDict.keys():
            resultDict[source] = 1
        else:
            resultDict[source] = resultDict[source] + 1
    print(json.dumps(resultDict, indent=4, sort_keys=True))


rootdir=sys.argv[1]

index = ontoFiles.loadIndexJson()
new_uris = [] 

#newDir = sys.argv[2]

fallout = ontoFiles.loadFalloutIndex()

relativeUrls = [
    "http://datos.bcn.cl/ontologies/bcn-geographics#GeographicOntology",
    "http://purl.org/crmeh#CRMEH",
    "http://semweb.mmlab.be/ns/dicera#ontology",
    "http://semweb.mmlab.be/ns/linkedconnections#Ontology",
    "http://semweb.mmlab.be/ns/stoptimes#Ontology",
    "http://www.ebusiness-unibw.org/ontologies/hva/ontology#Ontology",
    "https://w3id.org/opentrafficlights#Ontology",
    "https://w3id.org/tree#Ontology"
]

#checkDatabusIndexReleases(index)

#voidClasses = getVoidUris(archivoConfig.voidResults)

testSuite = TestSuite(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "shacl"))

#updateIndex(relativeUrls, rootdir, newDir,testSuite)

interpretIndex(index)

#print(checkAllLicenses(rootdir, index))

#ontoFiles.genStats(rootdir)

#crawlNewOntologies(hashUris=hashUris, prefixUris=prefixUris, voidPath="", testSuite=testSuite, indexFilePath=archivoConfig.ontoIndexPath, falloutFilePath=archivoConfig.falloutIndexPath)
#checkAllRobots(index)
#for i in range(20):
    #uri = random.choice(potentialUris)
    #while uri in new_uris:
        #uri = random.choice(potentialUris)
    #new_uris.append(uri)



#generatePoms.updateParentPoms(newDir, index)
