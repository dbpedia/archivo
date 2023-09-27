from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

import requests
import traceback

from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse, urldefrag, quote

from crawling.best_effort_crawling import determine_best_content_type
from datetime import datetime
from logging import Logger
from string import Template
from typing import Dict, List, Optional
import databusclient  # type: ignore
import rdflib
from rdflib import URIRef, Literal
from models.content_negotiation import (
    RDF_Type,
    get_accept_header,
    get_file_extension,
)
from models.crawling_response import CrawlingResponse
from models.databus_identifier import (
    DatabusFileMetadata,
    DatabusVersionIdentifier,
)
from models.data_writer import DataWriter, FileWriter
from models.user_interaction import ProcessStepLog, LogLevel
from utils import (
    string_tools,
    feature_plugins,
    docTemplates,
    archivo_config,
    parsing,
    content_access,
)
from querying import graph_handling
from utils.validation import TestSuite
from utils.string_tools import stars_from_meta_dict


class ArchivoVersion:
    def __init__(
        self,
        confirmed_ontology_id: str,
        crawling_result: CrawlingResponse,
        parsing_result: parsing.RapperParsingResult,
        databus_version_identifier: DatabusVersionIdentifier,
        test_suite: TestSuite,
        access_date: datetime,
        logger: Logger,
        source: str,
        data_writer: DataWriter,
        ontology_graph: rdflib.Graph | None = None,
        semantic_version: str = "1.0.0",
        dev_uri: str = "",
        user_output: List[ProcessStepLog] | None = None,
    ):
        if user_output is None:
            user_output = list()

        self.parsing_result = parsing_result
        # the nir is the identity of the ontology, confirmed by checking for the triple inside the ontology itself
        # not to be confused with the location of the ontology, or the URI the crawl started with
        self.nir = confirmed_ontology_id
        # data writer -> abstraction for handling the writing process
        self.data_writer = data_writer
        self.db_version_identifier = databus_version_identifier
        self.crawling_result = crawling_result

        self.ontology_graph = (
            graph_handling.get_graph_of_string(
                parsing_result.parsed_rdf, parsing_result.rdf_type
            )
            if ontology_graph is None
            else ontology_graph
        )

        self.isDev = False if dev_uri == "" else True
        self.location_uri = crawling_result.response.url if dev_uri == "" else dev_uri
        self.reference_uri = dev_uri if self.isDev else self.nir
        self.test_suite = test_suite
        self.access_date = access_date
        self.source = source
        self.semantic_version = semantic_version
        self.user_output = user_output
        self.logger = logger
        if len(self.crawling_result.response.history) > 0:
            self.nir_header = str(self.crawling_result.response.history[0].headers)
        else:
            self.nir_header = ""

        # initialize a empty dict for the metadata file

        self.metadata_dict: Dict[str, Dict] = {
            "test-results": {},
            "http-data": {},
            "ontology-info": {},
            "logs": {},
        }

    def __write_original_file(self):
        db_file_metadata = DatabusFileMetadata.build_from_content(
            content=self.crawling_result.response.text,
            version_identifier=self.db_version_identifier,
            content_variants={"type": "orig"},
            file_extension=get_file_extension(self.crawling_result.rdf_type),
        )

        self.data_writer.write_databus_file(
            self.crawling_result.response.text, db_file_metadata
        )

    def __generate_parsed_rdf(self):

        for parsing_type in RDF_Type:
            if parsing_type == self.parsing_result.rdf_type:
                db_file_metadata = parsing.generate_metadata_for_parsing_result(
                    self.db_version_identifier, self.parsing_result
                )
                self.data_writer.write_databus_file(
                    self.parsing_result.parsed_rdf, db_file_metadata
                )
            else:
                new_parsing_result = parsing.parse_rdf_from_string(
                    self.crawling_result.response.text,
                    self.nir,
                    self.crawling_result.rdf_type,
                    parsing_type,
                )

                db_file_metadata = parsing.generate_metadata_for_parsing_result(
                    self.db_version_identifier, new_parsing_result
                )
                self.data_writer.write_databus_file(
                    new_parsing_result.parsed_rdf, db_file_metadata
                )

    def __generate_shacl_reports(self):

        shacl_report_mappings = {
            self.test_suite.archivo_conformity_test: ("archivoMetadata", None),
            self.test_suite.license_existence_check: ("minLicense", "License-I"),
            self.test_suite.license_property_check: ("goodLicense", "License-II"),
            self.test_suite.lodeReadyValidation: ("lodeMetadata", "lode-conform"),
        }

        for shacl_report_fun, id_tuple in shacl_report_mappings.items():
            validates_cv, report_key = id_tuple
            (
                conforms,
                report_graph,
                _,
            ) = shacl_report_fun(self.ontology_graph)

            serialized_report = graph_handling.serialize_graph(
                report_graph, rdf_format="turtle"
            )

            db_file_metadata = DatabusFileMetadata.build_from_content(
                content=serialized_report,
                version_identifier=self.db_version_identifier,
                content_variants={"type": "shaclReport", "validates": validates_cv},
                file_extension="ttl",
                compression=None,
            )

            self.data_writer.write_databus_file(serialized_report, db_file_metadata)

            if report_key:
                self.metadata_dict["test-results"][report_key] = conforms

    def __run_consistency_checks(self):

        # looks in the data writer for the written parsed version of the ontology
        file_metadata = None
        for metadata, error in self.data_writer.written_files:
            if (
                metadata.file_extension == "ttl"
                and metadata.content_variants["type"] == "parsed"
            ):
                file_metadata = metadata
                break

        if file_metadata:

            url = content_access.get_location_url(file_metadata)

            for ignore_imports in [True, False]:

                imports_cv = "NONE" if ignore_imports else "FULL"
                metadata_key = (
                    "consistent-without-imports" if ignore_imports else "consistent"
                )

                consistency, output = self.test_suite.get_consistency(
                    ontology_url=url, ignore_imports=False
                )
                self.metadata_dict["test-results"][metadata_key] = consistency

                file_metadata = DatabusFileMetadata.build_from_content(
                    content=output,
                    version_identifier=self.db_version_identifier,
                    content_variants={
                        "type": "pelletConsistency",
                        "imports": imports_cv,
                    },
                    file_extension="txt",
                )

                self.data_writer.write_databus_file(output, file_metadata)

    def __run_pellet_info(self):

        file_metadata = None
        for metadata, error in self.data_writer.written_files:
            if (
                metadata.file_extension == "ttl"
                and metadata.content_variants["type"] == "parsed"
            ):
                file_metadata = metadata
                break

        if file_metadata:

            url = content_access.get_location_url(file_metadata)

            for ignore_imports in [True, False]:

                imports_cv = "NONE" if ignore_imports else "FULL"

                output = self.test_suite.get_pellet_info(
                    ontology_url=url, ignore_imports=False
                )

                file_metadata = DatabusFileMetadata.build_from_content(
                    content=output,
                    version_identifier=self.db_version_identifier,
                    content_variants={
                        "type": "pelletInfo",
                        "imports": imports_cv,
                    },
                    file_extension="txt",
                )

                self.data_writer.write_databus_file(output, file_metadata)

    def __generate_documentation_files(self):
        """generates the HTML documentation files"""

        # generate lode docu
        docustring, lode_error = feature_plugins.getLodeDocuFile(
            self.location_uri, logger=self.logger
        )

        if docustring:
            shasum, content_length = string_tools.get_content_stats(
                bytes(docustring, "utf-8")
            )
            db_metadata = DatabusFileMetadata(
                version_identifier=self.db_version_identifier,
                content_variants={"type": "generatedDocu"},
                file_extension="html",
                sha_256_sum=shasum,
                content_length=content_length,
                compression=None,
            )
            self.data_writer.write_databus_file(docustring, db_metadata)

        # TODO: Include pylode once they merged my pull request

    def __write_vocab_information_file(self):
        # set http metadata
        http_dict = self.metadata_dict["http-data"]
        http_dict["e-tag"] = string_tools.getEtagFromResponse(
            self.crawling_result.response
        )
        http_dict["accessed"] = self.access_date.strftime("%Y.%m.%d-%H%M%S")
        http_dict["content-length"] = string_tools.getContentLengthFromResponse(
            self.crawling_result.response
        )
        http_dict["best-header"] = get_accept_header(self.crawling_result.rdf_type)
        http_dict["lastModified"] = string_tools.getLastModifiedFromResponse(
            self.crawling_result.response
        )

        # set parsing logs
        logs_dict = self.metadata_dict["logs"]
        logs_dict["nir_header"] = self.nir_header
        logs_dict["rapper-errors"] = self.parsing_result.parsing_info.errors
        logs_dict["rapper-warnings"] = self.parsing_result.parsing_info.warnings
        logs_dict["resource-header"] = str(self.crawling_result.response.headers)

        # set ontology info
        info_dict = self.metadata_dict["ontology-info"]
        info_dict["non-information-uri"] = self.reference_uri
        info_dict["semantic-version"] = self.semantic_version
        info_dict["snapshot-url"] = self.location_uri
        info_dict["triples"] = self.parsing_result.parsing_info.triple_number
        info_dict["stars"] = stars_from_meta_dict(self.metadata_dict)

        content = json.dumps(self.metadata_dict, indent=4)

        db_file_metadata = DatabusFileMetadata.build_from_content(
            content=content,
            version_identifier=self.db_version_identifier,
            content_variants={"type": "meta"},
            file_extension="json",
        )

        self.data_writer.write_databus_file(content, db_file_metadata)

    def generate_files(self):

        self.__write_original_file()
        self.__generate_parsed_rdf()
        self.__generate_shacl_reports()
        self.__generate_documentation_files()
        # this needs to be run AFTER the parsed generation since it requires the file to be written
        self.__run_consistency_checks()
        self.__run_pellet_info()
        # This needs to be run last since all the other checks need to run first
        self.__write_vocab_information_file()

    def handle_dev_version(self) -> Optional[ArchivoVersion]:
        if self.isDev:
            return None
        track_this_uri = graph_handling.get_track_this_uri(self.ontology_graph)
        if track_this_uri is not None and self.location_uri != track_this_uri:
            self.user_output.append(
                ProcessStepLog(
                    status=LogLevel.INFO,
                    stepname="Check for Dev version link",
                    message=f"Found dev version at: {track_this_uri}",
                )
            )
            try:
                # clear history for new
                self.data_writer.clear_history()

                return handle_track_this_uri(
                    original_nir=self.nir,
                    dev_version_location=track_this_uri,
                    test_suite=self.test_suite,
                    data_writer=self.data_writer,
                    logger=self.logger,
                    process_log=self.user_output,
                )
            except Exception as e:
                self.logger.exception("Problem during handling trackThis")
                return None
        else:
            return None

    def get_label(self) -> str:
        label = self.nir if not self.isDev else self.nir + " DEV"

        if self.ontology_graph is not None:
            label_found = graph_handling.get_label(self.ontology_graph)
            if label_found is not None:
                label = label_found if not self.isDev else label_found + " DEV"
        return label

    def __get_comment(self) -> str:
        comment = Template(docTemplates.default_explaination).safe_substitute(
            non_information_uri=self.reference_uri
        )

        if self.ontology_graph is not None:
            found_comment = graph_handling.get_comment(self.ontology_graph)
            if found_comment is not None:
                comment = found_comment

        return comment

    def __get_description(self) -> str:
        description: Template = (
            Template(docTemplates.description)
            if not self.isDev
            else Template(docTemplates.description_dev)
        )

        if self.ontology_graph is not None:
            found_description = graph_handling.get_description(self.ontology_graph)
            version_iri = graph_handling.get_owl_version_iri(self.ontology_graph)
            if found_description is not None:
                return (
                    description.safe_substitute(
                        non_information_uri=self.nir,
                        snapshot_url=self.location_uri,
                        owl_version_iri=version_iri,
                        date=self.db_version_identifier.version,
                    )
                    + "\n\n"
                    + docTemplates.description_intro
                    + "\n\n"
                    + found_description
                )
            else:
                return description.safe_substitute(
                    non_information_uri=self.nir,
                    snapshot_url=self.location_uri,
                    owl_version_iri=version_iri,
                    date=str(self.access_date),
                )
        else:
            return str(description)

    def __get_license(self) -> str:

        found_license = graph_handling.get_license(self.ontology_graph)

        match found_license:
            case None:
                return docTemplates.default_license
            case URIRef(_):
                return str(found_license).strip("<>")
            case Literal(_):
                return docTemplates.license_literal_uri
            case _:
                return docTemplates.default_license

    def build_databus_jsonld(self, group_info: Dict[str, str] | None = None) -> Dict:

        if group_info is None:
            group_info = {}

        distribs = self.data_writer.generate_distributions()

        title = self.get_label()
        comment = self.__get_comment()
        description = self.__get_description()
        license_url = self.__get_license()
        if group_info == {}:
            dataset = databusclient.create_dataset(
                version_id=f"{archivo_config.DATABUS_BASE}/{self.db_version_identifier}",
                title=title,
                abstract=comment,
                description=description,
                license_url=license_url,
                distributions=distribs,
            )
        else:
            dataset = databusclient.create_dataset(
                version_id=f"{archivo_config.DATABUS_BASE}/{self.db_version_identifier}",
                title=title,
                abstract=comment,
                description=description,
                license_url=license_url,
                distributions=distribs,
                group_title=group_info["title"],
                group_description=group_info["description"],
            )

        return dataset

    def deploy(
        self, generate_files: bool, group_info: Optional[Dict[str, str]] | None = None
    ):

        if generate_files:
            self.generate_files()

        databus_dataset_jsonld = self.build_databus_jsonld(group_info=group_info)

        self.logger.info("Deploying the data to the databus...")
        databusclient.deploy(databus_dataset_jsonld, archivo_config.DATABUS_API_KEY)


def check_robot(uri: str) -> Tuple[Optional[bool], Optional[str]]:
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
    if rp.can_fetch(archivo_config.ARCHIVO_AGENT, uri):
        return True, None
    else:
        return False, "Not allowed"


# returns the NIR if fragment-equivalent, else None
def check_ontology_id_uri(
    uri: str, graph: rdflib.Graph, output: List[ProcessStepLog] | None = None
) -> Tuple[bool, Optional[str]]:
    """Checks for the existence of an ontology ID and checks if it is equal to the input URI.
    Returns A Tuple of"""

    if output is None:
        output = []
    candidates = graph_handling.get_ontology_uris(graph)

    if not candidates:
        output.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="Determine non-information resource (ID of the ontology)",
                message="Can't neither find a triple with <code>owl:Ontology</code> or <code>skos:ConceptScheme</code> as value",
            )
        )
        return False, None

    found_nir = None

    for nir in candidates:
        if string_tools.check_uri_equality(uri, nir):
            found_nir = nir
            break

    if found_nir is None:
        output.append(
            ProcessStepLog(
                status=LogLevel.WARNING,
                stepname="Determine non-information resource (ID of the ontology)",
                message=f"Neither of {str(candidates)} equals the source URI {uri}, trying to validate {candidates[0]}",
            )
        )
        return False, candidates[0]
    else:
        output.append(
            ProcessStepLog(
                status=LogLevel.INFO,
                stepname="Determine non-information resource (ID of the ontology)",
                message=f"Found non-information resource: {found_nir} corresponding with {uri}",
            )
        )
        return True, found_nir


def perform_robot_check(
    vocab_uri: str, user_output: List[ProcessStepLog], logger: Logger
) -> bool:
    allowed, message = check_robot(vocab_uri)
    if not allowed:
        logger.warning(f"{archivo_config.ARCHIVO_AGENT} not allowed")
        user_output.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="Robot allowance check",
                message=f"Archivo-Agent {archivo_config.ARCHIVO_AGENT} is not allowed to access the ontology at <a href={vocab_uri}>{vocab_uri}</a>",
            )
        )
        return False
    else:
        user_output.append(
            ProcessStepLog(
                status=LogLevel.INFO,
                stepname="Robot allowance check",
                message=f"Archivo-Agent {archivo_config.ARCHIVO_AGENT} is allowed.",
            )
        )
        return True


def parse_uri(uri: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Takes an URI and returns the defragmented URI, a"""

    defrag_uri = urldefrag(uri)[0]
    group_id, artifact_id = string_tools.generate_databus_identifier_from_uri(
        defrag_uri
    )

    return defrag_uri, group_id, artifact_id


def searching_for_linked_ontologies(
    uri: str,
    found_ontology_id: Optional[str],
    onto_graph: rdflib.Graph,
    vocab_uri_cache: List[str],
    logger: Logger,
    process_log: List[ProcessStepLog],
    recursion_depth: int,
    source: str,
    test_suite: TestSuite,
) -> Optional[ArchivoVersion]:

    match found_ontology_id:
        case None:
            # This means there is no ontology ID whatsoever. Try using isDefinedBy to find its defining vocab.
            defined_by_uri = graph_handling.get_defined_by_uri(onto_graph)

            match defined_by_uri:
                case None:
                    process_log.append(
                        ProcessStepLog(
                            status=LogLevel.ERROR,
                            stepname="Searching for linked ontologies",
                            message=f"The document given at {uri} does not contain a <code>rdfs:isDefinedBy</code> or <code>skos:inScheme</code> triple",
                        )
                    )
                    return None
                case def_by_uri if not string_tools.check_uri_equality(def_by_uri, uri):
                    process_log.append(
                        ProcessStepLog(
                            status=LogLevel.INFO,
                            stepname="Searching for linked ontologies",
                            message=f"Found linked potential ontology at {def_by_uri}",
                        )
                    )
                    return discover_new_uri(
                        uri=def_by_uri,
                        vocab_uri_cache=vocab_uri_cache,
                        logger=logger,
                        process_log=process_log,
                        recursion_depth=recursion_depth + 1,
                        source=source,
                        test_suite=test_suite,
                    )
                case def_by_uri if string_tools.check_uri_equality(def_by_uri, uri):
                    process_log.append(
                        ProcessStepLog(
                            status=LogLevel.ERROR,
                            stepname="Searching for linked ontologies",
                            message=f"The document given at {uri} links to itself via an <code>rdfs:isDefinedBy</code> or <code>skos:inScheme</code> triple but is no ontology",
                        )
                    )
                    return None

        case nir:
            # This means the crawled URI and the found ontology ID are inconsistent. Try crawling the new value.
            process_log.append(
                ProcessStepLog(
                    status=LogLevel.INFO,
                    stepname="Ontology Identification",
                    message=f"The document given at {uri} links to itself via an <code>rdfs:isDefinedBy</code> or <code>skos:inScheme</code> triple, bit is no ontology",
                )
            )
            if recursion_depth <= archivo_config.DISCOVERY_MAXIMUM_RECURSION_DEPTH:
                return discover_new_uri(
                    uri=nir,
                    vocab_uri_cache=vocab_uri_cache,
                    logger=logger,
                    process_log=process_log,
                    recursion_depth=recursion_depth + 1,
                    source=source,
                    test_suite=test_suite,
                )
            else:
                process_log.append(
                    ProcessStepLog(
                        status=LogLevel.ERROR,
                        stepname="Searching for linked ontologies",
                        message=f"Maximum recursion depth of {archivo_config.DISCOVERY_MAXIMUM_RECURSION_DEPTH} reached",
                    )
                )
                return None

    return None


def discover_new_uri(
    uri: str,
    vocab_uri_cache: List[str],
    test_suite: TestSuite,
    source: str,
    logger: Logger,
    process_log: List[ProcessStepLog] | None = None,
    recursion_depth: int = 1,
) -> Optional[ArchivoVersion]:

    if process_log is None:
        process_log = []

    uri, group_id, artifact_id = parse_uri(uri)

    # Check if URI was malformed
    if group_id is None or artifact_id is None:
        process_log.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="URI parsing check",
                message=f"ERROR: Malformed URI {uri}",
            )
        )
        return None

    # check if uri is in cache
    found_uri = string_tools.get_uri_from_index(uri, vocab_uri_cache)
    if found_uri is not None:
        logger.info("Already known uri, skipping...")
        process_log.append(
            ProcessStepLog(
                status=LogLevel.INFO,
                stepname="Index check",
                message=f"This Ontology is already in the Archivo index and can be found at <a href=/info?o={quote(found_uri)}>here</a>",
            )
        )
        return None

    if not perform_robot_check(vocab_uri=uri, user_output=process_log, logger=logger):
        return None

    crawling_result = determine_best_content_type(uri, user_output=process_log)

    if crawling_result is None:
        return None

    # now there is RDF and its parseable, we can now check if it is an ontology
    access_date = datetime.now()
    version_id = access_date.strftime("%Y.%m.%d-%H%M%S")

    # parse the content with rapper since its more consumeable by rdflib and load it into a graph

    parsing_result_turtle = parsing.parse_rdf_from_string(
        crawling_result.response.text, uri, crawling_result.rdf_type, RDF_Type.TURTLE
    )

    try:
        onto_graph = graph_handling.get_graph_of_string(
            parsing_result_turtle.parsed_rdf, RDF_Type.TURTLE
        )
    except Exception:
        logger.error(f"Exception in rdflib parsing of URI {uri}", exc_info=True)
        process_log.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="Load Graph in rdflib",
                message=f"RDFlib couldn't parse the file of {uri}. Reason: {traceback.format_exc()}",
            )
        )
        return None

    success, ontology_id_uri = check_ontology_id_uri(uri, onto_graph, process_log)

    if not success:
        # this means no ontology ID could be found
        return searching_for_linked_ontologies(
            uri=uri,
            found_ontology_id=ontology_id_uri,
            onto_graph=onto_graph,
            vocab_uri_cache=vocab_uri_cache,
            logger=logger,
            process_log=process_log,
            recursion_depth=recursion_depth,
            source=source,
            test_suite=test_suite,
        )
    assert ontology_id_uri is not None

    # Now from here on it is a confirmed ontology

    # overwrite generated databus identifiers
    group_id, artifact_id = string_tools.generate_databus_identifier_from_uri(
        ontology_id_uri
    )

    # again malformed check
    if group_id is None or artifact_id is None:
        process_log.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="URI parsing check",
                message=f"ERROR: Malformed ontology ID in document: {ontology_id_uri}",
            )
        )
        return None

    # again cache check
    found_uri = string_tools.get_uri_from_index(ontology_id_uri, vocab_uri_cache)
    if found_uri is not None:
        logger.info("Already known uri, skipping...")
        process_log.append(
            ProcessStepLog(
                status=LogLevel.INFO,
                stepname="Index check",
                message=f"This Ontology is already in the Archivo index and can be found at <a href=/info?o={quote(found_uri)}>here</a>",
            )
        )
        return None

    group_info = {
        "title": f"DBpedia Archivo ontologies from the {group_id} domain",
        "description": f"Each artifact in this group deals as the archive for snapshots of one ontology of the DBpedia Archivo - A Web-Scale Interface for Ontology Archiving under Consumer-oriented Aspects. Find out more at http://archivo.dbpedia.org.",
    }

    databus_version_id = DatabusVersionIdentifier(
        user=archivo_config.DATABUS_USER,
        group=group_id,
        artifact=artifact_id,
        version=version_id,
    )

    # generate new version
    data_writer = FileWriter(
        path_base=Path(archivo_config.LOCAL_PATH),
        target_url_base=archivo_config.PUBLIC_URL_BASE,
        logger=logger,
    )
    archivo_version = ArchivoVersion(
        confirmed_ontology_id=ontology_id_uri,
        crawling_result=crawling_result,
        parsing_result=parsing_result_turtle,
        databus_version_identifier=databus_version_id,
        access_date=access_date,
        data_writer=data_writer,
        logger=logger,
        source=source,
        test_suite=test_suite,
    )

    try:
        archivo_version.deploy(generate_files=True, group_info=group_info)
        logger.info(f"Successfully deployed the new update of ontology {uri}")
        process_log.append(
            ProcessStepLog(
                status=LogLevel.INFO,
                stepname="Deployment to Databus",
                message=f"Sucessfully deployed to the Databus: <a href={archivo_config.DATABUS_BASE}/{archivo_config.DATABUS_USER}/{group_id}/{artifact_id}>{archivo_config.DATABUS_BASE}/{archivo_config.DATABUS_USER}/{group_id}/{artifact_id}</a>",
            )
        )
        return archivo_version
    except Exception as e:
        logger.error("There was an Error deploying to the databus")
        logger.error(str(e))
        process_log.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="Deployment to Databus",
                message=f"Failed to deploy to the Databus. Reason: {str(e)}.\n\nThere is probably an error on the Databus site, if this error persists please create an issue in the github repository.",
            )
        )
        return None


def handle_track_this_uri(
    original_nir: str,
    dev_version_location: str,
    data_writer: DataWriter,
    test_suite: TestSuite,
    logger: Logger,
    process_log: List[ProcessStepLog],
) -> Optional[ArchivoVersion]:

    # check robot if we are allowed to crawl
    if not perform_robot_check(dev_version_location, process_log, logger):
        return None

    # now fetch the rdf data
    crawling_result = determine_best_content_type(
        dev_version_location, user_output=process_log
    )

    access_date = datetime.now()
    version_id = access_date.strftime("%Y.%m.%d-%H%M%S")

    if crawling_result is None:
        return None

    # all it needs to be is readable by rdflib, so try parsing it

    parsing_result_turtle = parsing.parse_rdf_from_string(
        crawling_result.response.text,
        original_nir,
        crawling_result.rdf_type,
        RDF_Type.TURTLE,
    )

    try:
        onto_graph = graph_handling.get_graph_of_string(
            parsing_result_turtle.parsed_rdf, RDF_Type.TURTLE
        )
    except Exception:
        logger.error(
            f"Exception in rdflib parsing of URI {dev_version_location}", exc_info=True
        )
        process_log.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="Load Graph in rdflib",
                message=f"RDFlib couldn't parse the file of {dev_version_location}. Reason: {traceback.format_exc()}",
            )
        )
        return None

    # now it is parseable rdf it can be deployed as dev version

    # overwrite generated databus identifiers
    group_id, artifact_id = string_tools.generate_databus_identifier_from_uri(
        original_nir, dev=True
    )
    assert group_id is not None
    assert artifact_id is not None

    databus_version_id = DatabusVersionIdentifier(
        user=archivo_config.DATABUS_USER,
        group=group_id,
        artifact=artifact_id,
        version=version_id,
    )

    archivo_version = ArchivoVersion(
        confirmed_ontology_id=original_nir,
        crawling_result=crawling_result,
        parsing_result=parsing_result_turtle,
        databus_version_identifier=databus_version_id,
        access_date=access_date,
        data_writer=data_writer,
        logger=logger,
        source="DEV",
        test_suite=test_suite,
        dev_uri=dev_version_location,
    )

    try:
        archivo_version.deploy(generate_files=True)
        logger.info(
            f"Successfully deployed the new update of DEV ontology for {original_nir}"
        )
        process_log.append(
            ProcessStepLog(
                status=LogLevel.INFO,
                stepname="Deployment to Databus",
                message=f"Sucessfully deployed to the Databus: <a href={archivo_config.DATABUS_BASE}/{archivo_config.DATABUS_USER}/{group_id}/{artifact_id}>{archivo_config.DATABUS_BASE}/{archivo_config.DATABUS_USER}/{group_id}/{artifact_id}</a>",
            )
        )
        return archivo_version
    except Exception as e:
        logger.error("There was an Error deploying to the databus")
        logger.error(str(e))
        process_log.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="Deployment to Databus",
                message=f"Failed to deploy to the Databus. Reason: {str(e)}.\n\nThere is probably an error on the Databus site, if this error persists please create an issue in the github repository.",
            )
        )
        return None
