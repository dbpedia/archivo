import requests
import re
import os
import sys
from datetime import datetime
from dateutil.parser import parse as parsedate
import ontoFiles
import validation
import inspectVocabs
import generatePoms
import stringTools

# docu for failed ontologies
failedGroupDoc = (f"#This group is for all unavailable ontologies\n\n"
                "All the artifacts in this group refer to one vocabulary.\n"
                "The ontologies are part of the Databus Archivo - A Web-Scale Ontology Interface for Time-Based and Semantic Archiving and Developing Good Ontologies.")

# explaination for the md-File
explaination="This ontology is part of the Databus Archivo - A Web-Scale OntologyInterface for Time-Based and SemanticArchiving and Developing Good Ontologies"

# url to get all vocabs and their resource
lovOntologiesURL="https://lov.linkeddata.es/dataset/lov/api/v2/vocabulary/list"

# url for the lodo docu service
lodeServiceUrl="https://w3id.org/lode/"

# url for the oops rest service
oopsServiceUrl=" http://oops.linkeddata.es/rest"

# possible headers for rdf-data
rdfHeaders=["application/rdf+xml", "application/ntriples", "text/turtle", "text/rdf+n3", "application/html"]

def getLodeDocuFile(vocab_uri):
  print("Generating lode-docu...")
  try:
    response = requests.get(lodeServiceUrl + vocab_uri)
    if response.status_code < 400:
      return response.text
    else:
      return None
  except requests.exceptions.TooManyRedirects:
        print("Too many redirects, cancel parsing...")
        return None
  except TimeoutError:
        print("Timed out during parsing: "+vocab_uri)
        return None
  except requests.exceptions.ConnectionError:
        print("Bad Connection "+ vocab_uri)
        return None
  except requests.exceptions.ReadTimeout:
        print("Connection timed out for URI ", vocab_uri)
        return None

def getOOPSReport(parsedRdfString):
  print("Generating OOPS report...")
  oopsXml=(
          "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
          "   <OOPSRequest>\n"
	        "   <OntologyURI></OntologyURI>\n"
	        f"    <OntologyContent><![CDATA[\n{parsedRdfString}]]></OntologyContent>\n"
	        "   <Pitfalls></Pitfalls>\n"
	        "   <OutputFormat>RDF/XML</OutputFormat>\n"
          "</OOPSRequest>"
          )
  headers = {'Content-Type': 'application/xml'}
  try:
    response = requests.post(oopsServiceUrl, data=oopsXml, headers=headers, timeout=30)
    if response.status_code < 400:
      return response.text
    else:
      print("Bad Connection: Status", response.status_code)
      return None
  except:
    print("Something went wrong generating the OOPS-report")
    return None


def determineBestAccHeader(vocab_uri):
  localTestDir = "./.tmpTestTriples"
  if not os.path.isdir(localTestDir):
    os.mkdir(localTestDir)
  print("Determining the best header for this vocabulary...")
  headerDict = {}
  os.makedirs(localTestDir, exist_ok=True)
  for header in rdfHeaders:
    success, filePath = downloadSource(vocab_uri, localTestDir, "testTriples", header)[:2]
    if success:
      tripleNumber = ontoFiles.getParsedTriples(filePath)
      if tripleNumber != None:
        headerDict[header] = tripleNumber
        print("Accept-Header: ",header,"; TripleNumber: ",tripleNumber)
  generatedFiles = [f for f in os.listdir(localTestDir) if os.path.isfile(localTestDir + os.sep + f)]
  for filename in generatedFiles:
    os.remove(os.path.join(localTestDir, filename))
  # return the header with the most triples
  if headerDict == {}:
    return None
  else:
    return [k for k, v in sorted(headerDict.items(), key=lambda item: item[1], reverse=True)][0]


def downloadSource(uri, path, name, accHeader):
  try:
    acc_header = {'Accept': accHeader}
    response=requests.get(uri, headers=acc_header, timeout=30, allow_redirects=True)    
    fileEnding = stringTools.getFileEnding(response)
    filePath = path + os.sep + name +"_type=orig"+ fileEnding
    if response.status_code < 400:
      with open(filePath, "w+") as ontfile:
        print(response.text, file=ontfile)
      return True, filePath, response
    else:
      return False, filePath, response
  except requests.exceptions.TooManyRedirects:
    print("Too many redirects, cancel parsing...")
    return False, "", None
  except TimeoutError:
    print("Timed out during parsing: "+uri)
    return False, "", None
  except requests.exceptions.ConnectionError:
    print("Bad Connection "+ uri)
    return False, "", None
  except requests.exceptions.ReadTimeout:
    print("Connection timed out for URI ", uri)
    return False, "", None


  

def generateNewRelease(vocab_uri, filePath, artifact, pathToOrigFile, bestHeader, response, accessDate):
  artifactPath, version = os.path.split(filePath)
  groupPath = os.path.split(artifactPath)[0]
  groupId = os.path.split(groupPath)[1]
  if len(response.history) > 0:
    nirHeader = str(response.history[0].headers)
  else:
    nirHeader = ""
  # generate parsed variants of the ontology
  rapperErrors, rapperWarnings=ontoFiles.parseRDFSource(pathToOrigFile, os.path.join(filePath, artifact+"_type=parsed.ttl"), outputType="turtle", deleteEmpty=True, sourceUri=vocab_uri)
  ontoFiles.parseRDFSource(pathToOrigFile, os.path.join(filePath, artifact+"_type=parsed.nt"), outputType="ntriples", deleteEmpty=True, sourceUri=vocab_uri)
  triples = ontoFiles.getParsedTriples(pathToOrigFile)
  if triples == None:
    triples = 0
  # shacl-validation
  # uses the turtle file since there were some problems with the blankNodes of rapper and rdflib
  # no empty parsed files since shacl is valid on empty files.
  if os.path.isfile(os.path.join(filePath, artifact+"_type=parsed.ttl")):
    ontoGraph = inspectVocabs.getGraphOfVocabFile(os.path.join(filePath, artifact+"_type=parsed.ttl"))
    conforms, reportGraph, reportText = validation.licenseValidation(ontoGraph)
    print(reportText)
    validation.printGraphToTurtleFile(reportGraph, os.path.join(filePath, artifact+"_type=shaclReport.ttl"))
  else:
    print("No valid syntax, no shacl report")
    conforms = False
    ontoGraph = None
  # write the metadata json file
  ontoFiles.writeVocabInformation(pathToFile=os.path.join(filePath, artifact+"_type=meta.json"),
                                  definedByUri=vocab_uri,
                                  lastModified=stringTools.getLastModifiedFromResponse(response),
                                  rapperErrors=rapperErrors,
                                  rapperWarnings=rapperWarnings,
                                  etag=stringTools.getEtagFromResponse(response),
                                  tripleSize=triples,
                                  bestHeader=bestHeader,
                                  shaclValidated=conforms,
                                  accessed= accessDate,
                                  headerString=str(response.headers),
                                  nirHeader = nirHeader,
                                  contentLenght=stringTools.getContentLengthFromResponse(response)
                                  )
  if triples > 0:                                                                
    docustring = getLodeDocuFile(vocab_uri)
    with open(filePath + os.sep + artifact + "_type=generatedDocu.html", "w+") as docufile:
      print(docustring, file=docufile)
    oopsReport = getOOPSReport(ontoFiles.getParsedRdf(pathToOrigFile))
    if oopsReport != None:
      with open(os.path.join(filePath, artifact + "_type=OOPS.rdf"), "w+") as oopsFile:
        print(oopsReport, file=oopsFile)
  generatePomAndMdFile(os.path.split(filePath)[0], groupId, artifact, version, ontoGraph)

def generatePomAndMdFile(artifactPath, groupId, artifact, version, ontograph):
  md_label=artifact + " ontology"
  md_description=""
  license=None
  if ontograph != None:
    labelList = inspectVocabs.getPossibleLabels(ontograph)
    descriptionList = inspectVocabs.getPossibleDescriptions(ontograph)
    if labelList != None:
      possibleLabels = [label for label in labelList if label != None]
    else:
      possibleLabels = []

    if descriptionList != None:
      possibleDescriptions = [desc for desc in descriptionList if desc != None]
    else:
      possibleDescriptions = []
    license =inspectVocabs.getLicense(ontograph)
    if possibleLabels != [] and len(possibleLabels) > 0:
      md_label = possibleLabels[0]
    if possibleDescriptions != [] and len(possibleDescriptions) > 0:
      md_description = possibleDescriptions[0]  
  childpomString = generatePoms.generateChildPom(groupId=groupId,
                                                  version=version,
                                                  artifactId=artifact,
                                                  packaging="jar",
                                                  license=license)
  with open(os.path.join(artifactPath, "pom.xml"), "w+") as childPomFile:
    print(childpomString, file=childPomFile)
  generatePoms.writeMarkdownDescription(artifactPath, artifact, md_label, explaination, md_description)
    


def handleNewUri(vocab_uri, index, dataPath, fallout_index):
  localDir = os.path.join(dataPath, ".tmpOntTest")
  if not os.path.isdir(localDir):
    os.mkdir(localDir)

  print("Trying to validate ", vocab_uri)
  if vocab_uri in index:
    print("Already known uri, skipping...")
    return
  bestHeader  = determineBestAccHeader(vocab_uri)
  groupId, artifact = stringTools.generateGroupAndArtifactFromUri(vocab_uri)
  version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
  if bestHeader == None:
    print("No header, probably server down")
    fallout_index.append((vocab_uri, False, "not reachable server"))
    stringTools.deleteAllFilesInDir(localDir)
    return
  accessDate = datetime.now().strftime("%Y.%m.%d; %H:%M:%S")
  success, pathToFile, response = downloadSource(vocab_uri, localDir, "tempOnt", bestHeader)
  if not success:
    print("No available Source")
    fallout_index.append((vocab_uri, False, "not reachable server"))
    stringTools.deleteAllFilesInDir(localDir)
    return
  ontoFiles.parseRDFSource(pathToFile, os.path.join(localDir, "parsedSource.ttl"), "turtle", deleteEmpty=True, silent=True, sourceUri=vocab_uri)
  if not os.path.isfile(os.path.join(localDir, "parsedSource.ttl")):
    print("Unparseable ontology")
    fallout_index.append((vocab_uri, False, "Unparseable source"))
    stringTools.deleteAllFilesInDir(localDir)
    return
  graph = inspectVocabs.getGraphOfVocabFile(os.path.join(localDir, "parsedSource.ttl"))
  real_ont_uri=inspectVocabs.getNIRUri(graph)
  if real_ont_uri == None:
    real_ont_uri = inspectVocabs.getDefinedByUri(graph)
    if real_ont_uri == None:
      fallout_index.append((vocab_uri, False, "No ontology"))
      print("Neither ontology nor class")
      stringTools.deleteAllFilesInDir(localDir)
      return
    if not real_ont_uri in index:
      bestHeader = determineBestAccHeader(real_ont_uri)
      if not vocab_uri == real_ont_uri:
        stringTools.deleteAllFilesInDir(localDir)
        handleNewUri(real_ont_uri, index, dataPath, fallout_index)
      return

  
  if real_ont_uri in index:
    print("Already known uri", real_ont_uri)
    return
  
  
  print("Real Uri:", real_ont_uri)
  groupId, artifact = stringTools.generateGroupAndArtifactFromUri(real_ont_uri)
  if groupId == None or artifact == None:
    print("Malformed non-information Uri", real_ont_uri)
    fallout_index.append((real_ont_uri, False, "Malformed non-information uri"))
    return
  index.append(real_ont_uri)
  newVersionPath=os.path.join(dataPath, groupId, artifact, version)
  os.makedirs(newVersionPath, exist_ok=True)
  if not os.path.isfile(os.path.join(dataPath, groupId, "pom.xml")):
    groupDoc=(f"#This group is for all vocabularies hosted on {groupId}\n\n"
            "All the artifacts in this group refer to one vocabulary, deployed in different formats.\n"
            "The ontologies are part of the Databus Archivo - A Web-Scale Ontology Interface for Time-Based and Semantic Archiving and Developing Good Ontologies.")
 
    pomString=generatePoms.generateParentPom(groupId=groupId,
                                            packaging="pom",
                                            modules=[],
                                            packageDirectory=generatePoms.packDir,
                                            downloadUrlPath=generatePoms.downloadUrl,
                                            publisher=generatePoms.pub,
                                            maintainer=generatePoms.pub,
                                            groupdocu=groupDoc,
                                            )
    with open(os.path.join(dataPath, groupId, "pom.xml"), "w+") as parentPomFile:
      print(pomString, file=parentPomFile)
  fileExt = os.path.splitext(pathToFile)[1]
  os.rename(pathToFile, os.path.join(newVersionPath, artifact+"_type=orig" + fileExt))
  generateNewRelease(real_ont_uri, newVersionPath, artifact, os.path.join(newVersionPath, artifact+"_type=orig" + fileExt), bestHeader, response, accessDate)
  ontoFiles.writeFalloutIndex(fallout_index)
  ontoFiles.writeSimpleIndex(index)
  stringTools.deleteAllFilesInDir(localDir)


def getLovUrls():
  req = requests.get(lovOntologiesURL)
  json_data=req.json()
  return [dataObj["uri"] for dataObj in json_data]
