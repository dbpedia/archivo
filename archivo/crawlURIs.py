import requests
import re
import os
import sys
import traceback
from datetime import datetime
from dateutil.parser import parse as parsedate
from utils import stringTools, generatePoms, ontoFiles, inspectVocabs, archivoConfig
from utils.validation import TestSuite
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse, urldefrag

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
    response = requests.post(oopsServiceUrl, data=oopsXml.encode("utf-8"), headers=headers, timeout=30)
    if response.status_code < 400:
      return response.text
    else:
      print("Bad Connection: Status", response.status_code)
      return None
  except Exception:
    print("Something went wrong generating the OOPS-report")
    traceback.print_exc(file=sys.stdout)
    return None


def checkRobot(uri):
  parsedUrl = urlparse(uri)
  if parsedUrl.scheme == "" or parsedUrl.netloc == "":
    return None
  robotsUrl =parsedUrl.scheme + "://" + parsedUrl.netloc + "/robots.txt"

  rp = RobotFileParser()
  rp.set_url(robotsUrl)
  rp.read()
  if rp.can_fetch("*",uri):
    return True
  else:
    return False

def determineBestAccHeader(vocab_uri, localDir):
  localTestDir = os.path.join(localDir,".tmpTestTriples")
  errors = set()
  if not os.path.isdir(localTestDir):
    os.mkdir(localTestDir)
  print("Determining the best header for this vocabulary...")
  headerDict = {}
  os.makedirs(localTestDir, exist_ok=True)
  for header in rdfHeaders:
    success, filePath, response = downloadSource(vocab_uri, localTestDir, "testTriples", header)
    if success:
      tripleNumber = ontoFiles.getParsedTriples(filePath)
      if tripleNumber != None:
        headerDict[header] = tripleNumber
        print("Accept-Header: ",header,"; TripleNumber: ",tripleNumber)
    else:
      errors.add(response)
  generatedFiles = [f for f in os.listdir(localTestDir) if os.path.isfile(localTestDir + os.sep + f)]
  for filename in generatedFiles:
    os.remove(os.path.join(localTestDir, filename))
  # return the header with the most triples
  if headerDict == {}:
    return None, errors
  else:
    return [k for k, v in sorted(headerDict.items(), key=lambda item: item[1], reverse=True)][0], errors


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
      return False, filePath, "Error - Status " + str(response.status_code)
  except requests.exceptions.TooManyRedirects:
    print("Too many redirects, cancel parsing...")
    return False, "", "Error - too many redirects"
  except TimeoutError:
    print("Timed out during parsing: "+uri)
    return False, "", "Error - Timeout error"
  except requests.exceptions.ConnectionError:
    print("Bad Connection "+ uri)
    return False, "", "Error - ConnectionError"
  except requests.exceptions.ReadTimeout:
    print("Connection timed out for URI ", uri)
    return False, "", "Error - ReadTimeout"
  except KeyboardInterrupt:
    print("Keyboard interruption")
    sys.exit(19)
  except:
    print("Unknown error during download")
    return False, "", "Error - UnknownError"

def updateFromOldFile(vocab_uri, filePath, artifact, pathToOrigFile, bestHeader, oldMetadata, accessDate, testSuite, semVersion="0.0.1"):
  artifactPath, version = os.path.split(filePath)
  groupPath = os.path.split(artifactPath)[0]
  groupId = os.path.split(groupPath)[1]
  nirHeader = oldMetadata["NIR-header"]
  # generate parsed variants of the ontology
  rapperErrors, rapperWarnings=ontoFiles.parseRDFSource(pathToOrigFile, os.path.join(filePath, artifact+"_type=parsed.ttl"), outputType="turtle", deleteEmpty=True, sourceUri=vocab_uri)
  ontoFiles.parseRDFSource(pathToOrigFile, os.path.join(filePath, artifact+"_type=parsed.nt"), outputType="ntriples", deleteEmpty=True, sourceUri=vocab_uri)
  ontoFiles.parseRDFSource(pathToOrigFile, os.path.join(filePath, artifact+"_type=parsed.owl"), outputType="rdfxml", deleteEmpty=True, sourceUri=vocab_uri)
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
    conformsLicense, reportGraphLicense, reportTextLicense = testSuite.licenseViolationValidation(ontoGraph)
    #print(reportTextLicense)
    with open(os.path.join(filePath, artifact+"_type=shaclReport_validates=minLicense.ttl"), "w+") as minLicenseFile:
      print(inspectVocabs.getTurtleGraph(reportGraphLicense), file=minLicenseFile)
    conformsLode, reportGraphLode, reportTextLode = testSuite.lodeReadyValidation(ontoGraph)
    #print(reportTextLode)
    with open(os.path.join(filePath, artifact+"_type=shaclReport_validates=lodeMetadata.ttl"), "w+") as lodeMetaFile:
      print(inspectVocabs.getTurtleGraph(reportGraphLode), file=lodeMetaFile)
    conformsLicense2, reportGraphLicense2, reportTextLicense2 = testSuite.licenseWarningValidation(ontoGraph)
    #print(reportTextLicense2)
    with open(os.path.join(filePath, artifact+"_type=shaclReport_validates=goodLicense.ttl"), "w+") as advLicenseFile:
      print(inspectVocabs.getTurtleGraph(reportGraphLicense2), file=advLicenseFile)
    # checks consistency with and without imports
    print("Check consistency...")
    isConsistent, output = testSuite.getConsistency(os.path.join(filePath, artifact+"_type=parsed.ttl"), ignoreImports=False)
    isConsistentNoImports, outputNoImports = testSuite.getConsistency(os.path.join(filePath, artifact+"_type=parsed.ttl"), ignoreImports=True)
    with open(os.path.join(filePath, artifact+"_type=pelletConsistency_imports=FULL.txt"), "w+") as consistencyReport:
      print(output, file=consistencyReport)
    with open(os.path.join(filePath, artifact+"_type=pelletConsistency_imports=NONE.txt"), "w+") as consistencyReportNoImports:
      print(outputNoImports, file=consistencyReportNoImports)
    # print pellet info files
    print("Generate Pellet info for vocabulary...")
    with open(os.path.join(filePath, artifact+"_type=pelletInfo_imports=FULL.txt"), "w+") as pelletInfoFile:
      print(testSuite.getPelletInfo(os.path.join(filePath, artifact+"_type=parsed.ttl"), ignoreImports=False), file=pelletInfoFile)
    with open(os.path.join(filePath, artifact+"_type=pelletInfo_imports=NONE.txt"), "w+") as pelletInfoFileNoImports:
      print(testSuite.getPelletInfo(os.path.join(filePath, artifact+"_type=parsed.ttl"), ignoreImports=True), file=pelletInfoFileNoImports)
    # profile check for ontology
    print("Get profile check...")
    stdout, stderr = testSuite.getProfileCheck(os.path.join(filePath, artifact+"_type=parsed.ttl"))
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
  ontoFiles.altWriteVocabInformation(pathToFile=os.path.join(filePath, artifact+"_type=meta.json"),
                                  definedByUri=vocab_uri,
                                  lastModified=oldMetadata["lastModified"],
                                  rapperErrors=rapperErrors,
                                  rapperWarnings=rapperWarnings,
                                  etag=oldMetadata["E-Tag"],
                                  tripleSize=triples,
                                  bestHeader=bestHeader,
                                  licenseViolationsBool=conformsLicense,
                                  licenseWarningsBool=conformsLicense2,
                                  consistentWithImports=isConsistent,
                                  consistentWithoutImports=isConsistentNoImports,
                                  lodeConform=conformsLode,
                                  accessed= accessDate,
                                  headerString=oldMetadata["resource-header"],
                                  nirHeader = nirHeader,
                                  contentLenght=oldMetadata["content-length"],
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
  generatePomAndMdFile(vocab_uri, os.path.split(filePath)[0], groupId, artifact, version, ontoGraph)

def generateNewRelease(vocab_uri, filePath, artifact, pathToOrigFile, bestHeader, response, accessDate, testSuite, semVersion="0.0.1"):
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
  ontoFiles.parseRDFSource(pathToOrigFile, os.path.join(filePath, artifact+"_type=parsed.owl"), outputType="rdfxml", deleteEmpty=True, sourceUri=vocab_uri)
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
    conformsLicense, reportGraphLicense, reportTextLicense = testSuite.licenseViolationValidation(ontoGraph)
    #print(reportTextLicense)
    with open(os.path.join(filePath, artifact+"_type=shaclReport_validates=minLicense.ttl"), "w+") as minLicenseFile:
      print(inspectVocabs.getTurtleGraph(reportGraphLicense), file=minLicenseFile)
    conformsLode, reportGraphLode, reportTextLode = testSuite.lodeReadyValidation(ontoGraph)
    #print(reportTextLode)
    with open(os.path.join(filePath, artifact+"_type=shaclReport_validates=lodeMetadata.ttl"), "w+") as lodeMetaFile:
      print(inspectVocabs.getTurtleGraph(reportGraphLode), file=lodeMetaFile)
    conformsLicense2, reportGraphLicense2, reportTextLicense2 = testSuite.licenseWarningValidation(ontoGraph)
    #print(reportTextLicense2)
    with open(os.path.join(filePath, artifact+"_type=shaclReport_validates=goodLicense.ttl"), "w+") as advLicenseFile:
      print(inspectVocabs.getTurtleGraph(reportGraphLicense2), file=advLicenseFile)
    # checks consistency with and without imports
    print("Check consistency...")
    isConsistent, output = testSuite.getConsistency(os.path.join(filePath, artifact+"_type=parsed.ttl"), ignoreImports=False)
    isConsistentNoImports, outputNoImports = testSuite.getConsistency(os.path.join(filePath, artifact+"_type=parsed.ttl"), ignoreImports=True)
    with open(os.path.join(filePath, artifact+"_type=pelletConsistency_imports=FULL.txt"), "w+") as consistencyReport:
      print(output, file=consistencyReport)
    with open(os.path.join(filePath, artifact+"_type=pelletConsistency_imports=NONE.txt"), "w+") as consistencyReportNoImports:
      print(outputNoImports, file=consistencyReportNoImports)
    # print pellet info files
    print("Generate Pellet info for vocabulary...")
    with open(os.path.join(filePath, artifact+"_type=pelletInfo_imports=FULL.txt"), "w+") as pelletInfoFile:
      print(testSuite.getPelletInfo(os.path.join(filePath, artifact+"_type=parsed.ttl"), ignoreImports=False), file=pelletInfoFile)
    with open(os.path.join(filePath, artifact+"_type=pelletInfo_imports=NONE.txt"), "w+") as pelletInfoFileNoImports:
      print(testSuite.getPelletInfo(os.path.join(filePath, artifact+"_type=parsed.ttl"), ignoreImports=True), file=pelletInfoFileNoImports)
    # profile check for ontology
    print("Get profile check...")
    stdout, stderr = testSuite.getProfileCheck(os.path.join(filePath, artifact+"_type=parsed.ttl"))
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
  ontoFiles.altWriteVocabInformation(pathToFile=os.path.join(filePath, artifact+"_type=meta.json"),
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
  generatePomAndMdFile(vocab_uri, os.path.split(filePath)[0], groupId, artifact, version, ontoGraph)

def generatePomAndMdFile(uri, artifactPath, groupId, artifact, version, ontograph):
  md_label=uri
  md_description=""
  md_comment=archivoConfig.default_explaination
  license=None
  if ontograph != None:
    label = inspectVocabs.getLabel(ontograph)
    description = inspectVocabs.getDescription(ontograph)
    comment = inspectVocabs.getComment(ontograph)
    if label != None:
      md_label = label

    if comment != None:
      md_comment = comment
    
    if description != None:
      md_description = description
    license =inspectVocabs.getLicense(ontograph)

  childpomString = generatePoms.generateChildPom(groupId=groupId,
                                                  version=version,
                                                  artifactId=artifact,
                                                  packaging="jar",
                                                  license=license)
  with open(os.path.join(artifactPath, "pom.xml"), "w+") as childPomFile:
    print(childpomString, file=childPomFile)
  generatePoms.writeMarkdownDescription(artifactPath, artifact, md_label, md_comment, md_description)
    

def checkUriEquality(uri1, uri2):
  if "#" in uri1:
    uri1 = uri1[:uri1.rfind("#")]
  if "#" in uri2:
    uri2 = uri2[:uri2.rfind("#")]
  if uri1 == uri2:
    return True
  else:
    return False

def checkIndexForUri(uri, index):
    for indexUri in index:
        if urldefrag(uri)[0] == urldefrag(indexUri)[0]:
            return True
    return False

def handleNewUri(vocab_uri, index, dataPath, fallout_index, source, isNIR, testSuite):
  vocab_uri = urldefrag(vocab_uri)[0]
  localDir = os.path.join(dataPath, ".tmpOntTest")
  if not os.path.isdir(localDir):
    os.mkdir(localDir)

  print("Trying to validate ", vocab_uri)
  groupId, artifact = stringTools.generateGroupAndArtifactFromUri(vocab_uri)
  if groupId == None or artifact == None:
    print("Malformed Uri", vocab_uri)
    if isNIR:
      fallout_index.append((vocab_uri, False, "Malformed Uri"))
    return False, isNIR,"Error - Malformed Uri. Please use a valid http URI"
  if checkIndexForUri(vocab_uri, index):
    print("Already known uri, skipping...")
    return True, isNIR, f"This Ontology is already in the Archivo index and can be found at https://databus.dbpedia.org/ontologies/{groupId}/{artifact}"
  bestHeader, headerErrors = determineBestAccHeader(vocab_uri, dataPath)
 
  version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
  if bestHeader == None:
    print("No header, probably server down"+ "\n".join(headerErrors))
    if isNIR:
      fallout_index.append((vocab_uri, False, "Unreachable server"))
    stringTools.deleteAllFilesInDir(localDir)
    return False, isNIR,f"There was an error accessing {vocab_uri}:\n" + "\n".join(headerErrors)
  accessDate = datetime.now().strftime("%Y.%m.%d; %H:%M:%S")
  success, pathToFile, response = downloadSource(vocab_uri, localDir, "tempOnt", bestHeader)
  if not success:
    print("No available Source")
    if isNIR:
      fallout_index.append((vocab_uri, False, str(response)))
    stringTools.deleteAllFilesInDir(localDir)
    return False, isNIR,"Couldn't access the suggested URI: " + str(response)
  
  rapperErrors, rapperWarnings = ontoFiles.parseRDFSource(pathToFile, os.path.join(localDir, "parsedSource.ttl"), "turtle", deleteEmpty=True, silent=True, sourceUri=vocab_uri)
  if not os.path.isfile(os.path.join(localDir, "parsedSource.ttl")):
    print("Unparseable ontology")
    if isNIR:
      fallout_index.append((vocab_uri, False, "Unparseable file"))
    stringTools.deleteAllFilesInDir(localDir)
    return False, isNIR, "Unparseable RDF:" + "\n" + rapperErrors.replace(";", "\n")
  graph = inspectVocabs.getGraphOfVocabFile(os.path.join(localDir, "parsedSource.ttl"))
  if graph == None:
    print("Error in rdflib parsing")
    if isNIR:
      fallout_index.append((vocab_uri, False, "Error in rdflib parsing"))
    return False, isNIR, "RDFLIB parsing error"
  real_ont_uri=inspectVocabs.getNIRUri(graph)
  print(real_ont_uri)
  if real_ont_uri == None:
    print("Couldn't find ontology uri, trying isDefinedBy...")
    real_ont_uri = inspectVocabs.getDefinedByUri(graph)
    if real_ont_uri == None:
      if isNIR:
        fallout_index.append((vocab_uri, False, "No ontology or Class"))
      print("Neither ontology nor class")
      stringTools.deleteAllFilesInDir(localDir)
      return False, isNIR, "The given URI does not contain a rdf:type owl:Ontology or rdfs:isDefinedBy triple"
    if not str(real_ont_uri) in index and not checkUriEquality(vocab_uri, str(real_ont_uri)):
      print("Found isDefinedByUri", real_ont_uri)
      stringTools.deleteAllFilesInDir(localDir)
      return handleNewUri(str(real_ont_uri), index, dataPath, fallout_index, testSuite=testSuite,source=source, isNIR=False) 
    else:
      print("Uri already in index or self-defining non-ontology")
      if isNIR:
        fallout_index.append((str(real_ont_uri), False, "Self defining non-ontology"))
      return False, isNIR, "Self defining non-ontology"

  if not isNIR and not checkUriEquality(vocab_uri, str(real_ont_uri)):
    print("Non information uri differs from source uri, revalidate", str(real_ont_uri))
    stringTools.deleteAllFilesInDir(localDir)
    return handleNewUri(str(real_ont_uri), index, dataPath, fallout_index, source, True, testSuite=testSuite)
 

  #it goes in here if the uri is NIR and  its resolveable
  real_ont_uri = str(real_ont_uri)

  if isNIR and vocab_uri != real_ont_uri:
    print("WARNING: unexpected value for real uri:", real_ont_uri)

  print("Real Uri:", real_ont_uri)
  groupId, artifact = stringTools.generateGroupAndArtifactFromUri(real_ont_uri)
  if groupId == None or artifact == None:
    print("Malformed non-information Uri", real_ont_uri)
    fallout_index.append((real_ont_uri, False, "Malformed non-information uri"))
    return False, isNIR, "Malformed non-information uri " + real_ont_uri


  if checkIndexForUri(real_ont_uri, index):
    print("Already known uri", real_ont_uri)
    return True, isNIR, "This Ontology is already in the Archivo index and can be found at https://databus.dbpedia.org/ontologies/{groupId}/{artifact}"
  
  
  index[real_ont_uri] = {"source" : source, "accessed" : accessDate}
  newVersionPath=os.path.join(dataPath, groupId, artifact, version)
  os.makedirs(newVersionPath, exist_ok=True)
  # generate parent pom
  if not os.path.isfile(os.path.join(dataPath, groupId, "pom.xml")):
    pomString=generatePoms.generateParentPom(groupId=groupId,
                                            packaging="pom",
                                            modules=[],
                                            packageDirectory=archivoConfig.packDir,
                                            downloadUrlPath=archivoConfig.downloadUrl,
                                            publisher=archivoConfig.pub,
                                            maintainer=archivoConfig.pub,
                                            groupdocu=archivoConfig.groupDoc.format(groupId),
                                            )
    with open(os.path.join(dataPath, groupId, "pom.xml"), "w+") as parentPomFile:
      print(pomString, file=parentPomFile)
  # prepare new release
  fileExt = os.path.splitext(pathToFile)[1]
  os.rename(pathToFile, os.path.join(newVersionPath, artifact+"_type=orig" + fileExt))
  # new release
  generateNewRelease(real_ont_uri, newVersionPath, artifact, os.path.join(newVersionPath, artifact+"_type=orig" + fileExt), bestHeader, response, accessDate, testSuite)
  # index writing
  #ontoFiles.writeFalloutIndex(fallout_index)
  #ontoFiles.writeIndexJson(index)
  stringTools.deleteAllFilesInDir(localDir)
  
  #print(generatePoms.callMaven(os.path.join(dataPath, groupId, artifact, "pom.xml"), "deploy"))
  return True, isNIR, f"Added the Ontology to Archivo, should be accessable at https://databus.dbpedia.org/ontologies/{groupId}/{artifact} soon"


def getLovUrls():
  req = requests.get(lovOntologiesURL)
  json_data=req.json()
  return [dataObj["uri"] for dataObj in json_data]

def testLOVInfo():
  req = requests.get("https://lov.linkeddata.es/dataset/lov/api/v2/vocabulary/info?vocab=schema")
  json_data = req.json()
  for versionObj in json_data["versions"]:
    resourceUrl = versionObj["fileURL"]
    version = versionObj["name"]
    print("Download source:", resourceUrl)
    success, pathToFile, response = downloadSource(resourceUrl, ".", "tempOnt"+version, "text/rdf+n3")
    print(success)