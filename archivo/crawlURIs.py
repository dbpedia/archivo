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
    feature_plugins,
    async_rdf_retrieval,
)
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse, urldefrag, quote
from rdflib.term import Literal, URIRef
from string import Template
from SPARQLWrapper import SPARQLWrapper, JSON


# determine_best_content_type
# function used by
#
def determine_best_content_type(uri, user_output=[], logger=None):
    header_dict = {}
    for header in stringTools.rdfHeadersMapping:
        response, error = download_rdf_string(uri, acc_header=header)
        if error is None:
            try:
                triple_number, rapper_errors = ontoFiles.get_triples_from_rdf_string(
                    response.text, uri, input_type=stringTools.rdfHeadersMapping[header]
                )
            except Exception as e:
                if logger is not None:
                    logger.warning(
                        f"Couldn't parse {uri} with header {header}: {str(e)}"
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

                # break for really large ontologies
                if triple_number > 200000:
                    break
            else:
                if len(rapper_errors) > 20:
                    rapper_errors = rapper_errors[:20]
                user_output.append(
                    {
                        "status": False,
                        "step": f"Parsing with header {header}",
                        "message": "Triples: {} \n{}".format(
                            str(triple_number), "\n".join(rapper_errors[:20])
                        ),
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
    resp, triple_number = header_dict[best_header]
    return best_header, resp, triple_number


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
    except KeyboardInterrupt:
        sys.exit(19)
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
        return None, str(e)


def checkRobot(uri):
    parsedUrl = urlparse(uri)
    if parsedUrl.scheme == "" or parsedUrl.netloc == "":
        return None, None
    robotsUrl = str(parsedUrl.scheme) + "://" + str(parsedUrl.netloc) + "/robots.txt"
    try:
        req = requests.get(url=robotsUrl)
    except Exception as e:
        return True, str(e)

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
        retrieval_errors=list(),
        user_output=list(),
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
        self.retrieval_errors = retrieval_errors
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
            inputFormat=stringTools.rdfHeadersMapping[self.best_header],
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
            inputFormat=stringTools.rdfHeadersMapping[self.best_header],
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
            inputFormat=stringTools.rdfHeadersMapping[self.best_header],
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
            self.original_file,
            inputFormat=stringTools.rdfHeadersMapping[self.best_header],
        )[0]
        self.graph = inspectVocabs.getGraphOfVocabFile(
            raw_file_path + "_type=parsed.ttl", logger=self.logger
        )
        # shacl-validation
        # uses the turtle file since there were some problems with the blankNodes of rapper and rdflib
        # no empty parsed files since shacl is valid on empty files.
        (
            self.conforms_archivo,
            reportGraphArchivo,
            reportTextArchivo,
        ) = self.test_suite.archivoConformityTest(self.graph)
        with open(
            raw_file_path + "_type=shaclReport_validates=archivoMetadata.ttl", "w+"
        ) as archivoConformityFile:
            print(
                inspectVocabs.getTurtleGraph(reportGraphArchivo),
                file=archivoConformityFile,
            )
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
        self.is_consistent = True
        self.is_consistent_noimports = True
        # checks consistency with and without imports
        # self.is_consistent, output = self.test_suite.getConsistency(
        #     raw_file_path + "_type=parsed.ttl", ignoreImports=False
        # )
        # self.is_consistent_noimports, outputNoImports = self.test_suite.getConsistency(
        #     raw_file_path + "_type=parsed.ttl", ignoreImports=True
        # )
        # with open(
        #     raw_file_path + "_type=pelletConsistency_imports=FULL.txt", "w+"
        # ) as consistencyReport:
        #     print(output, file=consistencyReport)
        # with open(
        #     raw_file_path + "_type=pelletConsistency_imports=NONE.txt", "w+"
        # ) as consistencyReportNoImports:
        #     print(outputNoImports, file=consistencyReportNoImports)
        # # print pellet info files
        # with open(
        #     raw_file_path + "_type=pelletInfo_imports=FULL.txt", "w+"
        # ) as pelletInfoFile:
        #     print(
        #         self.test_suite.getPelletInfo(
        #             raw_file_path + "_type=parsed.ttl", ignoreImports=False
        #         ),
        #         file=pelletInfoFile,
        #     )
        # with open(
        #     raw_file_path + "_type=pelletInfo_imports=NONE.txt", "w+"
        # ) as pelletInfoFileNoImports:
        #     print(
        #         self.test_suite.getPelletInfo(
        #             raw_file_path + "_type=parsed.ttl", ignoreImports=True
        #         ),
        #         file=pelletInfoFileNoImports,
        #     )
        # profile check for ontology
        # stdout, stderr = self.test_suite.getProfileCheck(
        #     raw_file_path + "_type=parsed.ttl"
        # )
        # with open(raw_file_path + "_type=profile.txt", "w+") as profileCheckFile:
        #     print(stderr + "\n" + stdout, file=profileCheckFile)

        # write the metadata json file
        ontoFiles.altWriteVocabInformation(
            pathToFile=raw_file_path + "_type=meta.json",
            definedByUri=self.reference_uri,
            lastModified=stringTools.getLastModifiedFromResponse(self.response),
            rapperErrors=self.retrieval_errors + self.rapper_errors,
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
        docustring, lode_error = feature_plugins.getLodeDocuFile(
            self.location_uri, logger=self.logger
        )
        if docustring is not None:
            with open(raw_file_path + "_type=generatedDocu.html", "w+") as docufile:
                print(docustring, file=docufile)

        # generate pylode docu
        # pylode_doc = feature_plugins.get_pyLODE_doc_string(
        #     raw_file_path + "_type=parsed.ttl", self.logger
        # )
        # if pylode_doc is not None:
        #     with open(raw_file_path + "_type=pyLodeDoc.html", "w+") as docufile:
        #         print(pylode_doc, file=docufile)

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
            return None, None
        trackThisURI = inspectVocabs.getTrackThisURI(self.graph)
        if trackThisURI is not None and self.location_uri != trackThisURI:
            self.user_output.append(
                {
                    "status": True,
                    "step": "Check for Dev version link",
                    "message": f"Found dev version at: {trackThisURI}",
                }
            )
            try:
                return handleDevURI(
                    self.nir,
                    trackThisURI,
                    self.data_path,
                    self.test_suite,
                    self.logger,
                    user_output=self.user_output,
                )
            except Exception as e:
                self.logger.exception("Problem during handling trackThis")
                return None, None
        else:
            return False, None


# ======== END OF CLASS ================

# returns the NIR if frgmant-equivalent, else None
def check_NIR(uri, graph, output=[]):

    candidates = inspectVocabs.get_ontology_URIs(graph)

    if candidates == []:
        output.append(
            {
                "status": False,
                "step": "Determine non-information resource",
                "message": "Neither can't find a triple with <code>owl:Ontology</code> or <code>skos:ConceptScheme</code> as value",
            }
        )
        return False, None

    found_nir = None

    for nir in candidates:
        if stringTools.check_uri_equality(uri, nir):
            found_nir = nir

    if found_nir is None:
        output.append(
            {
                "status": False,
                "step": "Determine non-information resource",
                "message": f"Neither of {str(candidates)} equals the source URI {uri}, trying to validate {candidates[0]}",
            }
        )
        return False, candidates[0]
    else:
        output.append(
            {
                "status": True,
                "step": "Determine non-information resource",
                "message": f"Found non-information resource: {found_nir}",
            }
        )
        return True, found_nir


def handleNewUri(
    vocab_uri, index, dataPath, source, isNIR, testSuite, logger, user_output=list()
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

    foundURI = stringTools.get_uri_from_index(vocab_uri, index)
    if foundURI is not None:
        logger.info("Already known uri, skipping...")
        user_output.append(
            {
                "status": True,
                "step": "Index check",
                "message": f"This Ontology is already in the Archivo index and can be found at <a href=/info?o={quote(foundURI)}>here</a>",
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
        logger.error(f"Exception in rdflib parsing of URI {vocab_uri}", exc_info=True)
        user_output.append(
            {
                "status": False,
                "step": "Load Graph in rdflib",
                "message": f"RDFlib couldn't parse the file of {vocab_uri}. Reason: {traceback.format_exc()}",
            }
        )
        return False, isNIR, None

    try:
        ont_succ, real_ont_uri = check_NIR(vocab_uri, graph, output=user_output)
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

    if not ont_succ and real_ont_uri is None:
        # if no or no different ontology URI -> check defined_by
        real_ont_uri = inspectVocabs.getDefinedByUri(graph)
        if real_ont_uri is None:
            logger.info("No Ontology discoverable")
            user_output.append(
                {
                    "status": False,
                    "step": "Looking for linked ontologies",
                    "message": "The given URI does not contain a <code>rdfs:isDefinedBy</code> or <code>skos:inScheme</code> triple",
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
                    "message": "This RDF document is linked to itself via <code>rdfs:isDefinedBy</code> or <code>skos:inScheme</code>, but does not contain a triple with <code>owl:Ontology</code> or <code>skos:ConceptScheme</code>, so it can't be recognized as an ontology.",
                }
            )
            return False, isNIR, None
    elif not ont_succ and real_ont_uri is not None:
        # when another URI was discovered -> check it
        isNIR = True
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
    isNIR = True

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

    foundURI = stringTools.get_uri_from_index(real_ont_uri, index)
    if foundURI is not None:
        logger.info(f"Already known uri {real_ont_uri}")
        user_output.append(
            {
                "status": True,
                "step": "Index check",
                "message": f"This Ontology is already in the Archivo index and can be found at <a href=/info?o={quote(foundURI)}>here</a>",
            }
        )
        return False, isNIR, None

    # handle slash uris
    if real_ont_uri.endswith("/"):
        (
            nt_content_list,
            retrieval_error_list,
        ) = async_rdf_retrieval.gather_linked_content(
            real_ont_uri, graph, bestHeader, concurrent_requests=50, logger=logger
        )

        # get nt content from response
        (orig_nt_content, _, _, _,) = ontoFiles.parse_rdf_from_string(
            response.text,
            real_ont_uri,
            input_type=stringTools.rdfHeadersMapping[bestHeader],
            output_type="ntriples",
        )

        if len(nt_content_list) > 0:
            # append original nt content to retrieved content
            nt_content_list.append(orig_nt_content)

            # set parsed, concatted content as the original content
            (
                parsed_triples,
                triple_count,
                rapper_errors,
                _,
            ) = ontoFiles.parse_rdf_from_string(
                "\n".join(nt_content_list),
                real_ont_uri,
                input_type="ntriples",
                output_type=stringTools.rdfHeadersMapping[bestHeader],
            )
            if len(retrieval_error_list) > 0:
                user_output.append(
                    {
                        "status": False,
                        "step": "Retrieve defined RDF content",
                        "message": "This ontology was recognized as a Slash Ontology, but there were errors with the defined RDF content:\n{}".format(
                            "\n".join([", ".join(tp) for tp in retrieval_error_list])
                        ),
                    }
                )
            else:
                user_output.append(
                    {
                        "status": True,
                        "step": "Retrieve defined RDF content",
                        "message": "This ontology was recognized as a Slash Ontology and {} different sources were included".format(
                            len(nt_content_list)
                        ),
                    }
                )

            orig_rdf_content = parsed_triples

        # if no slash uri or no additional content retrieved -> set original file as orig content
        else:
            user_output.append(
                {
                    "status": True,
                    "step": "Retrieve defined RDF content",
                    "message": "This ontology was recognized as a Slash Ontology but no defined RDF content was found by using the following properties:\n{}".format(
                        "\n".join(archivoConfig.defines_properties)
                    ),
                }
            )
            orig_rdf_content = response.text
    else:
        orig_rdf_content = response.text

    try:
        retrival_errors = [", ".join(tp) for tp in retrieval_error_list]
    except NameError:
        retrival_errors = []

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
    fileExt = stringTools.file_ending_mapping[bestHeader]
    new_orig_file_path = os.path.join(
        newVersionPath, artifact + "_type=orig." + fileExt
    )
    with open(new_orig_file_path, "w+") as new_orig_file:
        print(orig_rdf_content, file=new_orig_file)
    # new release
    logger.info("Generate new release files...")
    new_version = ArchivoVersion(
        real_ont_uri,
        new_orig_file_path,
        response,
        testSuite,
        accessDate,
        bestHeader,
        logger,
        source,
        retrieval_errors=retrival_errors,
        user_output=user_output,
    )
    new_version.generateFiles()
    new_version.generatePomAndDoc()

    # new_version.generatePomAndDoc()

    # logger.info("Deploying the data to the databus...")
    # returncode, deployLog = generatePoms.callMaven(
    #     os.path.join(dataPath, groupId, artifact, "pom.xml"), "deploy"
    # )

    returncode = 0

    deployLog = "No need to deploy, just add it to the database"
    
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
                "message": f"Deployed the Ontology to the DBpedia Databus, should be accessable at the <a href=https://databus.dbpedia.org/ontologies/{groupId}/{artifact}>databus</a> and at the <a href=/info?o={quote(real_ont_uri)}>Archivo webpage</a> soon.",
            }
        )
        return True, isNIR, new_version


def handleDevURI(nir, sourceURI, dataPath, testSuite, logger, user_output=list()):
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
                "message": f"Archivo-Agent {archivoConfig.archivo_agent} is not allowed to access the ontology at <a href={sourceURI}>{sourceURI}</a>",
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
    fileExt = stringTools.file_ending_mapping[bestHeader]
    new_orig_file_path = os.path.join(
        newVersionPath, artifact + "_type=orig." + fileExt
    )
    with open(new_orig_file_path, "w+") as new_orig_file:
        print(response.text, file=new_orig_file)
    # new release
    logger.info("Generate new release files...")
    new_version = ArchivoVersion(
        nir,
        os.path.join(newVersionPath, artifact + "_type=orig." + fileExt),
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
    # new_version.generatePomAndDoc()

    # logger.info("Deploying the data to the databus...")
    # returncode, deployLog = generatePoms.callMaven(
    #     os.path.join(dataPath, groupId, artifact, "pom.xml"), "deploy"
    # )

    returncode = 0

    deployLog = "No need to deploy, just add it to the database"

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
