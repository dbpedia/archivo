from typing import Optional, Tuple, Set, List

import rdflib
from pyshacl import validate
from rdflib import Graph, URIRef
from archivo.utils import archivo_config, string_tools
import os
import subprocess
import re
from archivo.utils.archivo_exceptions import UnparseableRDFException

# from owlready2 import get_ontology, sync_reasoner_pellet


consistencyRegex = re.compile(r"Consistent: (Yes|No)")


# needed for gunicorn
def load_shacl_graph(filepath: str, pub_id: Optional[str] = None) -> rdflib.Graph:
    shacl_graph = Graph()
    with open(filepath, "r") as shaclfile:
        shacl_graph.parse(shaclfile, format="turtle", publicID=pub_id)
    return shacl_graph


class TestSuite:
    pelletPath = archivo_config.pelletPath
    profileCheckerJar = archivo_config.profileCheckerJar

    def __init__(self):
        archivo_path = string_tools.get_local_directory()

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

    @staticmethod
    def __run_local_shacl_test(
        ontograph: Graph, testgraph: Graph
    ) -> Tuple[bool, Graph, str]:
        success, report_graph, report_text = validate(
            ontograph,
            shacl_graph=testgraph,
            ont_graph=None,
            inference="none",
            abort_on_error=False,
            meta_shacl=False,
            debug=False,
            advanced=True,
        )
        report_graph.namespace_manager.bind("sh", URIRef("http://www.w3.org/ns/shacl#"))
        return success, report_graph, report_text

    def archivo_conformity_test(self, ontology_graph: Graph) -> Tuple[bool, Graph, str]:
        return self.__run_local_shacl_test(ontology_graph, self.archivoTestGraph)

    def license_existence_check(self, ontograph: Graph) -> Tuple[bool, Graph, str]:
        return self.__run_local_shacl_test(ontograph, self.licenseViolationGraph)

    def license_property_check(self, ontograph: Graph) -> Tuple[bool, Graph, str]:
        return self.__run_local_shacl_test(ontograph, self.licenseWarningGraph)

    def lodeReadyValidation(self, ontograph: Graph) -> Tuple[bool, Graph, str]:
        return self.__run_local_shacl_test(ontograph, self.lodeTestGraph)

    def getProfileCheck(self, ontofile):
        process = subprocess.run(
            ["java", "-jar", self.profileCheckerJar, ontofile, "--all"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return process.stdout.decode("utf-8"), process.stderr.decode("utf-8")

    def run_pellet_command(
        self, ontology_url: str, command: str, parameters: List[str] = None
    ):
        if parameters is None:
            parameters = []
        pelletCommand = [self.pelletPath, command]
        for parameter in parameters:
            pelletCommand.append(parameter)
        pelletCommand.append(ontology_url)

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
        stdout, stderr, returncode = self.run_pellet_command(
            ontofile, "info", parameters=params
        )
        return stderr + "\n\n" + stdout

    def get_consistency(self, ontology_url: str, ignore_imports: bool = False):
        params = ["-v", "--loader", "Jena"]
        if ignore_imports:
            params.append("--ignore-imports")
        stdout, stderr, returncode = self.run_pellet_command(
            ontology_url, "consistency", parameters=params
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

    def get_axioms_of_rdf_ontology(self, ontology_content: str) -> Set[str]:
        process = subprocess.run(
            ["java", "-jar", self.displayAxiomsPath],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            input=bytes(ontology_content, "utf-8"),
        )

        axiomSet = process.stdout.decode("utf-8").split("\n")

        if process.returncode == 0:
            return set([axiom.strip() for axiom in axiomSet if axiom.strip() != ""])
        else:
            raise UnparseableRDFException(process.stderr.decode("utf-8"))


def check_if_consistent(consistent: str, consistent_without_imports: str) -> bool:
    if consistent == "Yes" or consistent_without_imports == "Yes":
        return True
    else:
        return False


def measure_stars(
    rapper_errors: List[str],
    license_1_check: bool,
    license_2_check: bool,
    consistency_check: str,
    consistenty_check_without_imports: str,
) -> int:
    stars = 0
    if rapper_errors == [] or rapper_errors == "":
        stars = stars + 1
    if license_1_check:
        stars = stars + 1

    if not stars == 2:
        return stars

    if check_if_consistent(consistency_check, consistenty_check_without_imports):
        stars = stars + 1
    if license_2_check:
        stars = stars + 1
    return stars
