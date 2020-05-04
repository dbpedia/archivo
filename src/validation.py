from pyshacl import validate
from rdflib import Graph
import inspectVocabs
import os
import sys
import subprocess
import re
#from owlready2 import get_ontology, sync_reasoner_pellet

pelletPath = "/home/denis/Workspace/Job/pellet/cli/target/pelletcli/bin/pellet"
profileCheckerJar="/home/denis/Downloads/profilechecker-1.1.0.jar"

consistencyRegex = re.compile(r"Consistent: (Yes|No)")

def loadShaclGraph(filename, pubId=None):
    shaclgraph = Graph()
    with open(os.path.abspath(os.path.dirname(sys.argv[0])) + os.sep + "shacl" + os.sep + filename, "r") as shaclFile:
        shaclgraph.parse(shaclFile, format="turtle", publicID=pubId)
    return shaclgraph

licenseViolationGraph = loadShaclGraph("license-I.ttl", pubId="https://raw.githubusercontent.com/dbpedia/Archivo/master/shacl-library/license-I.ttl")
licenseWarningGraph = loadShaclGraph("license-II.ttl", pubId="https://raw.githubusercontent.com/dbpedia/Archivo/master/shacl-library/license-II.ttl")
lodeTestGraph = loadShaclGraph("LODE.ttl", pubId="https://raw.githubusercontent.com/dbpedia/Archivo/master/shacl-library/LODE.ttl")

# returns triple with (conforms : bool, result_graph : rdflib.Graph, result_text: string)
def licenseViolationValidation(ontograph):
    r = validate(ontograph, shacl_graph=licenseViolationGraph, ont_graph=None, inference='none', abort_on_error=False, meta_shacl=False, debug=False)
    return r

def lodeReadyValidation(ontograph):
    r = validate(ontograph, shacl_graph=lodeTestGraph, ont_graph=None, inference="none", abort_on_error=False, meta_shacl=False, debug=False)
    return r

def licenseWarningValidation(ontograph):
    r = validate(ontograph, shacl_graph=licenseWarningGraph, ont_graph=None, inference="none", abort_on_error=False, meta_shacl=False, debug=False)
    return r

def getTurtleGraph(graph, base=None):    
    return graph.serialize(format='turtle', encoding="utf-8", base=base).decode("utf-8")

def runPelletCommand(ontofile, command, ignoreImports=False):
    if ignoreImports:
        process = subprocess.Popen([pelletPath, command, "--ignore-imports", "-v", ontofile], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        process = subprocess.Popen([pelletPath, command, "-v", ontofile], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    return stdout.decode("utf-8"), stderr.decode("utf-8"), process.returncode

def getConsistency(ontofile, ignoreImports=False):
    stdout, stderr, returncode = runPelletCommand(ontofile, "consistency", ignoreImports=ignoreImports)
    if returncode == 0:
        match = consistencyRegex.search(stdout)
        if match != None:
            if match.group(1) == "Yes":
                return True, stderr + "\n\n" + stdout
            else:
                return False, stderr + "\n\n" + stdout
        else:
            return False, stderr + "\n\n" + stdout
    else:
        return False, stderr + "\n\n" + stdout

def getPelletInfo(ontofile, ignoreImports=False):
    stdout, stderr, returncode = runPelletCommand(ontofile, "info", ignoreImports=ignoreImports)
    return stderr + "\n\n" + stdout

def getProfileCheck(ontofile):
    process = subprocess.Popen(["java", "-jar", profileCheckerJar, ontofile, "--all"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    return stdout.decode("utf-8"), stderr.decode("utf-8")
