import hashlib
import os
from datetime import datetime
from logging import Logger
from string import Template
from typing import Dict
import databusclient
from rdflib import URIRef, Literal

from archivo.crawling.discovery import handleDevURI
from archivo.models.ContentNegotiation import RDF_Type, get_file_extension, get_accept_header
from archivo.models.CrawlingResponse import CrawlingResponse
from archivo.models.DatabusIdentifier import DatabusFileMetadata, DatabusVersionIdentifier
from archivo.models.FileWriter import DataWriter
from archivo.utils import ontoFiles, stringTools, inspectVocabs, feature_plugins, docTemplates, generatePoms, \
    archivoConfig, parsing
from archivo.utils.validation import TestSuite


class ArchivoVersion:
    def __init__(
            self,
            confirmed_nir: str,
            crawling_result: CrawlingResponse,
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

    def generate_parsed_rdf(self):

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

    def generate_shacl_reports(self):

        shacl_report_mappings = {
            self.test_suite.archivoConformityTest: ("archivoMetadata", None),
            self.test_suite.licenseViolationValidation: ("minLicense", "License-I"),
            self.test_suite.licenseWarningValidation: ("goodLicense", "License-II"),
            self.test_suite.lodeReadyValidation: ("lodeMetadata", "lode-conform")
        }

        for shacl_report_fun, id_tuple in shacl_report_mappings:
            validates_cv, report_key = id_tuple
            (
                conforms,
                report_graph,
                report_text,
            ) = shacl_report_fun(self.graph)

            serialized_report = inspectVocabs.get_turtle_graph(report_graph)
            shasum, content_length = stringTools.get_content_stats(bytes(serialized_report))
            db_file_metadata = DatabusFileMetadata(version_identifier=self.db_version_identifier,
                                                   content_variants={"type": "shaclReport", "validates": validates_cv},
                                                   file_extension="ttl",
                                                   sha_256_sum=shasum,
                                                   content_length=content_length
                                                   )
            self.data_writer.write_databus_file(serialized_report, db_file_metadata)

            if report_key:
                self.metadata_dict["test-results"][report_key] = conforms

    def generateFiles(self):

        self.generate_parsed_rdf()
        self.generate_shacl_reports()


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

    def __get_distribution_of_file(self, filename: str) -> str:
        only_name = filename.split(".")[0]
        ftype = filename.split(".")[1]

        cv_strings = only_name.split("_")[1:]

        # get cvs from file

        cvs = {}

        for cv_string in cv_strings:
            key = cv_string.split("=")[0]
            val = cv_string.split("=")[1]
            cvs[key] = val

        # shasum and filelength
        BUF_SIZE = 65536

        file_length = 0
        sha256sum = hashlib.sha256()
        with open(os.path.join(self.file_path, filename)) as f:
            while True:
                data = f.read(BUF_SIZE)
                if not data:
                    break
                file_length += len(data)
                sha256sum.update(data)

        distrib = databusclient.create_distribution(
            url=f"{archivoConfig.download_url_base}/{self.group}/{self.artifact}/{self.version}/{filename}",
            cvs=cvs,
            file_format=ftype,
            sha256_length_tuple=(sha256sum.hexdigest(), file_length)
        )
        return distrib

    def __get_label(self) -> str:
        label = self.nir if not self.isDev else self.nir + " DEV"

        if self.graph is not None:
            label_found = inspectVocabs.getLabel(self.graph)
            if label_found is not None:
                label = label_found if not self.isDev else label_found + " DEV"
        return label

    def __get_comment(self) -> str:
        comment = Template(docTemplates.default_explaination).safe_substitute(
            non_information_uri=self.reference_uri
        )

        if self.graph is not None:
            found_comment = inspectVocabs.getComment(self.graph)
            if found_comment is not None:
                comment = found_comment

        return comment

    def __get_description(self) -> str:
        timestamp_now = datetime.strptime(self.version, "%Y.%m.%d-%H%M%S")
        description = (
            Template(docTemplates.description)
            if not self.isDev
            else Template(docTemplates.description_dev)
        )

        if self.graph is not None:
            found_description = inspectVocabs.getDescription(self.graph)
            versionIRI = inspectVocabs.getOwlVersionIRI(self.graph)
            if found_description is not None:
                description = (
                        description.safe_substitute(
                            non_information_uri=self.nir,
                            snapshot_url=self.location_uri,
                            owl_version_iri=versionIRI,
                            date=str(timestamp_now),
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

        found_license = inspectVocabs.getLicense(self.graph)
        if isinstance(found_license, URIRef):
            found_license = str(found_license).strip("<>")
        elif isinstance(found_license, Literal):
            # if license is literal: error uri
            found_license = docTemplates.license_literal_uri

        return found_license

    def build_databus_jsonld(self, group_info=None) -> Dict:

        if group_info is None:
            group_info = {}

        publish_files = [f for f in os.listdir(self.file_path) if os.path.isfile(f)]

        distribs = [self.__get_distribution_of_file(fname) for fname in publish_files]

        title = self.__get_label()
        comment = self.__get_comment()
        description = self.__get_description()
        license_url = self.__get_license()
        if group_info == {}:
            dataset = databusclient.createDataset(
                version_id=f"{archivoConfig.download_url_base}/{self.group}/{self.artifact}/{self.version}",
                title=title,
                abstract=comment,
                description=description,
                license_url=license_url,
                distributions=distribs
            )
        else:
            dataset = databusclient.createDataset(
                version_id=f"{archivoConfig.download_url_base}/{self.group}/{self.artifact}/{self.version}",
                title=title,
                abstract=comment,
                description=description,
                license_url=license_url,
                distributions=distribs,
                group_title=group_info["title"],
                group_description=group_info["description"]
            )

        return dataset
