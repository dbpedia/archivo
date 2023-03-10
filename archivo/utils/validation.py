from typing import Tuple

import rdflib
from pyshacl import validate
from rdflib import Graph, URIRef
from archivo.utils import graph_handling, archivoConfig, stringTools
import os
import sys
import subprocess
import re

# from owlready2 import get_ontology, sync_reasoner_pellet


consistencyRegex = re.compile(r"Consistent: (Yes|No)")


# needed for gunicorn
def load_shacl_graph(filepath: str, pub_id: str = None) -> rdflib.Graph:
    shacl_graph = Graph()
    with open(filepath, "r") as shaclfile:
        shacl_graph.parse(shaclfile, format="turtle", publicID=pub_id)
    return shacl_graph


class TestSuite:
    pelletPath = archivoConfig.pelletPath
    profileCheckerJar = archivoConfig.profileCheckerJar

    def __init__(self):
        archivo_path = stringTools.get_local_directory()

        self.licenseViolationGraph = load_shacl_graph(
            os.path.join(archivo_path, "shacl", "license-I.ttl"),
            pub_id="https://raw.githubusercontent.com/dbpedia/Archivo/master/shacl-library/license-I.ttl",
        )
        self.licenseWarningGraph = load_shacl_graph(
            os.path.join(archivo_path, "shacl", "license-II.ttl"),
            pub_id="https://raw.githubusercontent.com/dbpedia/Archivo/master/shacl-library/license-II.ttl",
        )
        self.lodeTestGraph = load_shacl_graph(
            os.path.join(archivo_path, "shacl", "LODE.ttl"),
            pub_id="https://raw.githubusercontent.com/dbpedia/Archivo/master/shacl-library/LODE.ttl",
        )
        self.displayAxiomsPath = os.path.join(
            archivo_path, "helpingBinaries", "DisplayAxioms.jar"
        )
        self.archivoTestGraph = load_shacl_graph(
            os.path.join(archivo_path, "shacl", "archivo.ttl"),
            pub_id="https://raw.githubusercontent.com/dbpedia/Archivo/master/shacl-library/archivo.ttl",
        )

    def archivo_conformity_test(self, ontograph: Graph) -> Tuple[bool, Graph, str]:
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

    def license_existence_check(self, ontograph: Graph) -> Tuple[bool, Graph, str]:
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

    def license_property_check(self, ontograph: Graph) -> Tuple[bool, Graph, str]:
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

    def lodeReadyValidation(self, ontograph: Graph) -> Tuple[bool, Graph, str]:
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

    def runPelletCommand(self, ontofile, command, parameters=None):
        if parameters is None:
            parameters = []
        pelletCommand = [self.pelletPath, command]
        for parameter in parameters:
            pelletCommand.append(parameter)
        pelletCommand.append(ontofile)

        try:
            process = subprocess.run(
                pelletCommand,
                timeout=600,
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
            if match is not None:
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
