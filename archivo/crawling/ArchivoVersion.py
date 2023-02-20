import hashlib
import os
from datetime import datetime
from string import Template
from typing import Dict
import databusclient
from rdflib import URIRef, Literal

from archivo.crawling.discovery import handleDevURI
from archivo.models.FileWriter import DataWriter
from archivo.utils import ontoFiles, stringTools, inspectVocabs, feature_plugins, docTemplates, generatePoms, \
    archivoConfig


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
        data_writer: DataWriter,
        semanticVersion="1.0.0",
        devURI="",
        retrieval_errors=None,
        user_output=None,
    ):
        if user_output is None:
            user_output = list()
        if retrieval_errors is None:
            retrieval_errors = list()
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

    def generate_parsed_rdf(self):
        parsed_rdf_doc: bytes



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
                    snapshot_url=self.location_url,
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
