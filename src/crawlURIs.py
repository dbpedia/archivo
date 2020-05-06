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
lodeServiceUrl="https://w3id.org/lode/owlapi/"

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

  

def generateNewRelease(vocab_uri, filePath, artifact, pathToOrigFile, bestHeader, response, accessDate, semVersion="0.0.1"):
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
    parseable = True
    ontoGraph = inspectVocabs.getGraphOfVocabFile(os.path.join(filePath, artifact+"_type=parsed.ttl"))
    print("Run SHACL Tests...")
    conformsLicense, reportGraphLicense, reportTextLicense = validation.licenseViolationValidation(ontoGraph)
    #print(reportTextLicense)
    with open(os.path.join(filePath, artifact+"_type=shaclReport_validates=minLicense.ttl"), "w+") as minLicenseFile:
      print(validation.getTurtleGraph(reportGraphLicense), file=minLicenseFile)
    conformsLode, reportGraphLode, reportTextLode = validation.lodeReadyValidation(ontoGraph)
    #print(reportTextLode)
    with open(os.path.join(filePath, artifact+"_type=shaclReport_validates=lodeMetadata.ttl"), "w+") as lodeMetaFile:
      print(validation.getTurtleGraph(reportGraphLode), file=lodeMetaFile)
    conformsLicense2, reportGraphLicense2, reportTextLicense2 = validation.licenseWarningValidation(ontoGraph)
    #print(reportTextLicense2)
    with open(os.path.join(filePath, artifact+"_type=shaclReport_validates=goodLicense.ttl"), "w+") as advLicenseFile:
      print(validation.getTurtleGraph(reportGraphLicense2), file=advLicenseFile)
    # checks consistency with and without imports
    print("Check consistency...")
    isConsistent, output = validation.getConsistency(os.path.join(filePath, artifact+"_type=parsed.ttl"), ignoreImports=False)
    isConsistentNoImports, outputNoImports = validation.getConsistency(os.path.join(filePath, artifact+"_type=parsed.ttl"), ignoreImports=True)
    with open(os.path.join(filePath, artifact+"_type=pelletConsistency_imports=FULL.txt"), "w+") as consistencyReport:
      print(output, file=consistencyReport)
    with open(os.path.join(filePath, artifact+"_type=pelletConsistency_imports=NONE.txt"), "w+") as consistencyReportNoImports:
      print(outputNoImports, file=consistencyReportNoImports)
    # print pellet info files
    print("Generate Pellet info for vocabulary...")
    with open(os.path.join(filePath, artifact+"_type=pelletInfo_imports=FULL.txt"), "w+") as pelletInfoFile:
      print(validation.getPelletInfo(os.path.join(filePath, artifact+"_type=parsed.ttl"), ignoreImports=False), file=pelletInfoFile)
    with open(os.path.join(filePath, artifact+"_type=pelletInfo_imports=NONE.txt"), "w+") as pelletInfoFileNoImports:
      print(validation.getPelletInfo(os.path.join(filePath, artifact+"_type=parsed.ttl"), ignoreImports=True), file=pelletInfoFileNoImports)
    # profile check for ontology
    print("Get profile check...")
    stdout, stderr = validation.getProfileCheck(os.path.join(filePath, artifact+"_type=parsed.ttl"))
    with open(os.path.join(filePath, artifact+"_type=profile.txt"), "w+") as profileCheckFile:
      print(stderr + "\n" + stdout, file=profileCheckFile)
  else:
    print("No valid syntax, no shacl report")
    conformsLicense = "Error - No turtle file available"
    conformsLicense2 = "Error - No turtle file available"
    conformsLode = "Error - No turtle file available"
    ontoGraph = None
    parseable = False
    isConsistent = "Error - No turtle file available"
    isConsistentNoImports = "Error - No turtle file available"

  # write the metadata json file
  ontoFiles.writeVocabInformation(pathToFile=os.path.join(filePath, artifact+"_type=meta.json"),
                                  definedByUri=vocab_uri,
                                  lastModified=stringTools.getLastModifiedFromResponse(response),
                                  rapperErrors=rapperErrors,
                                  rapperWarnings=rapperWarnings,
                                  etag=stringTools.getEtagFromResponse(response),
                                  tripleSize=triples,
                                  bestHeader=bestHeader,
                                  licenseViolationsBool=conformsLicense,
                                  licenseWarningsBool=conformsLicense2,
                                  consistentWithImports=isConsistent,
                                  consistentWithoutImports=isConsistentNoImports,
                                  lodeConform=conformsLode,
                                  accessed= accessDate,
                                  headerString=str(response.headers),
                                  nirHeader = nirHeader,
                                  contentLenght=stringTools.getContentLengthFromResponse(response),
                                  semVersion=semVersion,
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
    

def checkUriEquality(uri1, uri2):
  if "#" in uri1:
    uri1 = uri1[:uri1.rfind("#")]
  if "#" in uri2:
    uri2 = uri2[:uri2.rfind("#")]
  if uri1 == uri2:
    return True
  else:
    return False

def handleNewUri(vocab_uri, index, dataPath, fallout_index, source, isNIR):
  localDir = os.path.join(dataPath, ".tmpOntTest")
  if not os.path.isdir(localDir):
    os.mkdir(localDir)

  print("Trying to validate ", vocab_uri)
  groupId, artifact = stringTools.generateGroupAndArtifactFromUri(vocab_uri)
  if groupId == None or artifact == None:
    print("Malformed Uri", vocab_uri)
    if isNIR:
      fallout_index.append((vocab_uri, False, "Malformed Uri"))
    return
  if vocab_uri in index:
    print("Already known uri, skipping...")
    return
  bestHeader  = determineBestAccHeader(vocab_uri)
 
  version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
  if bestHeader == None:
    print("No header, probably server down")
    if isNIR:
      fallout_index.append((vocab_uri, False, "Unreachable server"))
    stringTools.deleteAllFilesInDir(localDir)
    return
  accessDate = datetime.now().strftime("%Y.%m.%d; %H:%M:%S")
  success, pathToFile, response = downloadSource(vocab_uri, localDir, "tempOnt", bestHeader)
  if not success:
    print("No available Source")
    if isNIR:
      fallout_index.append((vocab_uri, False, "not reachable server"))
    stringTools.deleteAllFilesInDir(localDir)
    return
  
  ontoFiles.parseRDFSource(pathToFile, os.path.join(localDir, "parsedSource.ttl"), "turtle", deleteEmpty=True, silent=True, sourceUri=vocab_uri)
  if not os.path.isfile(os.path.join(localDir, "parsedSource.ttl")):
    print("Unparseable ontology")
    if isNIR:
      fallout_index.append((vocab_uri, False, "Unparseable file"))
    stringTools.deleteAllFilesInDir(localDir)
    return
  graph = inspectVocabs.getGraphOfVocabFile(os.path.join(localDir, "parsedSource.ttl"))
  if graph == None:
    print("Error in rdflib parsing")
    if isNIR:
      fallout_index.append((vocab_uri, False, "Error in rdflib parsing"))
    return
  real_ont_uri=inspectVocabs.getNIRUri(graph)
  if real_ont_uri == None:
    real_ont_uri = inspectVocabs.getDefinedByUri(graph)
    if real_ont_uri == None:
      if isNIR:
        fallout_index.append((vocab_uri, False, "No ontology or Class"))
      print("Neither ontology nor class")
      stringTools.deleteAllFilesInDir(localDir)
      return
    if not str(real_ont_uri) in index and not vocab_uri == str(real_ont_uri):
      print("Found isDefinedByUri", real_ont_uri)
      stringTools.deleteAllFilesInDir(localDir)
      handleNewUri(str(real_ont_uri), index, dataPath, fallout_index, source=source, isNIR=False)
      return

  if not isNIR and not checkUriEquality(vocab_uri, str(real_ont_uri)):
    print("Non information uri differs from source uri, revalidate", str(real_ont_uri))
    stringTools.deleteAllFilesInDir(localDir)
    handleNewUri(str(real_ont_uri), index, dataPath, fallout_index, source, False)
    return

  #it goes in here if the uri is NIR and  its resolveable
  real_ont_uri = str(real_ont_uri)

  if isNIR and vocab_uri != real_ont_uri:
    print("WARNING: unexpected value for real uri:", real_ont_uri)
  if real_ont_uri in index:
    print("Already known uri", real_ont_uri)
    return
  
  print("Real Uri:", real_ont_uri)
  groupId, artifact = stringTools.generateGroupAndArtifactFromUri(real_ont_uri)
  if groupId == None or artifact == None:
    print("Malformed non-information Uri", real_ont_uri)
    fallout_index.append((real_ont_uri, False, "Malformed non-information uri"))
    return
  index[real_ont_uri] = {"source" : source, "accessed" : accessDate}
  newVersionPath=os.path.join(dataPath, groupId, artifact, version)
  os.makedirs(newVersionPath, exist_ok=True)
  # generate parent pom
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
  # prepare new release
  fileExt = os.path.splitext(pathToFile)[1]
  os.rename(pathToFile, os.path.join(newVersionPath, artifact+"_type=orig" + fileExt))
  # new release
  generateNewRelease(real_ont_uri, newVersionPath, artifact, os.path.join(newVersionPath, artifact+"_type=orig" + fileExt), bestHeader, response, accessDate)
  # index writing
  ontoFiles.writeFalloutIndex(fallout_index)
  ontoFiles.writeIndexJson(index)
  stringTools.deleteAllFilesInDir(localDir)


def getLovUrls():
  req = requests.get(lovOntologiesURL)
  json_data=req.json()
  return [dataObj["uri"] for dataObj in json_data]

def testLOVInfo():
  req = requests.get("https://lov.linkeddata.es/dataset/lov/api/v2/vocabulary/info?vocab=schema")
  json_data = req.json()
  for versionObj in json_data["versions"]:
    resourceUrl = versionObj["fileURL"]
    verison = versionObj["name"]
    print("Download source:", resourceUrl)
    success, pathToFile, response = downloadSource(resourceUrl, ".", "tempOnt"+verison, "text/rdf+n3")
    print(success)

handleNewUri("https://w3id.org/tree", {}, "scd-testdir", [], "test", False)