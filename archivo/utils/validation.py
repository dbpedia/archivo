from pyshacl import validate
from rdflib import Graph, URIRef
from utils import inspectVocabs, archivoConfig
import os
import sys
import subprocess
import re
import traceback

# from owlready2 import get_ontology, sync_reasoner_pellet


consistencyRegex = re.compile(r"Consistent: (Yes|No)")


def loadShaclGraph(filename, pubId=None):
    shaclgraph = Graph()
    with open(
        os.path.abspath(os.path.dirname(sys.argv[0]))
        + os.sep
        + "shacl"
        + os.sep
        + filename,
        "r",
    ) as shaclFile:
        shaclgraph.parse(shaclFile, format="turtle", publicID=pubId)
    return shaclgraph


# needed for gunicorn
def loadShacl(filepath, pubId=None):
    shaclgraph = Graph()
    with open(filepath, "r") as shaclfile:
        shaclgraph.parse(shaclfile, format="turtle", publicID=pubId)
    return shaclgraph


class TestSuite:

    pelletPath = archivoConfig.pelletPath
    profileCheckerJar = archivoConfig.profileCheckerJar

    def __init__(self, archivoPath):
        self.licenseViolationGraph = loadShacl(
            os.path.join(archivoPath, "shacl", "license-I.ttl"),
            pubId="https://raw.githubusercontent.com/dbpedia/Archivo/master/shacl-library/license-I.ttl",
        )
        self.licenseWarningGraph = loadShacl(
            os.path.join(archivoPath, "shacl", "license-II.ttl"),
            pubId="https://raw.githubusercontent.com/dbpedia/Archivo/master/shacl-library/license-II.ttl",
        )
        self.lodeTestGraph = loadShacl(
            os.path.join(archivoPath, "shacl", "LODE.ttl"),
            pubId="https://raw.githubusercontent.com/dbpedia/Archivo/master/shacl-library/LODE.ttl",
        )
        self.displayAxiomsPath = os.path.join(archivoPath, "helpingBinaries", "DisplayAxioms.jar")
        self.archivoTestGraph = loadShacl(
            os.path.join(archivoPath, "shacl", "archivo.ttl"),
            pubId="https://raw.githubusercontent.com/dbpedia/Archivo/master/shacl-library/archivo.ttl",
        )

    def archivoConformityTest(self, ontograph):
        success, report_graph, report_text = validate(
            ontograph,
            shacl_graph=self.archivoTestGraph,
            ont_graph=None,
            inference="none",
            abort_on_error=False,
            meta_shacl=False,
            debug=False,
            advanced=True,
        )
        report_graph.namespace_manager.bind("sh", URIRef("http://www.w3.org/ns/shacl#"))
        return success, report_graph, report_text

    def licenseViolationValidation(self, ontograph):
        success, report_graph, report_text = validate(
            ontograph,
            shacl_graph=self.licenseViolationGraph,
            ont_graph=None,
            inference="none",
            abort_on_error=False,
            meta_shacl=False,
            debug=False,
            advanced=True,
        )
        report_graph.namespace_manager.bind("sh", URIRef("http://www.w3.org/ns/shacl#"))
        return success, report_graph, report_text

    def licenseWarningValidation(self, ontograph):
        success, report_graph, report_text = validate(
            ontograph,
            shacl_graph=self.licenseWarningGraph,
            ont_graph=None,
            inference="none",
            abort_on_error=False,
            meta_shacl=False,
            debug=False,
            advanced=True,
        )
        report_graph.namespace_manager.bind("sh", URIRef("http://www.w3.org/ns/shacl#"))
        return success, report_graph, report_text

    def lodeReadyValidation(self, ontograph):
        success, report_graph, report_text = validate(
            ontograph,
            shacl_graph=self.lodeTestGraph,
            ont_graph=None,
            inference="none",
            abort_on_error=False,
            meta_shacl=False,
            debug=False,
            advanced=True,
        )
        report_graph.namespace_manager.bind("sh", URIRef("http://www.w3.org/ns/shacl#"))
        return success, report_graph, report_text

    def getProfileCheck(self, ontofile):
        process = subprocess.run(
            ["java", "-jar", self.profileCheckerJar, ontofile, "--all"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return process.stdout.decode("utf-8"), process.stderr.decode("utf-8")

    def runPelletCommand(self, ontofile, command, parameters=[]):
        pelletCommand = [self.pelletPath, command]
        for parameter in parameters:
            pelletCommand.append(parameter)
        pelletCommand.append(ontofile)

        try:
            process = subprocess.run(
                pelletCommand,
                timeout=300,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            return (
                process.stdout.decode("utf-8"),
                process.stderr.decode("utf-8"),
                process.returncode,
            )
        except TimeoutError:
            return "", "Timeout in pellet", 999
        except subprocess.TimeoutExpired:
            return "", "Timeout in pellet", 999

    def getPelletInfo(self, ontofile, ignoreImports=False):
        params = ["-v"]
        if ignoreImports:
            params.append("--ignore-imports")
        stdout, stderr, returncode = self.runPelletCommand(
            ontofile, "info", parameters=params
        )
        return stderr + "\n\n" + stdout

    def getConsistency(self, ontofile, ignoreImports=False):
        params = ["-v", "--loader", "Jena"]
        if ignoreImports:
            params.append("--ignore-imports")
        stdout, stderr, returncode = self.runPelletCommand(
            ontofile, "consistency", parameters=params
        )
        if returncode == 0:
            match = consistencyRegex.search(stdout)
            if match != None:
                return match.group(1), stderr + "\n\n" + stdout
            else:
                return (
                    "Error - couldn't find consistency string",
                    stderr + "\n\n" + stdout,
                )
        elif returncode == 999:
            return "Error - pellet timed out", stderr + "\n\n" + stdout
        else:
            return "Error - Exit " + str(returncode), stderr + "\n\n" + stdout

    def getAxiomsOfOntology(self, ontologyPath):
        process = subprocess.Popen(
            ["java", "-jar", self.displayAxiomsPath, ontologyPath],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = process.communicate()

        axiomSet = stdout.decode("utf-8").split("\n")
        if process.returncode == 0:
            success = True
            return success, set(
                [axiom.strip() for axiom in axiomSet if axiom.strip() != ""]
            )
        else:
            success = False
            return success, stderr.decode("utf-8").split("\n")

    def runAllTests(self, pathToRdfFile, artifact):
        ontoGraph = inspectVocabs.getGraphOfVocabFile(pathToRdfFile)
        filePath, _ = os.path.split(pathToRdfFile)
        (
            conformsLicense,
            reportGraphLicense,
            reportTextLicense,
        ) = self.licenseViolationValidation(ontoGraph)
        with open(
            os.path.join(
                filePath, artifact + "_type=shaclReport_validates=minLicense.ttl"
            ),
            "w+",
        ) as minLicenseFile:
            print(inspectVocabs.getTurtleGraph(reportGraphLicense), file=minLicenseFile)
        conformsLode, reportGraphLode, reportTextLode = self.lodeReadyValidation(
            ontoGraph
        )
        with open(
            os.path.join(
                filePath, artifact + "_type=shaclReport_validates=lodeMetadata.ttl"
            ),
            "w+",
        ) as lodeMetaFile:
            print(inspectVocabs.getTurtleGraph(reportGraphLode), file=lodeMetaFile)
        (
            conformsLicense2,
            reportGraphLicense2,
            reportTextLicense2,
        ) = self.licenseWarningValidation(ontoGraph)
        with open(
            os.path.join(
                filePath, artifact + "_type=shaclReport_validates=goodLicense.ttl"
            ),
            "w+",
        ) as advLicenseFile:
            print(
                inspectVocabs.getTurtleGraph(reportGraphLicense2), file=advLicenseFile
            )
        # checks consistency with and without imports
        isConsistent, output = self.getConsistency(
            os.path.join(filePath, artifact + "_type=parsed.ttl"), ignoreImports=False
        )
        isConsistentNoImports, outputNoImports = self.getConsistency(
            os.path.join(filePath, artifact + "_type=parsed.ttl"), ignoreImports=True
        )
        with open(
            os.path.join(
                filePath, artifact + "_type=pelletConsistency_imports=FULL.txt"
            ),
            "w+",
        ) as consistencyReport:
            print(output, file=consistencyReport)
        with open(
            os.path.join(
                filePath, artifact + "_type=pelletConsistency_imports=NONE.txt"
            ),
            "w+",
        ) as consistencyReportNoImports:
            print(outputNoImports, file=consistencyReportNoImports)
        # print pellet info files
        with open(
            os.path.join(filePath, artifact + "_type=pelletInfo_imports=FULL.txt"), "w+"
        ) as pelletInfoFile:
            print(
                self.getPelletInfo(
                    os.path.join(filePath, artifact + "_type=parsed.ttl"),
                    ignoreImports=False,
                ),
                file=pelletInfoFile,
            )
        with open(
            os.path.join(filePath, artifact + "_type=pelletInfo_imports=NONE.txt"), "w+"
        ) as pelletInfoFileNoImports:
            print(
                self.getPelletInfo(
                    os.path.join(filePath, artifact + "_type=parsed.ttl"),
                    ignoreImports=True,
                ),
                file=pelletInfoFileNoImports,
            )
