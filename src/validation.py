from pyshacl import validate
from rdflib import Graph
import inspectVocabs
import os
import sys
from owlready2 import get_ontology, sync_reasoner_pellet

def loadShaclGraph(filename):
    shaclgraph = Graph()
    shaclgraph.parse(os.path.abspath(os.path.dirname(sys.argv[0])) + os.sep + filename, format="turtle")
    return shaclgraph

licenseShaclGraph = loadShaclGraph("shacl-license-test.ttl")

# returns triple with (conforms : bool, result_graph : rdflib.Graph, result_text: string)
def licenseValidation(ontograph):
    r = validate(ontograph, shacl_graph=licenseShaclGraph, ont_graph=None, inference='none', abort_on_error=False, meta_shacl=False, debug=False)
    return r


def getTurtleGraph(graph, base=None):    
    graph.serialize(format='turtle', encoding="utf-8", base=base)

def consistencyCheck(ontofile):
    onto = get_ontology(ontofile).load()
    with onto:sync_reasoner_pellet()
    onto.save("consistencyResult.owl")