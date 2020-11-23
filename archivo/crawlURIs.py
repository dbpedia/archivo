import requests
import os
import sys
import traceback
from datetime import datetime
from utils import (
    stringTools,
    generatePoms,
    ontoFiles,
    inspectVocabs,
    archivoConfig,
    docTemplates,
)
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse, urldefrag, quote
from rdflib.term import Literal, URIRef
from string import Template
from SPARQLWrapper import SPARQLWrapper, JSON


# mod uris
mod_endpoint = "http://akswnc7.informatik.uni-leipzig.de:9062/sparql/"

# url to get all vocabs and their resource
lovOntologiesURL = "https://lov.linkeddata.es/dataset/lov/api/v2/vocabulary/list"

# prefix.cc complete urls
prefixccURLs = "http://prefix.cc/context"

# url for the lodo docu service
lodeServiceUrl = "https://w3id.org/lode/owlapi/"

# url for the oops rest service
oopsServiceUrl = " http://oops.linkeddata.es/rest"

# possible headers for rdf-data
rdfHeaders = [
    "application/rdf+xml",
    "application/ntriples",
    "text/turtle",
    "application/html",
]
rdfHeadersMapping = {
    "application/rdf+xml": "rdfxml",
    "application/ntriples": "ntriples",
    "text/turtle": "turtle",
    "application/xhtml": "rdfa",
}

file_ending_mapping = {
    "application/rdf+xml": "owl",
    "application/ntriples": "nt",
    "text/turtle": "ttl",
    "*/*": "file",
}


# determine_best_content_type
# function used by
#
def determine_best_content_type(uri, user_output=[]):
    header_dict = {}
    for header in rdfHeadersMapping:
        response, error = download_rdf_string(uri, acc_header=header)
        if error is None:
            try:
                triple_number, rapper_errors = ontoFiles.get_triples_from_rdf_string(
                    response.text, uri, input_type=rdfHeadersMapping[header]
                )
            except Exception as e:
                print(
                    f"There was an error parsing {uri} with header {header}: {str(e)}"
                )
                continue
            if triple_number is not None and triple_number > 0:
                user_output.append(
                    {
                        "status": True,
                        "step": f"Parsing with header {header}",
                        "message": f"Triples: {str(triple_number)}",
                    }
                )
                header_dict[header] = (response, triple_number)
            else:
                if len(rapper_errors) > 20:
                    rapper_errors = rapper_errors[:20]
                user_output.append(
                    {
                        "status": False,
                        "step": f"Parsing with header {header}",
                        "message": "Triples: {} \n{}".format(str(triple_number), '\n'.join(rapper_errors[:20])),
                    }
                )
        else:
            user_output.append(
                {
                    "status": False,
                    "step": f"Parsing with header {header}",
                    "message": f"{error}",
                }
            )
    if header_dict == {}:
        return None, None, None
    best_header = [
        k
        for k, v in sorted(
            header_dict.items(), key=lambda item: item[1][1], reverse=True
        )
    ][0]
    rdf_string, triple_number = header_dict[best_header]
    return best_header, rdf_string, triple_number


def download_rdf_string(uri, acc_header, encoding="utf-8"):
    try:
        headers = {"Accept": acc_header}
        response = requests.get(uri, headers=headers, timeout=30, allow_redirects=True)
        if encoding is not None:
            response.encoding = encoding
        if response.status_code < 400:
            return response, None
        else:
            return response, "Not Accessible - Status " + str(response.status_code)
    except requests.exceptions.TooManyRedirects as e:
        return None, str(e)
    except TimeoutError as e:
        return None, str(e)
    except requests.exceptions.ConnectionError as e:
        return None, str(e)
    except requests.exceptions.ReadTimeout as e:
        return None, str(e)
    except KeyboardInterrupt:
        sys.exit(19)
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
        return None, str(e)


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
    oopsXml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "   <OOPSRequest>\n"
        "   <OntologyURI></OntologyURI>\n"
        f"    <OntologyContent><![CDATA[\n{parsedRdfString}]]></OntologyContent>\n"
        "   <Pitfalls></Pitfalls>\n"
        "   <OutputFormat>RDF/XML</OutputFormat>\n"
        "</OOPSRequest>"
    )
    headers = {"Content-Type": "application/xml"}
    try:
        response = requests.post(
            oopsServiceUrl, data=oopsXml.encode("utf-8"), headers=headers, timeout=30
        )
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
    robotsUrl = parsedUrl.scheme + "://" + parsedUrl.netloc + "/robots.txt"
    try:
        req = requests.get(url=robotsUrl)
    except requests.exceptions.SSLError:
        return True, "SSL error"
    except requests.exceptions.ConnectionError:
        return True, "Connection Error"
    except requests.exceptions.InvalidSchema:
        return True, f"Invalid schema: {robotsUrl}"
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


def downloadSource(uri, path, name, accHeader, encoding="utf-8"):
    try:
        acc_header = {"Accept": accHeader}
        response = requests.get(
            uri, headers=acc_header, timeout=30, allow_redirects=True
        )
        if encoding is not None:
            response.encoding = encoding
        fileEnding = stringTools.getFileEnding(response)
        filePath = path + os.sep + name + "_type=orig" + fileEnding
        if response.status_code < 400:
            with open(filePath, "w+") as ontfile:
                print(response.text, file=ontfile)
            return True, filePath, response
        else:
            return (
                False,
                filePath,
                "Not Accessible - Status " + str(response.status_code),
            )
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


class ArchivoVersion:
    def __init__(
        self,
        nir,
        pathToOrigFile,
        response,
        testSuite,
        accessDate,
        bestHeader,
        logger,
        source,
        semanticVersion="1.0.0",
        devURI="",
        user_output=[],
    ):
        self.nir = nir
        self.isDev = False if devURI == "" else True
        self.original_file = pathToOrigFile
        self.file_path, _ = os.path.split(pathToOrigFile)
        self.artifact_path, self.version = os.path.split(self.file_path)
        self.group_path, self.artifact = os.path.split(self.artifact_path)
        self.data_path, self.group = os.path.split(self.group_path)
        self.location_uri = response.url if devURI == "" else devURI
        self.reference_uri = devURI if self.isDev else nir
        self.response = response
        self.test_suite = testSuite
        self.access_date = accessDate
        self.best_header = bestHeader
        self.source = source
        self.semantic_version = semanticVersion
        self.user_output = user_output
        self.logger = logger
        if len(self.response.history) > 0:
            self.nir_header = str(self.response.history[0].headers)
        else:
            self.nir_header = ""
        self.location_url = self.response.url

    def generateFiles(self):
        raw_file_path = os.path.join(self.file_path, self.artifact)
        self.rapper_errors, rapperWarnings = ontoFiles.parseRDFSource(
            self.original_file,
            raw_file_path + "_type=parsed.nt",
            outputType="ntriples",
            deleteEmpty=True,
            sourceUri=self.nir,
            inputFormat=rdfHeadersMapping[self.best_header],
            logger=self.logger,
        )
        nt_generated = (
            True if os.path.isfile(raw_file_path + "_type=parsed.nt") else False
        )

        ontoFiles.parseRDFSource(
            self.original_file,
            raw_file_path + "_type=parsed.ttl",
            outputType="turtle",
            deleteEmpty=True,
            inputFormat=rdfHeadersMapping[self.best_header],
            logger=self.logger,
        )
        ttl_generated = (
            True if os.path.isfile(raw_file_path + "_type=parsed.ttl") else False
        )

        ontoFiles.parseRDFSource(
            self.original_file,
            raw_file_path + "_type=parsed.owl",
            outputType="rdfxml",
            deleteEmpty=True,
            inputFormat=rdfHeadersMapping[self.best_header],
            logger=self.logger,
        )
        owl_generated = (
            True if os.path.isfile(raw_file_path + "_type=parsed.owl") else False
        )
        self.user_output.append(
            {
                "status": True,
                "step": "Generate Formats",
                "message": f"N-triples: {nt_generated}<br>Turtle: {ttl_generated}<br>RDF+XML: {owl_generated}",
            }
        )
        self.triples = ontoFiles.getParsedTriples(
            self.original_file, inputFormat=rdfHeadersMapping[self.best_header]
        )[0]
        self.graph = inspectVocabs.getGraphOfVocabFile(
            raw_file_path + "_type=parsed.ttl"
        )
        # shacl-validation
        # uses the turtle file since there were some problems with the blankNodes of rapper and rdflib
        # no empty parsed files since shacl is valid on empty files.
        (
            self.conforms_licenseI,
            reportGraphLicense,
            reportTextLicense,
        ) = self.test_suite.licenseViolationValidation(self.graph)
        with open(
            raw_file_path + "_type=shaclReport_validates=minLicense.ttl", "w+"
        ) as minLicenseFile:
            print(inspectVocabs.getTurtleGraph(reportGraphLicense), file=minLicenseFile)

        (
            self.conforms_lode,
            reportGraphLode,
            reportTextLode,
        ) = self.test_suite.lodeReadyValidation(self.graph)
        self.lode_severity = inspectVocabs.hackyShaclStringInpection(
            inspectVocabs.getTurtleGraph(reportGraphLode)
        )
        with open(
            raw_file_path + "_type=shaclReport_validates=lodeMetadata.ttl", "w+"
        ) as lodeMetaFile:
            print(inspectVocabs.getTurtleGraph(reportGraphLode), file=lodeMetaFile)
        (
            self.conforms_licenseII,
            reportGraphLicense2,
            reportTextLicense2,
        ) = self.test_suite.licenseWarningValidation(self.graph)
        with open(
            raw_file_path + "_type=shaclReport_validates=goodLicense.ttl", "w+"
        ) as advLicenseFile:
            print(
                inspectVocabs.getTurtleGraph(reportGraphLicense2), file=advLicenseFile
            )
        # checks consistency with and without imports
        self.is_consistent, output = self.test_suite.getConsistency(
            raw_file_path + "_type=parsed.ttl", ignoreImports=False
        )
        self.is_consistent_noimports, outputNoImports = self.test_suite.getConsistency(
            raw_file_path + "_type=parsed.ttl", ignoreImports=True
        )
        with open(
            raw_file_path + "_type=pelletConsistency_imports=FULL.txt", "w+"
        ) as consistencyReport:
            print(output, file=consistencyReport)
        with open(
            raw_file_path + "_type=pelletConsistency_imports=NONE.txt", "w+"
        ) as consistencyReportNoImports:
            print(outputNoImports, file=consistencyReportNoImports)
        # print pellet info files
        with open(
            raw_file_path + "_type=pelletInfo_imports=FULL.txt", "w+"
        ) as pelletInfoFile:
            print(
                self.test_suite.getPelletInfo(
                    raw_file_path + "_type=parsed.ttl", ignoreImports=False
                ),
                file=pelletInfoFile,
            )
        with open(
            raw_file_path + "_type=pelletInfo_imports=NONE.txt", "w+"
        ) as pelletInfoFileNoImports:
            print(
                self.test_suite.getPelletInfo(
                    raw_file_path + "_type=parsed.ttl", ignoreImports=True
                ),
                file=pelletInfoFileNoImports,
            )
        # profile check for ontology
        stdout, stderr = self.test_suite.getProfileCheck(
            raw_file_path + "_type=parsed.ttl"
        )
        with open(raw_file_path + "_type=profile.txt", "w+") as profileCheckFile:
            print(stderr + "\n" + stdout, file=profileCheckFile)

        # write the metadata json file
        ontoFiles.altWriteVocabInformation(
            pathToFile=raw_file_path + "_type=meta.json",
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
            accessed=self.access_date,
            headerString=str(self.response.headers),
            nirHeader=self.nir_header,
            contentLenght=stringTools.getContentLengthFromResponse(self.response),
            semVersion=self.semantic_version,
            snapshot_url=self.location_url,
        )
        # generate lode docu
        docustring, lode_error = getLodeDocuFile(self.location_uri, logger=self.logger)
        if docustring is None:
            with open(raw_file_path + "_type=generatedDocu.html", "w+") as docufile:
                print(docustring, file=docufile)

    def generatePomAndDoc(self):
        datetime_obj = datetime.strptime(self.version, "%Y.%m.%d-%H%M%S")
        versionIRI = str(None)
        self.md_label = self.nir if not self.isDev else self.nir + " DEV"
        md_description = (
            Template(docTemplates.description)
            if not self.isDev
            else Template(docTemplates.description_dev)
        )
        md_comment = Template(docTemplates.default_explaination).safe_substitute(
            non_information_uri=self.reference_uri
        )
        license = None
        if self.graph is not None:
            label = inspectVocabs.getLabel(self.graph)
            description = inspectVocabs.getDescription(self.graph)
            comment = inspectVocabs.getComment(self.graph)
            versionIRI = inspectVocabs.getOwlVersionIRI(self.graph)
            if label is not None:
                self.md_label = label if not self.isDev else label + " DEV"

            if comment is not None:
                md_comment = comment

            if description is not None:
                md_description = (
                    md_description.safe_substitute(
                        non_information_uri=self.nir,
                        snapshot_url=self.location_uri,
                        owl_version_iri=versionIRI,
                        date=str(datetime_obj),
                    )
                    + "\n\n"
                    + docTemplates.description_intro
                    + "\n\n"
                    + description
                )
            else:
                md_description = md_description.safe_substitute(
                    non_information_uri=self.nir,
                    snapshot_url=self.location_url,
                    owl_version_iri=versionIRI,
                    date=str(datetime_obj),
                )
            license = inspectVocabs.getLicense(self.graph)
            if isinstance(license, URIRef):
                license = str(license).strip("<>")
            elif isinstance(license, Literal):
                # if license is literal: error uri
                license = docTemplates.license_literal_uri

        childpomString = generatePoms.generateChildPom(
            groupId=self.group,
            version=self.version,
            artifactId=self.artifact,
            packaging="jar",
            license=license,
        )
        with open(os.path.join(self.artifact_path, "pom.xml"), "w+") as childPomFile:
            print(childpomString, file=childPomFile)
        generatePoms.writeMarkdownDescription(
            self.artifact_path, self.artifact, self.md_label, md_comment, md_description
        )

    def handleTrackThis(self):
        if self.isDev:
            return None, None, None
        trackThisURI = inspectVocabs.getTrackThisURI(self.graph)
        if trackThisURI is None and self.location_uri != trackThisURI:
            self.user_output.append(
                {
                    "status": True,
                    "step": "Check for Dev version link",
                    "message": f"Found dev version at: {trackThisURI}",
                }
            )
            return handleDevURI(
                self.nir,
                trackThisURI,
                self.data_path,
                self.test_suite,
                self.logger,
                user_output=self.user_output,
            )
        else:
            return False, None, None


# ======== END OF CLASS ================


def handleNewUri(
    vocab_uri, index, dataPath, source, isNIR, testSuite, logger, user_output=[]
):
    # remove fragment
    vocab_uri = urldefrag(vocab_uri)[0]
    # testing uri validity
    logger.info(f"Trying to validate {vocab_uri}")
    groupId, artifact = stringTools.generateGroupAndArtifactFromUri(vocab_uri)
    if groupId is None or artifact is None:
        logger.warning(f"Malformed Uri {vocab_uri}")
        user_output.append(
            {
                "status": False,
                "step": "URI check",
                "message": f"ERROR: Malformed URI {vocab_uri}",
            }
        )
        return False, isNIR, None
    if stringTools.get_uri_from_index(vocab_uri, index) is not None:
        logger.info("Already known uri, skipping...")
        user_output.append(
            {
                "status": True,
                "step": "Index check",
                "message": f"This Ontology is already in the Archivo index and can be found at <a href=/info?o={quote(vocab_uri)}>here</a>",
            }
        )
        return False, isNIR, None

    # check robots.txt access
    allowed, message = checkRobot(vocab_uri)
    logger.info(f"Robot allowed: {allowed}")
    if not allowed:
        logger.warning(f"{archivoConfig.archivo_agent} not allowed")
        user_output.append(
            {
                "status": False,
                "step": "Robot allowed check",
                "message": f"Archivo-Agent {archivoConfig.archivo_agent} is not allowed to access the ontology at <a href={vocab_uri}>{vocab_uri}</a>",
            }
        )
        return False, isNIR, None

    user_output.append(
        {
            "status": True,
            "step": "Robot allowed check",
            "message": f"Archivo-Agent {archivoConfig.archivo_agent} is allowed.",
        }
    )
    # load the best header with response and triple number
    bestHeader, response, triple_number = determine_best_content_type(
        vocab_uri, user_output=user_output
    )

    version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
    if bestHeader is None:
        user_output.append(
            {
                "status": False,
                "step": "Find Best Header",
                "message": "No RDF content detectable.",
            }
        )
        return False, isNIR, None

    accessDate = datetime.now()
    user_output.append(
        {
            "status": True,
            "step": "Find Best Header",
            "message": f"Best Header: {bestHeader} with {triple_number} triples",
        }
    )

    # generating the graph and runnning the queries
    try:
        graph = inspectVocabs.get_graph_of_string(response.text, bestHeader)
    except Exception:
        logger.error("Exception in rdflib parsing", exc_info=True)
        user_output.append(
            {
                "status": False,
                "step": "Load Graph in rdflib",
                "message": f"RDFlib couldn't parse the file of {vocab_uri}. Reason: {traceback.format_exc()}",
            }
        )
        return False, isNIR, None

    try:
        real_ont_uri = inspectVocabs.getNIRUri(graph)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        user_output.append(
            {
                "status": False,
                "step": "Determine non-information resource",
                "message": traceback.format_exc(),
            }
        )
        return False, isNIR, None

    if real_ont_uri is None:
        user_output.append(
            {
                "status": False,
                "step": "Determine non-information resource",
                "message": "Neither owl:Ontology or skos:ConceptScheme",
            }
        )
        real_ont_uri = inspectVocabs.getDefinedByUri(graph)
        if real_ont_uri is None:
            logger.info("No Ontology discoverable")
            user_output.append(
                {
                    "status": False,
                    "step": "Looking for linked ontologies",
                    "message": "The given URI does not contain a rdf:type owl:Ontology, rdfs:isDefinedBy, skos:inScheme or a skos:ConceptScheme triple",
                }
            )
            return False, isNIR, None

        if not stringTools.check_uri_equality(vocab_uri, str(real_ont_uri)):
            user_output.append(
                {
                    "status": True,
                    "step": "Looking for linked ontologies",
                    "message": f"Found linked URI: {real_ont_uri}",
                }
            )
            return handleNewUri(
                str(real_ont_uri),
                index,
                dataPath,
                testSuite=testSuite,
                source=source,
                isNIR=True,
                logger=logger,
                user_output=user_output,
            )
        else:
            user_output.append(
                {
                    "status": False,
                    "step": "Looking for linked ontologies",
                    "message": "Self defining non-ontology.",
                }
            )
            return False, isNIR, None

    user_output.append(
        {
            "status": True,
            "step": "Determine non-information resource",
            "message": f"Found non-information resource: {real_ont_uri}",
        }
    )
    isNIR = True
    if not stringTools.check_uri_equality(vocab_uri, str(real_ont_uri)):
        user_output.append(
            {
                "status": False,
                "step": "URI equality check",
                "message": f"{real_ont_uri} differs from {vocab_uri}",
            }
        )
        return handleNewUri(
            str(real_ont_uri),
            index,
            dataPath,
            source,
            True,
            testSuite=testSuite,
            logger=logger,
            user_output=user_output,
        )

    # here we go if the uri is NIR and  its resolveable
    real_ont_uri = str(real_ont_uri)

    if isNIR and vocab_uri != real_ont_uri:
        logger.warning(f"unexpected value for real uri: {real_ont_uri}")

    groupId, artifact = stringTools.generateGroupAndArtifactFromUri(real_ont_uri)
    if groupId is None or artifact is None:
        logger.warning(f"Malformed Uri {vocab_uri}")
        user_output.append(
            {
                "status": False,
                "step": "URI Check",
                "message": f"Malformed Uri {vocab_uri}",
            }
        )
        return False, isNIR, None

    if stringTools.get_uri_from_index(real_ont_uri, index) is None:
        logger.info(f"Already known uri {real_ont_uri}")
        user_output.append(
            {
                "status": True,
                "step": "Index check",
                "message": f"This Ontology is already in the Archivo index and can be found at <a href=/info?o={urlencode(vocab_uri)}>here</a>",
            }
        )
        return False, isNIR, None

    newVersionPath = os.path.join(dataPath, groupId, artifact, version)
    os.makedirs(newVersionPath, exist_ok=True)
    # generate parent pom
    if not os.path.isfile(os.path.join(dataPath, groupId, "pom.xml")):
        pomString = generatePoms.generateParentPom(
            groupId=groupId,
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
    fileExt = file_ending_mapping[bestHeader]
    new_orig_file_path = os.path.join(
        newVersionPath, artifact + "_type=orig." + fileExt
    )
    with open(new_orig_file_path, "w+") as new_orig_file:
        print(response.text, file=new_orig_file)
    # new release
    logger.info("Generate new release files...")
    new_version = ArchivoVersion(
        urldefrag(real_ont_uri)[0],
        new_orig_file_path,
        response,
        testSuite,
        accessDate,
        bestHeader,
        logger,
        source,
        user_output=user_output,
    )
    new_version.generateFiles()
    new_version.generatePomAndDoc()

    logger.info("Deploying the data to the databus...")
    returncode, deployLog = generatePoms.callMaven(
        os.path.join(dataPath, groupId, artifact, "pom.xml"), "deploy"
    )

    if returncode > 0:
        logger.error("There was an Error deploying to the databus")
        user_output.append(
            {"status": False, "step": "Deploy to DBpedia Databus", "message": deployLog}
        )
        logger.error(deployLog)
        return False, isNIR, None
    else:
        logger.info(f"Successfully deployed the new ontology {real_ont_uri}")
        user_output.append(
            {
                "status": True,
                "step": "Deploy to DBpedia Databus",
                "message": f"Deployed the Ontology to the DBpedia Databus, should be accessable at <a href=https://databus.dbpedia.org/ontologies/{groupId}/{artifact}>https://databus.dbpedia.org/ontologies/{groupId}/{artifact}</a> soon",
            }
        )
        return True, isNIR, new_version


def handleDevURI(nir, sourceURI, dataPath, testSuite, logger, user_output=[]):
    # remove fragment
    sourceURI = urldefrag(sourceURI)[0]
    # testing uri validity
    logger.info(f"Trying to validate {sourceURI}")

    # check robots.txt access
    allowed, message = checkRobot(sourceURI)
    logger.info(f"Robot allowed: {allowed}")
    if not allowed:
        logger.warning(f"{archivoConfig.archivo_agent} not allowed")
        user_output.append(
            {
                "status": False,
                "step": "Robot allowed check",
                "message": f"Archivo-Agent {archivoConfig.archivo_agent} is not allowed to access the ontology at <a href={vocab_uri}>{vocab_uri}</a>",
            }
        )
        return False, None

    user_output.append(
        user_output.append(
            {
                "status": True,
                "step": "Robot allowed check",
                "message": f"Archivo-Agent {archivoConfig.archivo_agent} is allowed.",
            }
        )
    )
    # load the best header with response and triple number
    bestHeader, response, triple_number = determine_best_content_type(
        nir, user_output=user_output
    )

    version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
    if bestHeader is None:
        user_output.append(
            {
                "status": False,
                "step": "Find Best Header",
                "message": f"No RDF content detectable.",
            }
        )
        return False, None

    accessDate = datetime.now()

    # generating the graph and runnning the queries
    try:
        _ = inspectVocabs.get_graph_of_string(response.text, bestHeader)
    except Exception:
        logger.error("Exception in rdflib parsing", exc_info=True)
        user_output.append(
            {
                "status": False,
                "step": "Load Graph in rdflib",
                "message": f"RDFlib couldn't parse the file of {nir}. Reason: {traceback.format_exc()}",
            }
        )
        return False, None

    # here we go if the uri is NIR and  its resolveable

    groupId, artifact = stringTools.generateGroupAndArtifactFromUri(nir, dev=True)
    if groupId is None or artifact is None:
        logger.warning(f"Malformed Uri {sourceURI}")
        user_output.append(
            user_output.append(
                {
                    "status": False,
                    "step": "URI Check",
                    "message": f"Malformed Uri {str(nir)}",
                }
            )
        )
        return False, None

    newVersionPath = os.path.join(dataPath, groupId, artifact, version)
    os.makedirs(newVersionPath, exist_ok=True)
    # generate parent pom
    if not os.path.isfile(os.path.join(dataPath, groupId, "pom.xml")):
        pomString = generatePoms.generateParentPom(
            groupId=groupId,
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
    fileExt = file_ending_mapping[bestHeader]
    new_orig_file_path = os.path.join(
        newVersionPath, artifact + "_type=orig." + fileExt
    )
    with open(new_orig_file_path, "w+") as new_orig_file:
        print(response.text, file=new_orig_file)
    # new release
    logger.info("Generate new release files...")
    new_version = ArchivoVersion(
        nir,
        os.path.join(newVersionPath, artifact + "_type=orig" + fileExt),
        response,
        testSuite,
        accessDate,
        bestHeader,
        logger,
        "DEV",
        user_output=user_output,
        devURI=sourceURI,
    )
    new_version.generateFiles()
    new_version.generatePomAndDoc()

    logger.info("Deploying the data to the databus...")
    returncode, deployLog = generatePoms.callMaven(
        os.path.join(dataPath, groupId, artifact, "pom.xml"), "deploy"
    )

    if returncode > 0:
        logger.error("There was an Error deploying to the databus")
        user_output.append(
            {"status": False, "step": "Deploy to DBpedia Databus", "message": deployLog}
        )
        logger.error(deployLog)
        return False, None
    else:
        logger.info(f"Successfully deployed the new dev ontology {sourceURI}")
        user_output.append(
            {
                "status": True,
                "step": "Deploy to DBpedia Databus",
                "message": f"Deployed the Ontology to the DBpedia Databus, should be accessable at <a href=https://databus.dbpedia.org/ontologies/{groupId}/{artifact}>https://databus.dbpedia.org/ontologies/{groupId}/{artifact}</a> soon",
            }
        )
        return True, new_version


def getLovUrls():
    req = requests.get(lovOntologiesURL)
    json_data = req.json()
    return [dataObj["uri"] for dataObj in json_data]


def getPrefixURLs():
    req = requests.get(prefixccURLs)
    json_data = req.json()
    prefixOntoDict = json_data["@context"]
    return [prefixOntoDict[prefix] for prefix in prefixOntoDict]


# returns a distinct list of VOID classes and properties
def get_VOID_URIs():
    query = "\n".join(
        (
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
    if not "results" in results:
        return None
    return [binding["URI"]["value"] for binding in results["results"]["bindings"]]


def testLOVInfo():
    req = requests.get(
        "https://lov.linkeddata.es/dataset/lov/api/v2/vocabulary/info?vocab=schema"
    )
    json_data = req.json()
    for versionObj in json_data["versions"]:
        resourceUrl = versionObj["fileURL"]
        version = versionObj["name"]
        print("Download source:", resourceUrl)
        success, pathToFile, response = downloadSource(
            resourceUrl, ".", "tempOnt" + version, "text/rdf+n3"
        )
        print(success)
