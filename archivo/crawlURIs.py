import requests
import re
import os
import sys
import traceback
from datetime import datetime
from dateutil.parser import parse as parsedate
from utils import stringTools, generatePoms, ontoFiles, inspectVocabs, archivoConfig, docTemplates
from utils.validation import TestSuite
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse, urldefrag, quote
from rdflib.term import Literal, URIRef
import uuid
from string import Template

# url to get all vocabs and their resource
lovOntologiesURL="https://lov.linkeddata.es/dataset/lov/api/v2/vocabulary/list"

# url for the lodo docu service
lodeServiceUrl="https://w3id.org/lode/owlapi/"

# url for the oops rest service
oopsServiceUrl=" http://oops.linkeddata.es/rest"

# possible headers for rdf-data
rdfHeaders=["application/rdf+xml", "application/ntriples", "text/turtle", "application/html"]
rdfHeadersMapping = {"application/rdf+xml":"rdfxml", "application/ntriples":"ntriples", "text/turtle":"turtle", "application/html":"rdfa"}

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
    return None, None
  robotsUrl =parsedUrl.scheme + "://" + parsedUrl.netloc + "/robots.txt"
  try:
    req = requests.get(url=robotsUrl)
  except requests.exceptions.SSLError:
    return False, "SSL error"
  except requests.exceptions.ConnectionError:
    return False, "Connection Error"
  if req.status_code > 400:
    # if robots.txt is not accessible, we are allowed
    return True, None
  rp = RobotFileParser()
  rp.set_url(robotsUrl)
  rp.parse(req.text.split("\n"))
  if rp.can_fetch(archivoConfig.archivo_agent, uri):
    return True, None
  else:
    return False, "Not allowed"

def determineBestAccHeader(vocab_uri, localDir):
  localTestDir = os.path.join(localDir,".tmpTestTriples")
  errors = set()
  if not os.path.isdir(localTestDir):
    os.mkdir(localTestDir)
  print("Determining the best header for this vocabulary...")
  headerDict = {}
  os.makedirs(localTestDir, exist_ok=True)
  for header in rdfHeadersMapping:
    success, filePath, response = downloadSource(vocab_uri, localTestDir, "testTriples", header)
    if success:
      tripleNumber = ontoFiles.getParsedTriples(filePath, inputFormat=rdfHeadersMapping[header])
      if tripleNumber != None:
        headerDict[header] = tripleNumber
        #print("Accept-Header: ",header,"; TripleNumber: ",tripleNumber)
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
    traceback.print_exc(file=sys.stdout)
    return False, "", "Error - UnknownError"

def updateFromOldFile(vocab_uri, filePath, artifact, pathToOrigFile, bestHeader, oldMetadata, accessDate, testSuite, semVersion):
  artifactPath, version = os.path.split(filePath)
  groupPath = os.path.split(artifactPath)[0]
  groupId = os.path.split(groupPath)[1]
  nirHeader = oldMetadata["logs"]["nir-header"]
  # generate parsed variants of the ontology
  rapperErrors, rapperWarnings=ontoFiles.parseRDFSource(pathToOrigFile, os.path.join(filePath, artifact+"_type=parsed.ttl"), outputType="turtle", deleteEmpty=True, sourceUri=vocab_uri, inputFormat=rdfHeadersMapping[bestHeader])
  ontoFiles.parseRDFSource(pathToOrigFile, os.path.join(filePath, artifact+"_type=parsed.nt"), outputType="ntriples", deleteEmpty=True, sourceUri=vocab_uri, inputFormat=rdfHeadersMapping[bestHeader])
  ontoFiles.parseRDFSource(pathToOrigFile, os.path.join(filePath, artifact+"_type=parsed.owl"), outputType="rdfxml", deleteEmpty=True, sourceUri=vocab_uri, inputFormat=rdfHeadersMapping[bestHeader])
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
                                  lastModified=oldMetadata["http-data"]["lastModified"],
                                  rapperErrors=rapperErrors,
                                  rapperWarnings=rapperWarnings,
                                  etag=oldMetadata["http-data"]["e-tag"],
                                  tripleSize=triples,
                                  bestHeader=bestHeader,
                                  licenseViolationsBool=conformsLicense,
                                  licenseWarningsBool=conformsLicense2,
                                  consistentWithImports=isConsistent,
                                  consistentWithoutImports=isConsistentNoImports,
                                  lodeConform=conformsLode,
                                  accessed= accessDate,
                                  headerString=oldMetadata["logs"]["resource-header"],
                                  nirHeader = nirHeader,
                                  contentLenght=oldMetadata["http-data"]["content-length"],
                                  semVersion=semVersion,
                                  )
  if triples > 0:
    if not os.path.isfile(filePath + os.sep + artifact + "_type=generatedDocu.html"):
      docustring = getLodeDocuFile(vocab_uri)
      with open(filePath + os.sep + artifact + "_type=generatedDocu.html", "w+") as docufile:
        print(docustring, file=docufile)

    if not os.path.isfile(os.path.join(filePath, artifact + "_type=OOPS.rdf")):
      oopsReport = getOOPSReport(ontoFiles.getParsedRdf(pathToOrigFile))
    else:
      oopsReport = None
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
  location_url = response.url
  # generate parsed variants of the ontology
  rapperErrors, rapperWarnings=ontoFiles.parseRDFSource(pathToOrigFile, os.path.join(filePath, artifact+"_type=parsed.ttl"), outputType="turtle", deleteEmpty=True, sourceUri=vocab_uri, inputFormat=rdfHeadersMapping[bestHeader])
  ontoFiles.parseRDFSource(pathToOrigFile, os.path.join(filePath, artifact+"_type=parsed.nt"), outputType="ntriples", deleteEmpty=True, sourceUri=vocab_uri, inputFormat=rdfHeadersMapping[bestHeader])
  ontoFiles.parseRDFSource(pathToOrigFile, os.path.join(filePath, artifact+"_type=parsed.owl"), outputType="rdfxml", deleteEmpty=True, sourceUri=vocab_uri, inputFormat=rdfHeadersMapping[bestHeader])
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
                                  snapshot_url=location_url
                                  )
  if triples > 0:                                                                
    docustring = getLodeDocuFile(vocab_uri)
    with open(filePath + os.sep + artifact + "_type=generatedDocu.html", "w+") as docufile:
      print(docustring, file=docufile)
    oopsReport = getOOPSReport(ontoFiles.getParsedRdf(pathToOrigFile))
    if oopsReport != None:
      with open(os.path.join(filePath, artifact + "_type=OOPS.rdf"), "w+") as oopsFile:
        print(oopsReport, file=oopsFile)
  generatePomAndMdFile(vocab_uri, os.path.split(filePath)[0], groupId, artifact, version, ontoGraph, location_url)

def generatePomAndMdFile(uri, artifactPath, groupId, artifact, version, ontograph, location_url):
  datetime_obj= datetime.strptime(version, "%Y.%m.%d-%H%M%S")
  versionIRI = str(None) 
  md_label=uri
  md_description=Template(docTemplates.description)
  md_comment=Template(docTemplates.default_explaination).safe_substitute(non_information_uri=uri)
  license=None
  if ontograph != None:
    label = inspectVocabs.getLabel(ontograph)
    description = inspectVocabs.getDescription(ontograph)
    comment = inspectVocabs.getComment(ontograph)
    versionIRI = inspectVocabs.getOwlVersionIRI(ontograph)
    if label != None:
      md_label = label

    if comment != None:
      md_comment = comment
    
    if description != None:
      md_description = md_description.safe_substitute(non_information_uri=uri, snapshot_url=location_url, owl_version_iri=versionIRI, date=str(datetime_obj)) + "\n\n" + docTemplates.description_intro + "\n\n" + description
    else:
      md_description = md_description.safe_substitute(non_information_uri=uri, snapshot_url=location_url, owl_version_iri=versionIRI, date=str(datetime_obj))
    license =inspectVocabs.getLicense(ontograph)
    if isinstance(license, URIRef):
      license = str(license).strip("<>")
    elif isinstance(license, Literal):
      # if license is literal: error uri
      license = docTemplates.license_literal_uri

  childpomString = generatePoms.generateChildPom(groupId=groupId,
                                                  version=version,
                                                  artifactId=artifact,
                                                  packaging="jar",
                                                  license=license)
  with open(os.path.join(artifactPath, "pom.xml"), "w+") as childPomFile:
    print(childpomString, file=childPomFile)
  generatePoms.writeMarkdownDescription(artifactPath, artifact, md_label, md_comment, md_description)

def checkIndexForUri(uri, index):
    for indexUri in index:
        if urldefrag(uri)[0] == urldefrag(indexUri)[0]:
            return indexUri
    return None

def checkUriEquality(uri1, uri2):
  if urldefrag(uri1)[0] == urldefrag(uri2)[0]:
    return True
  else:
    return False

def handleNewUri(vocab_uri, index, dataPath, fallout_index, source, isNIR, testSuite):
  # remove fragment
  vocab_uri = urldefrag(vocab_uri)[0]
  localDir = os.path.join(dataPath, "." + uuid.uuid4().hex)
  if not os.path.isdir(localDir):
    os.mkdir(localDir)

  # testing uri validity
  print("Trying to validate ", vocab_uri)
  groupId, artifact = stringTools.generateGroupAndArtifactFromUri(vocab_uri)
  if groupId == None or artifact == None:
    print("Malformed Uri", vocab_uri)
    if isNIR:
      fallout_index.append((vocab_uri, str(datetime.now()), source, False, "Malformed Uri"))
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR,"Error - Malformed Uri. Please use a valid http URI"
  if checkIndexForUri(vocab_uri, index) != None:
    print("Already known uri, skipping...")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return True, isNIR, f"This Ontology is already in the Archivo index and can be found at <a href=https://databus.dbpedia.org/ontologies/{groupId}/{artifact}>https://databus.dbpedia.org/ontologies/{groupId}/{artifact}</a>"
  
  # check robots.txt access
  allowed = checkRobot(vocab_uri)
  print("Robot allowed:", allowed)
  if not allowed:
    if isNIR:
      fallout_index.append((vocab_uri, str(datetime.now()), source, False, f"Archivo-Agent {archivoConfig.archivo_agent} is not allowed to access the ontology at {vocab_uri}"))
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR, f"Archivo-Agent {archivoConfig.archivo_agent} is not allowed to access the ontology at <a href={vocab_uri}>{vocab_uri}</a>"
  
  bestHeader, headerErrors = determineBestAccHeader(vocab_uri, dataPath)
  if headerErrors == set():
    headerErrorsString = "Cant parse RDF from this URI"
  else:
    headerErrorsString = ";".join(headerErrors)

  version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
  if bestHeader == None:
    print("\n".join(headerErrors))
    if isNIR:
      fallout_index.append((vocab_uri, str(datetime.now()), source, False, f"ERROR: {headerErrorsString}"))
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR,f"There was an error accessing {vocab_uri}:\n" + "\n".join(headerErrors)
  accessDate = datetime.now().strftime("%Y.%m.%d; %H:%M:%S")


  # downloading and parsing
  success, pathToFile, response = downloadSource(vocab_uri, localDir, "tmpOnt", bestHeader)
  if not success:
    print("No available Source")
    if isNIR:
      fallout_index.append((vocab_uri, str(datetime.now()), source, False, str(response)))
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR,"Couldn't access the suggested URI: " + str(response)
  
  rapperErrors, rapperWarnings = ontoFiles.parseRDFSource(pathToFile, os.path.join(localDir, "parsedSource.ttl"), "turtle", deleteEmpty=True, silent=True, sourceUri=vocab_uri, inputFormat=rdfHeadersMapping[bestHeader])
  if not os.path.isfile(os.path.join(localDir, "parsedSource.ttl")):
    print("There was an error in parsing ontology of", vocab_uri)
    if isNIR:
      fallout_index.append((vocab_uri, str(datetime.now()), source, False, "INTERNAL ERROR: Couldn't parse file. "))
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR, "Couldnt parse RDF:" + "\n" + rapperErrors.replace(";", "<br>")

  
  graph = inspectVocabs.getGraphOfVocabFile(os.path.join(localDir, "parsedSource.ttl"))
  if graph == None:
    print("Error in rdflib parsing")
    if isNIR:
      fallout_index.append((vocab_uri, str(datetime.now()), source, False, "Error in rdflib parsing"))
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR, "Unexpected Error: RDFlib couldn't read the file."
  
  try:
    real_ont_uri=inspectVocabs.getNIRUri(graph)
  except Exception:
    traceback.print_exc(file=sys.stderr)
    stringTools.deleteAllFilesInDirAndDir(localDir)
    fallout_index.append((vocab_uri, str(datetime.now()), source, False, "Error at querying with rdflib"))
    return False, isNIR, "There was a querying error reading the file with rdflib"


  if real_ont_uri == None:
    print("Couldn't find ontology uri, trying isDefinedBy...")
    real_ont_uri = inspectVocabs.getDefinedByUri(graph)
    if real_ont_uri == None:
      print("No Ontology discoverable")
      if isNIR:
        fallout_index.append((vocab_uri, str(datetime.now()), source, False, "Neither a Vocab nor a link to one"))
      stringTools.deleteAllFilesInDirAndDir(localDir)
      return False, isNIR, "The given URI does not contain a rdf:type owl:Ontology, rdfs:isDefinedBy, skos:inScheme or a skos:ConceptScheme triple"
    
    if not checkUriEquality(vocab_uri, str(real_ont_uri)):
      print("Found isDefinedBy or skos uri", real_ont_uri)
      stringTools.deleteAllFilesInDirAndDir(localDir)
      return handleNewUri(str(real_ont_uri), index, dataPath, fallout_index, testSuite=testSuite,source=source, isNIR=True) 
    else:
      print("Uri already in index or self-defining non-ontology")
      if isNIR:
        fallout_index.append((vocab_uri, str(datetime.now()), source, False, "Self defining non-ontology"))
      stringTools.deleteAllFilesInDirAndDir(localDir)
      return False, isNIR, "No owl:Ontology defined"

  isNIR=True
  if not checkUriEquality(vocab_uri, str(real_ont_uri)):
    print("Non information uri differs from source uri, revalidate", str(real_ont_uri))
    stringTools.deleteAllFilesInDirAndDir(localDir)
    groupId, artifact = stringTools.generateGroupAndArtifactFromUri(str(real_ont_uri))
    if groupId == None or artifact == None:
      print("Malformed Uri", vocab_uri)
      if isNIR:
        fallout_index.append((vocab_uri, str(datetime.now()), source, False, "Malformed Uri"))
      stringTools.deleteAllFilesInDirAndDir(localDir)
      return False, isNIR,"Error - Malformed Uri. Please use a valid http URI"
    else:
      return handleNewUri(str(real_ont_uri), index, dataPath, fallout_index, source, True, testSuite=testSuite)
 

  #it goes in here if the uri is NIR and  its resolveable
  real_ont_uri = str(real_ont_uri)

  if isNIR and vocab_uri != real_ont_uri:
    print("WARNING: unexpected value for real uri:", real_ont_uri)

  print("Real Uri:", real_ont_uri)
  groupId, artifact = stringTools.generateGroupAndArtifactFromUri(real_ont_uri)
  if groupId == None or artifact == None:
    print("Malformed non-information Uri", real_ont_uri)
    fallout_index.append((vocab_uri, str(datetime.now()), source, False, "Malformed non-information uri"))
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR, "Malformed non-information uri " + real_ont_uri


  if checkIndexForUri(real_ont_uri, index) != None:
    print("Already known uri", real_ont_uri)
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return True, isNIR, f"This Ontology is already in the Archivo index and can be found at <a href=https://databus.dbpedia.org/ontologies/{groupId}/{artifact}>https://databus.dbpedia.org/ontologies/{groupId}/{artifact}</a>"
  
  
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
                                            groupdocu=Template(docTemplates.groupDoc).safe_substitute(groupid=groupId),
                                            )
    with open(os.path.join(dataPath, groupId, "pom.xml"), "w+") as parentPomFile:
      print(pomString, file=parentPomFile)
  # prepare new release
  fileExt = os.path.splitext(pathToFile)[1]
  os.rename(pathToFile, os.path.join(newVersionPath, artifact+"_type=orig" + fileExt))
  # new release
  generateNewRelease(urldefrag(real_ont_uri)[0], newVersionPath, artifact, os.path.join(newVersionPath, artifact+"_type=orig" + fileExt), bestHeader, response, accessDate, testSuite)
  # index writing
  #ontoFiles.writeFalloutIndex(fallout_index)
  #ontoFiles.writeIndexJson(index)
  stringTools.deleteAllFilesInDirAndDir(localDir)
  
  returncode, deployLog =generatePoms.callMaven(os.path.join(dataPath, groupId, artifact, "pom.xml"), "deploy")
  print(deployLog)
  returncode = 0
  if returncode > 0:
    return False, isNIR, "There was an error deploying the Ontology to the databus:<br><br>" + "<br>".join(deployLog.split("\n"))
  return True, isNIR, f"Added the Ontology to Archivo, should be accessable at <a href=https://databus.dbpedia.org/ontologies/{groupId}/{artifact}>https://databus.dbpedia.org/ontologies/{groupId}/{artifact}</a> soon"


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