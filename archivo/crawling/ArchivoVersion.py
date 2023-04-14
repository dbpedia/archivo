import hashlib
import os
from datetime import datetime
from logging import Logger
from string import Template
from typing import Dict, List
import databusclient
import rdflib
from rdflib import URIRef, Literal

from archivo.crawling.discovery import handleDevURI
from archivo.models.ContentNegotiation import RDF_Type, get_file_extension, get_accept_header
from archivo.models.CrawlingResponse import CrawlingResponse
from archivo.models.DatabusIdentifier import DatabusFileMetadata, DatabusVersionIdentifier
from archivo.models.DataWriter import DataWriter
from archivo.utils import ontoFiles, stringTools, graph_handling, feature_plugins, docTemplates, generatePoms, \
    archivoConfig, parsing
from archivo.utils.validation import TestSuite


class ArchivoVersion:
    def __init__(
            self,
            confirmed_nir: str,
            crawling_result: CrawlingResponse,
            ontology_graph: rdflib.Graph,
            databus_version_identifier: DatabusVersionIdentifier,
            test_suite: TestSuite,
            access_date: datetime,
            logger: Logger,
            source: str,
            data_writer: DataWriter,
            semantic_version: str = "1.0.0",
            dev_uri: str = "",
            retrieval_errors=None,
            user_output=None,
    ):
        if user_output is None:
            user_output = list()
        if retrieval_errors is None:
            retrieval_errors = list()
        # the nir is the identity of the ontology, confirmed by checking for the triple inside the ontology itself
        # not to be confused with the location of the ontology, or the URI the crawl started with
        self.nir = confirmed_nir
        # data writer -> abstraction for handling the writing process
        self.data_writer = data_writer
        self.db_version_identifier = databus_version_identifier
        self.crawling_result = crawling_result
        self.ontology_graph = ontology_graph
        self.isDev = False if dev_uri == "" else True
        self.location_uri = crawling_result.response.url if dev_uri == "" else dev_uri
        self.reference_uri = dev_uri if self.isDev else self.nir
        self.test_suite = test_suite
        self.access_date = access_date
        self.source = source
        self.semantic_version = semantic_version
        self.user_output = user_output
        self.logger = logger
        self.retrieval_errors = retrieval_errors
        if len(self.crawling_result.response.history) > 0:
            self.nir_header = str(self.crawling_result.response.history[0].headers)
        else:
            self.nir_header = ""

        # initialize a empty dict for the metadata file

        self.metadata_dict = {"test-results": {}, "http-data": {}, "ontology-info": {}, "logs": {}}

        self.stars_dict = {}

    def __generate_parsed_rdf(self):

        for parsing_type in RDF_Type:
            parsing_result = parsing.parse_rdf_from_string(self.crawling_result.rdf_content,
                                                           self.nir,
                                                           self.crawling_result.rdf_type,
                                                           parsing_type)
            shasum, content_length = stringTools.get_content_stats(bytes(parsing_result.parsed_rdf))
            db_file_metadata = DatabusFileMetadata(version_identifier=self.db_version_identifier,
                                                   content_variants={"type": "parsed"},
                                                   file_extension=get_file_extension(get_accept_header(parsing_type)),
                                                   sha_256_sum=shasum,
                                                   content_length=content_length)
            self.data_writer.write_databus_file(parsing_result.parsed_rdf, db_file_metadata)

    def __generate_shacl_reports(self):

        shacl_report_mappings = {
            self.test_suite.archivo_conformity_test: ("archivoMetadata", None),
            self.test_suite.license_existence_check: ("minLicense", "License-I"),
            self.test_suite.license_property_check: ("goodLicense", "License-II"),
            self.test_suite.lodeReadyValidation: ("lodeMetadata", "lode-conform")
        }

        for shacl_report_fun, id_tuple in shacl_report_mappings:
            validates_cv, report_key = id_tuple
            (
                conforms,
                report_graph,
                report_text,
            ) = shacl_report_fun(self.ontology_graph)

            serialized_report = graph_handling.serialize_graph(report_graph, rdf_format="turtle")
            shasum, content_length = stringTools.get_content_stats(bytes(serialized_report))
            db_file_metadata = DatabusFileMetadata(version_identifier=self.db_version_identifier,
                                                   content_variants={"type": "shaclReport", "validates": validates_cv},
                                                   file_extension="ttl",
                                                   sha_256_sum=shasum,
                                                   content_length=content_length,
                                                   compression=None
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
            shasum, content_length = stringTools.get_content_stats(bytes(docustring))
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







    def generate_files(self):

        self.__generate_parsed_rdf()
        self.__generate_shacl_reports()
        self.__generate_documentation_files()



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
            snapshot_url=self.location_uri,
        )

    def handleTrackThis(self):
        if self.isDev:
            return None, None
        trackThisURI = graph_handling.get_track_this_uri(self.ontology_graph)
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
                    sha256_length_tuple=(metadata.sha_256_sum, metadata.content_length)
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
                    date=str(timestamp_now),
                )

        return description

    def __get_license(self) -> str:

        found_license = inspectVocabs.get_license(self.ontology_graph)
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
            dataset = databusclient.createDataset(
                version_id=f"{archivoConfig.DATABUS_BASE}/{self.db_version_identifier}",
                title=title,
                abstract=comment,
                description=description,
                license_url=license_url,
                distributions=distribs
            )
        else:
            dataset = databusclient.createDataset(
                version_id=f"{archivoConfig.DATABUS_BASE}/{self.db_version_identifier}",
                title=title,
                abstract=comment,
                description=description,
                license_url=license_url,
                distributions=distribs,
                group_title=group_info["title"],
                group_description=group_info["description"]
            )

        return dataset
