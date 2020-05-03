from pyshacl import validate
from rdflib import Graph
import inspectVocabs
import os
import sys
from owlready2 import get_ontology, sync_reasoner_pellet

def loadShaclGraph(filename, pubId=None):
    shaclgraph = Graph()
    with open(os.path.abspath(os.path.dirname(sys.argv[0])) + os.sep + "shacl" + os.sep + filename, "r") as shaclFile:
        shaclgraph.parse(shaclFile, format="turtle", publicID=pubId)
    return shaclgraph

licenseShaclGraph = loadShaclGraph("license-test.ttl", pubId="https://raw.githubusercontent.com/dbpedia/Archivo/master/src/shacl/license-test.ttl")
#metadataTestGraph = loadShaclGraph("metadata-test.ttl", pubId="https://raw.githubusercontent.com/dbpedia/Archivo/master/src/shacl/metadata-test.ttl")

# returns triple with (conforms : bool, result_graph : rdflib.Graph, result_text: string)
def licenseValidation(ontograph):
    r = validate(ontograph, shacl_graph=licenseShaclGraph, ont_graph=None, inference='none', abort_on_error=False, meta_shacl=False, debug=False)
    return r


def getTurtleGraph(graph, base=None):    
    return graph.serialize(format='turtle', encoding="utf-8", base=base).decode("utf-8")

def consistencyCheck(ontofile):
    onto = get_ontology(ontofile).load()
    with onto:sync_reasoner_pellet()
    onto.save("consistencyResult.owl")