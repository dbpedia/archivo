from pyshacl import validate
from rdflib import Graph
from utils import inspectVocabs, archivoConfig
import os
import sys
import subprocess
import re
import traceback
#from owlready2 import get_ontology, sync_reasoner_pellet



consistencyRegex = re.compile(r"Consistent: (Yes|No)")

def loadShaclGraph(filename, pubId=None):
    shaclgraph = Graph()
    with open(os.path.abspath(os.path.dirname(sys.argv[0])) + os.sep + "shacl" + os.sep + filename, "r") as shaclFile:
        shaclgraph.parse(shaclFile, format="turtle", publicID=pubId)
    return shaclgraph

def loadShacl(filepath, pubId=None):
    shaclgraph = Graph()
    with open(filepath, "r") as shaclfile:
        shaclgraph.parse(shaclfile, format="turtle", publicID=pubId)
    return shaclgraph


class TestSuite:

    pelletPath = archivoConfig.pelletPath
    profileCheckerJar=archivoConfig.profileCheckerJar

    def __init__(self, pathToShaclFiles):
        self.licenseViolationGraph = loadShacl(os.path.join(pathToShaclFiles, "license-I.ttl"), pubId="https://raw.githubusercontent.com/dbpedia/Archivo/master/shacl-library/license-I.ttl")
        self.licenseWarningGraph = loadShacl(os.path.join(pathToShaclFiles, "license-II.ttl"), pubId="https://raw.githubusercontent.com/dbpedia/Archivo/master/shacl-library/license-II.ttl")
        self.lodeTestGraph = loadShacl(os.path.join(pathToShaclFiles, "LODE.ttl"), pubId="https://raw.githubusercontent.com/dbpedia/Archivo/master/shacl-library/LODE.ttl")

    def licenseViolationValidation(self, ontograph):
        r = validate(ontograph, shacl_graph=self.licenseViolationGraph, ont_graph=None, inference='none', abort_on_error=False, meta_shacl=False, debug=False)
        return r
    def licenseWarningValidation(self, ontograph):
        r = validate(ontograph, shacl_graph=self.licenseWarningGraph, ont_graph=None, inference='none', abort_on_error=False, meta_shacl=False, debug=False)
        return r
    def lodeReadyValidation(self, ontograph):
        r = validate(ontograph, shacl_graph=self.lodeTestGraph, ont_graph=None, inference='none', abort_on_error=False, meta_shacl=False, debug=False)
        return r
    def getProfileCheck(self, ontofile):
        process = subprocess.run(["java", "-jar", self.profileCheckerJar, ontofile, "--all"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return process.stdout.decode("utf-8"), process.stderr.decode("utf-8")

    def runPelletCommand(self, ontofile, command, parameters=[]):
        pelletCommand = [self.pelletPath, command]
        for parameter in parameters:
            pelletCommand.append(parameter)
        pelletCommand.append(ontofile)

        try:
            process = subprocess.run(pelletCommand, timeout=300, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return process.stdout.decode("utf-8"), process.stderr.decode("utf-8"), process.returncode
        except TimeoutError:
            print("Timeout in consistency check")
            traceback.print_exc(file=sys.stdout)
            return "", "Timeout in pellet", 999

    def getPelletInfo(self, ontofile, ignoreImports=False):
        params=["-v"]
        if ignoreImports:
            params.append("--ignore-imports")
        stdout, stderr, returncode = self.runPelletCommand(ontofile, "info", parameters=params)
        return stderr + "\n\n" + stdout

    def getConsistency(self, ontofile, ignoreImports=False):
        params = ["-v", "--loader", "Jena"]
        if ignoreImports:
            params.append("--ignore-imports")
        stdout, stderr, returncode = self.runPelletCommand(ontofile, "consistency", parameters=params)
        if returncode == 0:
            match = consistencyRegex.search(stdout)
            if match != None:
                    return match.group(1), stderr + "\n\n" + stdout
            else:
                return "Error - couldn't find consistency string", stderr + "\n\n" + stdout
        elif returncode == 999:
            return "Error - pellet timed out", stderr + "\n\n" + stdout
        else:
            return "Error - Exit " + str(returncode), stderr + "\n\n" + stdout