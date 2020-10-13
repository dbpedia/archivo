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
from webservice.dbModels import OfficialOntology, DevelopOntology, Version
import uuid
from string import Template
import logging
from SPARQLWrapper import SPARQLWrapper, JSON


# mod uris
mod_endpoint = 'http://akswnc7.informatik.uni-leipzig.de:9062/sparql/'

# url to get all vocabs and their resource
lovOntologiesURL="https://lov.linkeddata.es/dataset/lov/api/v2/vocabulary/list"

# prefix.cc complete urls
prefixccURLs = "http://prefix.cc/context"

# url for the lodo docu service
lodeServiceUrl="https://w3id.org/lode/owlapi/"

# url for the oops rest service
oopsServiceUrl=" http://oops.linkeddata.es/rest"

# possible headers for rdf-data
rdfHeaders=["application/rdf+xml", "application/ntriples", "text/turtle", "application/html"]
rdfHeadersMapping = {"application/rdf+xml":"rdfxml", "application/ntriples":"ntriples", "text/turtle":"turtle", "*/*":None}

success_symbol = "<span class=\"check\">✔</span>"
failed_symbol = "<span class=\"x\">✘</span>"

def getLodeDocuFile(vocab_uri, logger):
  try:
    response = requests.get(lodeServiceUrl + vocab_uri)
    if response.status_code < 400:
      return response.text, None
    else:
      return None, f"Access Error - Status {response.status_code}"
  except requests.exceptions.TooManyRedirects as e:
    logger.error("Exeption in loading the LODE-docu", exc_info=True)
    return None, str(e)
  except TimeoutError as e:
    logger.error("Exeption in loading the LODE-docu", exc_info=True)
    return None, str(e)
  except requests.exceptions.ConnectionError as e:
    logger.error("Exeption in loading the LODE-docu", exc_info=True)
    return None, str(e)
  except requests.exceptions.ReadTimeout as e:
    logger.error("Exeption in loading the LODE-docu", exc_info=True)
    return None, str(e)

def getOOPSReport(parsedRdfString, logger):
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
      return response.text, None
    else:
      logger.error(f"OOPS not acessible: Status {response.status_code}")
      return None, f"Not Accessible - Status {response.status_code}"
  except Exception as e:
    logger.error("Exeption in loading the OOPS-report", exc_info=True)
    return None, str(e)


def checkRobot(uri):
  parsedUrl = urlparse(uri)
  if parsedUrl.scheme == "" or parsedUrl.netloc == "":
    return None, None
  robotsUrl =parsedUrl.scheme + "://" + parsedUrl.netloc + "/robots.txt"
  try:
    req = requests.get(url=robotsUrl)
  except requests.exceptions.SSLError:
    return True, "SSL error"
  except requests.exceptions.ConnectionError:
    return True, "Connection Error"
  except requests.exceptions.InvalidSchema:
    return True, f'Invalid schema: {robotsUrl}'
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

def determineBestAccHeader(vocab_uri, localDir, user_output=[]):
  localTestDir = os.path.join(localDir,".tmpTestTriples")
  errors = set()
  if not os.path.isdir(localTestDir):
    os.mkdir(localTestDir)
  headerDict = {}
  for header in rdfHeadersMapping:
    success, filePath, response = downloadSource(vocab_uri, localTestDir, "testTriples", header)
    if success:
      tripleNumber, rapperErrors = ontoFiles.getParsedTriples(filePath, inputFormat=rdfHeadersMapping[header])
      if tripleNumber != None and tripleNumber > 0:
        user_output.append(f"Testing header {header}: {success_symbol}; Triples: {str(tripleNumber)}")
        headerDict[header] = tripleNumber
      else:
        user_output.append(f"Testing header {header}: Access {success_symbol}; Triples: {str(tripleNumber)}")
        if tripleNumber == None:
          user_output.append(rapperErrors)
    else:
      user_output.append(f"Testing header {header}: Access {failed_symbol}")
      user_output.append(response)
      errors.add(response)
  generatedFiles = [f for f in os.listdir(localTestDir) if os.path.isfile(localTestDir + os.sep + f)]
  for filename in generatedFiles:
    os.remove(os.path.join(localTestDir, filename))
  # return the header with the most triples
  stringTools.deleteAllFilesInDirAndDir(localTestDir)
  if headerDict == {}:
    return None, errors
  else:
    return [k for k, v in sorted(headerDict.items(), key=lambda item: item[1], reverse=True)][0], errors


def downloadSource(uri, path, name, accHeader, encoding=None):
  try:
    acc_header = {'Accept': accHeader}
    response=requests.get(uri, headers=acc_header, timeout=30, allow_redirects=True)
    if encoding != None:
      response.encoding = encoding
    fileEnding = stringTools.getFileEnding(response)
    filePath = path + os.sep + name +"_type=orig"+ fileEnding
    if response.status_code < 400:
      with open(filePath, "w+") as ontfile:
        print(response.text, file=ontfile)
      return True, filePath, response
    else:
      return False, filePath, "Not Accessible - Status " + str(response.status_code)
  except requests.exceptions.TooManyRedirects as e:
    return False, "", str(e)
  except TimeoutError as e:
    return False, "", str(e)
  except requests.exceptions.ConnectionError as e:
    return False, "", str(e)
  except requests.exceptions.ReadTimeout as e:
    return False, "", str(e)
  except KeyboardInterrupt:
    sys.exit(19)
  except Exception as e:
    traceback.print_exc(file=sys.stdout)
    return False, "", str(e)


class ArchivoVersion():

  def __init__(self, nir, pathToOrigFile, response, testSuite, accessDate, bestHeader, logger, source, semanticVersion='1.0.0', devURI='', user_output=[]):
    self.nir = nir
    self.isDev = False if devURI == '' else True
    self.original_file = pathToOrigFile
    self.file_path, _ = os.path.split(pathToOrigFile)
    self.artifact_path, self.version = os.path.split(self.file_path)
    self.group_path, self.artifact = os.path.split(self.artifact_path)
    self.data_path, self.group = os.path.split(self.group_path)
    self.location_uri = response.url if devURI == '' else devURI
    self.reference_uri = devURI if self.isDev else nir
    self.response = response
    self.test_suite = testSuite
    self.access_date = accessDate
    self.best_header = bestHeader
    self.source = source
    self.semantic_version = semanticVersion
    self.user_output = user_output
    self.user_output.append(f'New Version for {self.reference_uri} ...')
    self.logger = logger
    if len(self.response.history) > 0:
      self.nir_header = str(self.response.history[0].headers)
    else:
      self.nir_header = ""
    self.location_url = self.response.url

  def generateFiles(self):
    raw_file_path = os.path.join(self.file_path, self.artifact)
    self.rapper_errors, rapperWarnings=ontoFiles.parseRDFSource(self.original_file, raw_file_path+"_type=parsed.nt", outputType="ntriples", deleteEmpty=True, sourceUri=self.nir, inputFormat=rdfHeadersMapping[self.best_header], logger=self.logger)
    self.user_output.append(f"Generating N-Triples File: {success_symbol}") if os.path.isfile(raw_file_path+"_type=parsed.nt") else self.user_output.append(f"Generating N-Triples File: {failed_symbol}")

    ontoFiles.parseRDFSource(raw_file_path+"_type=parsed.nt", raw_file_path+"_type=parsed.ttl", outputType="turtle", deleteEmpty=True, inputFormat='ntriples', logger=self.logger)
    self.user_output.append(f"Generating Turtle File: {success_symbol}") if os.path.isfile(raw_file_path+"_type=parsed.ttl") else self.user_output.append(f"Generating Turtle File: {failed_symbol}")
    
    ontoFiles.parseRDFSource(raw_file_path+"_type=parsed.nt", raw_file_path+"_type=parsed.owl", outputType="rdfxml", deleteEmpty=True, inputFormat='ntriples', logger=self.logger)
    self.user_output.append(f"Generating OWL File: {success_symbol}") if os.path.isfile(raw_file_path+"_type=parsed.owl") else self.user_output.append(f"Generating OWL File: {failed_symbol}")

    self.triples = ontoFiles.getParsedTriples(self.original_file, inputFormat=rdfHeadersMapping[self.best_header])[0]
    self.graph = inspectVocabs.getGraphOfVocabFile(raw_file_path+"_type=parsed.ttl")
    # shacl-validation
    # uses the turtle file since there were some problems with the blankNodes of rapper and rdflib
    # no empty parsed files since shacl is valid on empty files.
    self.conforms_licenseI, reportGraphLicense, reportTextLicense = self.test_suite.licenseViolationValidation(self.graph)
    with open(raw_file_path+"_type=shaclReport_validates=minLicense.ttl", "w+") as minLicenseFile:
      print(inspectVocabs.getTurtleGraph(reportGraphLicense), file=minLicenseFile)

    self.conforms_lode, reportGraphLode, reportTextLode = self.test_suite.lodeReadyValidation(self.graph)
    self.lode_severity = inspectVocabs.hackyShaclStringInpection(inspectVocabs.getTurtleGraph(reportGraphLode))
    with open(raw_file_path+"_type=shaclReport_validates=lodeMetadata.ttl", "w+") as lodeMetaFile:
      print(inspectVocabs.getTurtleGraph(reportGraphLode), file=lodeMetaFile)
    self.conforms_licenseII, reportGraphLicense2, reportTextLicense2 = self.test_suite.licenseWarningValidation(self.graph)
    with open(raw_file_path+"_type=shaclReport_validates=goodLicense.ttl", "w+") as advLicenseFile:
      print(inspectVocabs.getTurtleGraph(reportGraphLicense2), file=advLicenseFile) 
    # checks consistency with and without imports
    self.is_consistent, output = self.test_suite.getConsistency(raw_file_path+"_type=parsed.ttl", ignoreImports=False)
    self.is_consistent_noimports, outputNoImports = self.test_suite.getConsistency(raw_file_path+"_type=parsed.ttl", ignoreImports=True)
    with open(raw_file_path+"_type=pelletConsistency_imports=FULL.txt", "w+") as consistencyReport:
      print(output, file=consistencyReport)
    with open(raw_file_path+"_type=pelletConsistency_imports=NONE.txt", "w+") as consistencyReportNoImports:
      print(outputNoImports, file=consistencyReportNoImports)
    # print pellet info files
    with open(raw_file_path+"_type=pelletInfo_imports=FULL.txt", "w+") as pelletInfoFile:
      print(self.test_suite.getPelletInfo(raw_file_path+"_type=parsed.ttl", ignoreImports=False), file=pelletInfoFile)
    with open(raw_file_path+"_type=pelletInfo_imports=NONE.txt", "w+") as pelletInfoFileNoImports:
      print(self.test_suite.getPelletInfo(raw_file_path+"_type=parsed.ttl", ignoreImports=True), file=pelletInfoFileNoImports)
    # profile check for ontology
    stdout, stderr = self.test_suite.getProfileCheck(raw_file_path+"_type=parsed.ttl")
    with open(raw_file_path+"_type=profile.txt", "w+") as profileCheckFile:
      print(stderr + "\n" + stdout, file=profileCheckFile)

    # write the metadata json file
    ontoFiles.altWriteVocabInformation(pathToFile=raw_file_path+"_type=meta.json",
                                      definedByUri=self.reference_uri,
                                      lastModified=stringTools.getLastModifiedFromResponse(self.response),
                                      rapperErrors=self.rapper_errors,
                                      rapperWarnings=rapperWarnings,
                                      etag=stringTools.getEtagFromResponse(self.response),
                                      tripleSize=self.triples,
                                      bestHeader=self.best_header,
                                      licenseViolationsBool=self.conforms_licenseI,
                                      licenseWarningsBool=self.conforms_licenseII,
                                      consistentWithImports=self.is_consistent,
                                      consistentWithoutImports=self.is_consistent_noimports,
                                      lodeConform=self.conforms_lode,
                                      accessed= self.access_date,
                                      headerString=str(self.response.headers),
                                      nirHeader = self.nir_header,
                                      contentLenght=stringTools.getContentLengthFromResponse(self.response),
                                      semVersion=self.semantic_version,
                                      snapshot_url=self.location_url
                                      )
    # generate lode docu
    docustring, lode_error = getLodeDocuFile(self.location_uri, logger=self.logger)
    if docustring != None:
      self.user_output.append(f"Generating LODE-Docu: {success_symbol}")
      with open(raw_file_path+ "_type=generatedDocu.html", "w+") as docufile:
        print(docustring, file=docufile)
    else:
      user_output.append(f"Generating LODE-Docu: {failed_symbol}")
      user_output.append(lode_error)
    
  def generatePomAndDoc(self):
    datetime_obj= datetime.strptime(self.version, "%Y.%m.%d-%H%M%S")
    versionIRI = str(None)
    self.md_label=self.nir if not self.isDev else self.nir + " DEV"
    md_description=Template(docTemplates.description) if not self.isDev else Template(docTemplates.description_dev)
    md_comment=Template(docTemplates.default_explaination).safe_substitute(non_information_uri=self.reference_uri)
    license=None
    if self.graph != None:
      label = inspectVocabs.getLabel(self.graph)
      description = inspectVocabs.getDescription(self.graph)
      comment = inspectVocabs.getComment(self.graph)
      versionIRI = inspectVocabs.getOwlVersionIRI(self.graph)
      if label != None:
        self.md_label = label if not self.isDev else label + " DEV"

      if comment != None:
        md_comment = comment
      
      if description != None:
        md_description = md_description.safe_substitute(non_information_uri=self.nir, snapshot_url=self.location_uri, owl_version_iri=versionIRI, date=str(datetime_obj)) + "\n\n" + docTemplates.description_intro + "\n\n" + description
      else:
        md_description = md_description.safe_substitute(non_information_uri=self.nir, snapshot_url=self.location_url, owl_version_iri=versionIRI, date=str(datetime_obj))
      license =inspectVocabs.getLicense(self.graph)
      if isinstance(license, URIRef):
        license = str(license).strip("<>")
      elif isinstance(license, Literal):
        # if license is literal: error uri
        license = docTemplates.license_literal_uri

    childpomString = generatePoms.generateChildPom(groupId=self.group,
                                                    version=self.version,
                                                    artifactId=self.artifact,
                                                    packaging="jar",
                                                    license=license)
    with open(os.path.join(self.artifact_path, "pom.xml"), "w+") as childPomFile:
      print(childpomString, file=childPomFile)
    generatePoms.writeMarkdownDescription(self.artifact_path, self.artifact, self.md_label, md_comment, md_description)

  def handleTrackThis(self):
    if self.isDev:
      return None, None, None, None
    trackThisURI = inspectVocabs.getTrackThisURI(self.graph)
    if trackThisURI != None and self.location_uri != trackThisURI:
      self.user_output.append(f'Found a new develop stage URI: {trackThisURI}')
      return handleDevURI(self.nir, trackThisURI, self.data_path, self.test_suite, self.logger, user_output=self.user_output)
    else:
      return False, None, None, None

  def getdbVersion(self):
    consistencyCheck=lambda s: True if s == "Yes" else False
    return Version(
            version=datetime.strptime(self.version, "%Y.%m.%d-%H%M%S"),
            semanticVersion=self.semantic_version,
            stars=ontoFiles.measureStars(self.rapper_errors, self.conforms_licenseI, self.is_consistent, self.is_consistent_noimports, self.conforms_licenseII),
            triples=self.triples,
            parsing=True if self.rapper_errors == "" else False,
            licenseI=self.conforms_licenseI,
            licenseII=self.conforms_licenseII,
            consistency=consistencyCheck(self.is_consistent),
            lodeSeverity=self.lode_severity,
            ontology=self.reference_uri,
            )
  
  def getDatabaseEntry(self):
    if self.isDev:
      dbOntology = DevelopOntology(
        uri = self.reference_uri,
        source="DEV",
        accessDate=self.access_date,
        title=self.md_label,
        official=self.nir,
      )
    else:
      dbOntology = OfficialOntology(
        uri = self.reference_uri,
        source = self.source,
        accessDate = self.access_date,
        title = self.md_label,
        devel = None
      )
    dbVersion = self.getdbVersion()
    return dbOntology, dbVersion

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

def handleNewUri(vocab_uri, index, dataPath, source, isNIR, testSuite, logger, user_output=[]):
  # remove fragment
  vocab_uri = urldefrag(vocab_uri)[0]
  localDir = os.path.join(dataPath, "." + uuid.uuid4().hex)
  if not os.path.isdir(localDir):
    os.mkdir(localDir)
  # testing uri validity
  logger.info(f"Trying to validate {vocab_uri}")
  user_output.append(f"Trying to validate {vocab_uri}")
  groupId, artifact = stringTools.generateGroupAndArtifactFromUri(vocab_uri)
  if groupId == None or artifact == None:
    logger.warning(f"Malformed Uri {vocab_uri}")
    user_output.append(f"ERROR: Malformed URI {vocab_uri}")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR,"<br>".join(map(str, user_output)), None, None
  if checkIndexForUri(vocab_uri, index) != None:
    logger.info("Already known uri, skipping...")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    user_output.append(f"This Ontology is already in the Archivo index and can be found at <a href=https://databus.dbpedia.org/ontologies/{groupId}/{artifact}>https://databus.dbpedia.org/ontologies/{groupId}/{artifact}</a>")
    return False, isNIR, "<br>".join(map(str, user_output)), None, None
  
  # check robots.txt access
  allowed, message = checkRobot(vocab_uri)
  logger.info(f"Robot allowed: {allowed}")
  if not allowed:
    logger.warning(f"{archivoConfig.archivo_agent} not allowed")
    user_output.append(f"Archivo-Agent {archivoConfig.archivo_agent} is not allowed to access the ontology at <a href={vocab_uri}>{vocab_uri}</a>")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR, "<br>".join(map(str, user_output)), None, None
  
  user_output.append(f"Allowed Robot {archivoConfig.archivo_agent}: {success_symbol}")
  bestHeader, headerErrors = determineBestAccHeader(vocab_uri, dataPath, user_output=user_output)

  version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
  if bestHeader == None:
    user_output.append(f"Determinig the best header: {failed_symbol}")
    logger.error(f"Error in parsing: {headerErrors}")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR, "<br>".join(map(str, user_output)), None, None

  accessDate = datetime.now()
  user_output.append(f"Found best header: {bestHeader}")

  # downloading and parsing
  success, pathToFile, response = downloadSource(vocab_uri, localDir, "tmpOnt", bestHeader)
  if not success:
    logger.warning(f"Ontology {vocab_uri} is not accessible after best header was determined")
    user_output.append(f"Accessing URI {vocab_uri}: {failed_symbol}")
    user_output.append(response)
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR,"<br>".join(map(str, user_output)), None, None
  
  user_output.append(f"Accessing URI {vocab_uri}: {success_symbol}")
  rapperErrors, rapperWarnings = ontoFiles.parseRDFSource(pathToFile, os.path.join(localDir, "parsedSource.ttl"), "turtle", deleteEmpty=True, sourceUri=vocab_uri, inputFormat=rdfHeadersMapping[bestHeader], logger=logger)
  if not os.path.isfile(os.path.join(localDir, "parsedSource.ttl")):
    logger.error(f"There was an error in parsing ontology of {vocab_uri} even though triples could be found")
    user_output.append(f"Parse downloaded File: {failed_symbol}")
    user_output.append(f"There was an error in parsing ontology of {vocab_uri} even though triples could be found")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR, "<br>".join(map(str, user_output)), None, None

  # generating the graph and runnning the queries
  graph = inspectVocabs.getGraphOfVocabFile(os.path.join(localDir, "parsedSource.ttl"))
  if graph == None:
    logger.error(f"RDFlib couldn't parse the file of {vocab_uri}")
    user_output.append(f"Loading Graph in RDFlib: {failed_symbol}")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR, "<br>".join(map(str, user_output)), None, None
  
  try:
    real_ont_uri=inspectVocabs.getNIRUri(graph)
  except Exception:
    traceback.print_exc(file=sys.stderr)
    user_output.append(f"Finding Ontology URI: {failed_symbol}")
    user_output.append(traceback.format_exc())
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR, "<br>".join(map(str, user_output)), None, None

  if real_ont_uri == None:
    logger.info("Couldn't find ontology uri, trying isDefinedBy and inScheme...")
    user_output.append(f"Finding ontology URI: {failed_symbol}")
    user_output.append("Couldn't find ontology uri, trying isDefinedBy and inScheme...")
    real_ont_uri = inspectVocabs.getDefinedByUri(graph)
    if real_ont_uri == None:
      logger.info("No Ontology discoverable")
      user_output.append(f"Finding isDefinedBy: {failed_symbol}")
      user_output.append("The given URI does not contain a rdf:type owl:Ontology, rdfs:isDefinedBy, skos:inScheme or a skos:ConceptScheme triple")
      stringTools.deleteAllFilesInDirAndDir(localDir)
      return False, isNIR, "<br>".join(map(str, user_output)), None, None
    
    if not checkUriEquality(vocab_uri, str(real_ont_uri)):
      logger.info(f"Found isDefinedBy or skos uri {real_ont_uri}")
      user_output.append(f"Found isDefinedBy or skos uri {real_ont_uri}")
      stringTools.deleteAllFilesInDirAndDir(localDir)
      return handleNewUri(str(real_ont_uri), index, dataPath, testSuite=testSuite,source=source, isNIR=True, logger=logger, user_output=user_output) 
    else:
      logger.info("Uri already in index or self-defining non-ontology")
      user_output.append(f"Found isDefinedBy or skos uri {real_ont_uri}")
      user_output.append("Self-defining non-ontology.")
      stringTools.deleteAllFilesInDirAndDir(localDir)
      return False, isNIR, "<br>".join(map(str, user_output)), None, None
  
  user_output.append(f"Found ontology URI: {str(real_ont_uri)} {success_symbol}")
  isNIR=True
  if not checkUriEquality(vocab_uri, str(real_ont_uri)):
    logger.info(f"Non information uri differs from source uri, revalidate {str(real_ont_uri)}")
    user_output.append(f"Non information uri differs from source uri, revalidate {str(real_ont_uri)}")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    groupId, artifact = stringTools.generateGroupAndArtifactFromUri(str(real_ont_uri))
    if groupId == None or artifact == None:
      logger.warning(f"Malformed Uri {vocab_uri}")
      user_output.append(f"Malformed Uri {str(real_ont_uri)}")
      stringTools.deleteAllFilesInDirAndDir(localDir)
      return False, isNIR, "<br>".join(map(str, user_output)), None, None
    else:
      return handleNewUri(str(real_ont_uri), index, dataPath, source, True, testSuite=testSuite, logger=logger, user_output=user_output)
 

  # here we go if the uri is NIR and  its resolveable
  real_ont_uri = str(real_ont_uri)

  if isNIR and vocab_uri != real_ont_uri:
    logger.warning(f"unexpected value for real uri: {real_ont_uri}")

  logger.info(f"Found non-information URI: {real_ont_uri}")
  groupId, artifact = stringTools.generateGroupAndArtifactFromUri(real_ont_uri)
  if groupId == None or artifact == None:
    logger.warning(f"Malformed Uri {vocab_uri}")
    user_output.append(f"Malformed Uri {str(real_ont_uri)}")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR, str("<br>".join(map(str, user_output))), None, None


  if checkIndexForUri(real_ont_uri, index) != None:
    logger.info(f"Already known uri {real_ont_uri}")
    user_output.append(f"This Ontology is already in the Archivo index and can be found at <a href=https://databus.dbpedia.org/ontologies/{groupId}/{artifact}>https://databus.dbpedia.org/ontologies/{groupId}/{artifact}</a>")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, isNIR, "<br>".join(map(str, user_output)), None, None
  
  dbOntos = []
  dbVersions = []

  #index[real_ont_uri] = {"source" : source, "accessed" : accessDate}
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
  new_orig_file_path = os.path.join(newVersionPath, artifact+"_type=orig" + fileExt)
  os.rename(pathToFile, new_orig_file_path)
  # Generate database obj
  ontTitle = inspectVocabs.getLabel(graph)
  # new release
  logger.info("Generate new release files...")
  stringTools.deleteAllFilesInDirAndDir(localDir)
  new_version = ArchivoVersion(urldefrag(real_ont_uri)[0], new_orig_file_path, response, testSuite, accessDate, bestHeader, logger, source, user_output=user_output)
  new_version.generateFiles()
  new_version.generatePomAndDoc()
  trackThisSuccess, message, dbO, dbV = new_version.handleTrackThis()
  dbOntology, dbVersion = new_version.getDatabaseEntry()
  dbOntos.append(dbOntology)
  dbVersions.append(dbVersion)
  if trackThisSuccess:
    dbOntos.append(dbO)
    dbVersions.append(dbV)
  
  logger.info("Deploying the data to the databus...")
  returncode, deployLog =generatePoms.callMaven(os.path.join(dataPath, groupId, artifact, "pom.xml"), "deploy")
  
  if returncode > 0:
    logger.error("There was an Error deploying to the databus")
    user_output.append(f"Deploying to Databus: {failed_symbol}")
    user_output.append(deployLog)
    logger.error(deployLog)
    return False, isNIR, "<br>".join(map(str, user_output)), None, None
  else:
    logger.info(f"Successfully deployed the new ontology {real_ont_uri}")
    user_output.append(f"Deploying to Databus: {success_symbol}")
    user_output.append(f"Added the Ontology to Archivo, should be accessable at <a href=https://databus.dbpedia.org/ontologies/{groupId}/{artifact}>https://databus.dbpedia.org/ontologies/{groupId}/{artifact}</a> soon")
    dbOntos.append(dbOntology)
    dbVersions.append(dbVersion)
    return True, isNIR, "<br>".join(map(str, user_output)), dbOntos, dbVersions


def handleDevURI(nir, sourceURI, dataPath, testSuite, logger, user_output=[]):
  # remove fragment
  sourceURI = urldefrag(sourceURI)[0]
  localDir = os.path.join(dataPath, "." + uuid.uuid4().hex)
  if not os.path.isdir(localDir):
    os.mkdir(localDir)
  # testing uri validity
  logger.info(f"Trying to validate {sourceURI}")

  # check robots.txt access
  allowed, message = checkRobot(sourceURI)
  logger.info(f"Robot allowed: {allowed}")
  if not allowed:
    logger.warning(f"{archivoConfig.archivo_agent} not allowed")
    user_output.append(f"Archivo-Agent {archivoConfig.archivo_agent} is not allowed to access the ontology at <a href={sourceURI}>{sourceURI}</a>")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, "<br>".join(map(str, user_output)), None, None
  
  user_output.append(f"Allowed Robot {archivoConfig.archivo_agent}: {success_symbol}")
  bestHeader, headerErrors = determineBestAccHeader(sourceURI, dataPath, user_output=user_output)

  version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
  if bestHeader == None:
    user_output.append(f"Determinig the best header: {failed_symbol}")
    logger.error(f"Error in parsing: {headerErrors}")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, "<br>".join(map(str, user_output)), None, None

  accessDate = datetime.now()
  user_output.append(f"Found best header: {bestHeader}")

  # downloading and parsing
  success, pathToFile, response = downloadSource(sourceURI, localDir, "tmpOnt", bestHeader)
  if not success:
    logger.warning(f"Ontology {sourceURI} is not accessible after best header was determined")
    user_output.append(f"Accessing URI {sourceURI}: {failed_symbol}")
    user_output.append(response)
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, "<br>".join(map(str, user_output)), None, None
  
  user_output.append(f"Accessing URI {sourceURI}: {success_symbol}")
  rapperErrors, rapperWarnings = ontoFiles.parseRDFSource(pathToFile, os.path.join(localDir, "parsedSource.ttl"), "turtle", deleteEmpty=True, sourceUri=nir, inputFormat=rdfHeadersMapping[bestHeader], logger=logger)
  if not os.path.isfile(os.path.join(localDir, "parsedSource.ttl")):
    logger.error(f"There was an error in parsing ontology of {sourceURI} even though triples could be found")
    user_output.append(f"Parse downloaded File: {failed_symbol}")
    user_output.append(f"There was an error in parsing ontology of {sourceURI} even though triples could be found")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, "<br>".join(map(str, user_output)), None, None

  
  graph = inspectVocabs.getGraphOfVocabFile(os.path.join(localDir, "parsedSource.ttl"))
  if graph == None:
    logger.error(f"RDFlib couldn't parse the file of {sourceURI}")
    user_output.append(f"Loading Graph in RDFlib: {failed_symbol}")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, "<br>".join(map(str, user_output)), None, None
  
  # here we go if the uri is NIR and  its resolveable
  
  groupId, artifact = stringTools.generateGroupAndArtifactFromUri(nir, dev=True)
  if groupId == None or artifact == None:
    logger.warning(f"Malformed Uri {sourceURI}")
    user_output.append(f"Malformed Uri {str(nir)}")
    stringTools.deleteAllFilesInDirAndDir(localDir)
    return False, str("<br>".join(map(str, user_output))), None, None
  
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
  # Generate database obj
  ontTitle = inspectVocabs.getLabel(graph)
  dbOntology = DevelopOntology(
    uri = sourceURI,
    source="DEV",
    accessDate=accessDate,
    title=ontTitle + " DEV" if ontTitle != None else nir + " DEV",
    official=nir,
  )
  # new release
  logger.info("Generate new release files...")
  new_version = ArchivoVersion(nir, os.path.join(newVersionPath, artifact+"_type=orig" + fileExt), response, testSuite, accessDate, bestHeader, logger, 'DEV', user_output=user_output, devURI=sourceURI)
  new_version.generateFiles()
  new_version.generatePomAndDoc()
  dbVersion = new_version.getdbVersion()
  #dbVersion = generateNewRelease(nir, newVersionPath, artifact, os.path.join(newVersionPath, artifact+"_type=orig" + fileExt), bestHeader, response, accessDate, testSuite, logger=logger, user_output=user_output, devURI=sourceURI)
  # index writing
  #ontoFiles.writeIndexJson(index)
  stringTools.deleteAllFilesInDirAndDir(localDir)
  
  logger.info("Deploying the data to the databus...")
  returncode, deployLog =generatePoms.callMaven(os.path.join(dataPath, groupId, artifact, "pom.xml"), "deploy")
  
  if returncode > 0:
    logger.error("There was an Error deploying to the databus")
    user_output.append(f"Deploying to Databus: {failed_symbol}")
    user_output.append(deployLog)
    logger.error(deployLog)
    return False, "<br>".join(map(str, user_output)), dbOntology, dbVersion
  else:
    logger.info(f"Successfully deployed the new dev ontology {sourceURI}")
    user_output.append(f"Deploying to Databus: {success_symbol}")
    user_output.append(f"Added the Ontology to Archivo, should be accessable at <a href=https://databus.dbpedia.org/ontologies/{groupId}/{artifact}>https://databus.dbpedia.org/ontologies/{groupId}/{artifact}</a> soon")
    return True, "<br>".join(map(str, user_output)), dbOntology, dbVersion


def getLovUrls():
  req = requests.get(lovOntologiesURL)
  json_data=req.json()
  return [dataObj["uri"] for dataObj in json_data]


def getPrefixURLs():
  req = requests.get(prefixccURLs)
  json_data = req.json()
  prefixOntoDict = json_data["@context"]
  return [prefixOntoDict[prefix] for prefix in prefixOntoDict]

# returns a distinct list of VOID classes and properties
def get_VOID_URIs():
  query = "\n".join((
        "PREFIX prov: <http://www.w3.org/ns/prov#>",
        "PREFIX void: <http://rdfs.org/ns/void#>",
        "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>",
        "PREFIX dcat:   <http://www.w3.org/ns/dcat#>",
        "PREFIX dct:    <http://purl.org/dc/terms/>",
        "SELECT DISTINCT ?URI {",
        "?mod prov:generated ?generated .",
        "{ SELECT ?URI WHERE {",
        "?generated void:propertyPartition [",
        "void:property ?URI",
        "] .",
        "}",
        "}",
        "UNION",
        "{ SELECT DISTINCT ?URI WHERE {",
        "?generated void:classPartition [",
        "void:class ?URI",
        "] .",
        "}",
        "}",
        "}",
        )
    )
  try:
    sparql = SPARQLWrapper(mod_endpoint)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
  except e:
    return None
  print(results)
  if not 'results' in results:
    return None
  return [binding['URI']['value'] for binding in results['results']['bindings']]



def testLOVInfo():
  req = requests.get("https://lov.linkeddata.es/dataset/lov/api/v2/vocabulary/info?vocab=schema")
  json_data = req.json()
  for versionObj in json_data["versions"]:
    resourceUrl = versionObj["fileURL"]
    version = versionObj["name"]
    print("Download source:", resourceUrl)
    success, pathToFile, response = downloadSource(resourceUrl, ".", "tempOnt"+version, "text/rdf+n3")
    print(success)