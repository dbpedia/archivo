import hashlib
import os
from datetime import datetime
from logging import Logger
from string import Template
from typing import Dict, List, Optional
import databusclient
import rdflib
from rdflib import URIRef, Literal

from archivo.crawling.discovery import handleDevURI
from archivo.models.content_negotiation import (
    RDF_Type,
    get_file_extension,
    get_accept_header,
)
from archivo.models.crawling_response import CrawlingResponse
from archivo.models.databus_identifier import (
    DatabusFileMetadata,
    DatabusVersionIdentifier,
)
from archivo.models.data_writer import DataWriter
from archivo.models.user_interaction import ProcessStepLog, LogLevel
from archivo.utils import (
    string_tools,
    graph_handling,
    feature_plugins,
    docTemplates,
    archivoConfig,
    parsing,
)
from archivo.utils.validation import TestSuite


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
        ontology_graph: rdflib.Graph = None,
        semantic_version: str = "1.0.0",
        dev_uri: str = "",
        user_output: List[ProcessStepLog] = None,
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

        if ontology_graph is None:
            self.ontology_graph: rdflib.Graph = graph_handling.get_graph_of_string(
                parsing_result.parsed_rdf, parsing_result.rdf_type
            )
        else:
            self.ontology_graph: rdflib.Graph = ontology_graph

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

        self.metadata_dict = {
            "test-results": {},
            "http-data": {},
            "ontology-info": {},
            "logs": {},
        }

        self.stars_dict = {}

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
            shasum, content_length = string_tools.get_content_stats(
                bytes(serialized_report, "utf-8")
            )
            db_file_metadata = DatabusFileMetadata(
                version_identifier=self.db_version_identifier,
                content_variants={"type": "shaclReport", "validates": validates_cv},
                file_extension="ttl",
                sha_256_sum=shasum,
                content_length=content_length,
                compression=None,
            )

            self.data_writer.write_databus_file(serialized_report, db_file_metadata)

            if report_key:
                self.metadata_dict["test-results"][report_key] = conforms

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
        http_dict["accessed"] = self.access_date
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
        # info_dict["stars"] =

    def generate_files(self):

        self.__generate_parsed_rdf()
        self.__generate_shacl_reports()
        self.__generate_documentation_files()
        self.__write_vocab_information_file()

    def handleTrackThis(self):
        if self.isDev:
            return None, None
        trackThisURI = graph_handling.get_track_this_uri(self.ontology_graph)
        if trackThisURI is not None and self.location_uri != trackThisURI:
            self.user_output.append(
                ProcessStepLog(
                    status=LogLevel.INFO,
                    stepname="Check for Dev version link",
                    message=f"Found dev version at: {trackThisURI}",
                )
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

    def __generate_distributions(self) -> List[str]:

        distributions = []

        for metadata, error in self.data_writer.written_files.items():
            if error:
                self.logger.error(f"Error during writing file {metadata}: {error}")
            else:
                dst = databusclient.create_distribution(
                    url=f"{self.data_writer.target_url_base}/{metadata}",
                    cvs=metadata.content_variants,
                    file_format=metadata.file_extension,
                    compression=metadata.compression,
                    sha256_length_tuple=(metadata.sha_256_sum, metadata.content_length),
                )
                distributions.append(dst)

        return distributions

    def __get_label(self) -> str:
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
        description = (
            Template(docTemplates.description)
            if not self.isDev
            else Template(docTemplates.description_dev)
        )

        if self.ontology_graph is not None:
            found_description = graph_handling.get_description(self.ontology_graph)
            versionIRI = graph_handling.get_owl_version_iri(self.ontology_graph)
            if found_description is not None:
                description = (
                    description.safe_substitute(
                        non_information_uri=self.nir,
                        snapshot_url=self.location_uri,
                        owl_version_iri=versionIRI,
                        date=self.db_version_identifier.version,
                    )
                    + "\n\n"
                    + docTemplates.description_intro
                    + "\n\n"
                    + found_description
                )
            else:
                description = description.safe_substitute(
                    non_information_uri=self.nir,
                    snapshot_url=self.location_uri,
                    owl_version_iri=versionIRI,
                    date=str(self.access_date),
                )

        return description

    def __get_license(self) -> str:

        found_license = graph_handling.get_license(self.ontology_graph)
        if isinstance(found_license, URIRef):
            found_license = str(found_license).strip("<>")
        elif isinstance(found_license, Literal):
            # if license is literal: error uri
            found_license = docTemplates.license_literal_uri

        return found_license

    def build_databus_jsonld(self, group_info=None) -> Dict:

        if group_info is None:
            group_info = {}

        distribs = self.__generate_distributions()

        title = self.__get_label()
        comment = self.__get_comment()
        description = self.__get_description()
        license_url = self.__get_license()
        if group_info == {}:
            dataset = databusclient.create_dataset(
                version_id=f"{archivoConfig.DATABUS_BASE}/{self.db_version_identifier}",
                title=title,
                abstract=comment,
                description=description,
                license_url=license_url,
                distributions=distribs,
            )
        else:
            dataset = databusclient.create_dataset(
                version_id=f"{archivoConfig.DATABUS_BASE}/{self.db_version_identifier}",
                title=title,
                abstract=comment,
                description=description,
                license_url=license_url,
                distributions=distribs,
                group_title=group_info["title"],
                group_description=group_info["description"],
            )

        return dataset
