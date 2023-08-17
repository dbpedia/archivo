import os
import sys
from typing import List, Optional, Dict

import rdflib
import requests
from rdflib import OWL, RDFS, RDF, URIRef, ConjunctiveGraph, Graph
from rdflib.namespace import DCTERMS, DC, SKOS
import json
import traceback
from archivo.utils import string_tools, archivoConfig
from urllib.parse import quote as urlQuote
from urllib.parse import urlparse

from archivo.utils.ArchivoExceptions import UnknownRDFFormatException

descriptionNamespaceGraph = Graph()
descriptionNamespaceGraph.bind("dct", DCTERMS)
descriptionNamespaceGraph.bind("dc", DC)
descriptionNamespaceGraph.bind("rdfs", RDFS)

header_rdflib_mapping = {
    "application/ntriples": "nt",
    "application/rdf+xml": "xml",
    "text/turtle": "turtle",
    "application/xhtml": "rdfa",
}


def get_graph_by_uri(uri: str, rdf_format: str = None) -> Graph:
    """Loads the RDF content behind URI into an RDFlib Graph instance"""

    if rdf_format is None:
        rdf_format = rdflib.util.guess_format(uri)
    if rdf_format is None:
        raise UnknownRDFFormatException(f"Could nt determine the rdf format of {uri}")

    graph = rdflib.Graph()
    graph.parse(uri, format=rdf_format)
    return graph


def get_graph_of_string(rdf_string: str, content_type: str) -> Graph:
    """Builds rdflib Graph of the string based on the HTTP content type of the string. Default content type is xml"""

    graph = rdflib.Graph()
    graph.parse(data=rdf_string, format=header_rdflib_mapping.get(content_type, "xml"))
    return graph


def serialize_graph(graph: rdflib.Graph, rdf_format: str = "turtle", base=None) -> str:
    """Serializes an RDFlib Graph as a string"""

    return graph.serialize(format=rdf_format, encoding="utf-8", base=base).decode("utf-8")


def get_defined_uris(nir: str, graph: rdflib.Graph) -> List[str]:
    """Returns a list of defined resources of an ontology. The defined resources MUST be in the scope of the ontology NIR.
    The subject is not relevant, it considers only the objects of the properties defined in the config."""

    prop_string = " ".join(
        [f"<{defines_prop}>" for defines_prop in archivoConfig.defines_properties]
    )
    query_string = "\n".join(
        [
            "SELECT DISTINCT ?defResource",
            "WHERE {",
            " VALUES ?prop { %s }" % prop_string,
            " ?s ?prop ?defResource .",
            "}",
        ]
    )

    result = graph.query(query_string)

    nir_domain = urlparse(nir).netloc

    if result is None:
        return []
    else:
        return [
            str(line[0])
            for line in result
            if len(line) > 0 and nir_domain == urlparse(line[0]).netloc
        ]


# Relevant properties:
# rdfs:label
# rdfs:comment
# rdfs:description
# dcterms:license
# dcterms:title
# dcterms:description
# dcterms:abstract
# dc:title
# dc:description


def get_owl_version_iri(graph: Graph) -> Optional[str]:
    """Returns the value of owl:versionIRI (if available, else None)"""

    queryString = (
        "SELECT DISTINCT ?versionIRI\n"
        "WHERE {\n"
        " VALUES ?type { owl:Ontology skos:ConceptScheme }\n"
        " ?uri a ?type .\n"
        " ?uri owl:versionIRI ?versionIRI ."
        "} LIMIT 1"
    )
    result = graph.query(queryString, initNs={"owl": OWL, "rdf": RDF, "skos": SKOS})
    if result is not None and len(result) > 0:
        for row in result:
            return row[0]
    else:
        return None


def get_ontology_uris(graph: Graph) -> List[str]:
    """Get a List of ontology URIs of an ontology graph. Currently either owl:Ontology or skos:ConceptScheme"""

    queryString = (
        "SELECT DISTINCT ?uri\n"
        "WHERE {\n"
        " VALUES ?type { owl:Ontology skos:ConceptScheme }\n"
        " ?uri a ?type .\n"
        "}"
    )
    result = graph.query(queryString, initNs={"owl": OWL, "rdf": RDF, "skos": SKOS})
    if result is not None and len(result) > 0:
        return [str(row[0]) for row in result]
    else:
        return []


def get_label(graph: Graph) -> Optional[str]:
    """Best effort label finding"""

    queryString = (
        "SELECT DISTINCT ?prefLabel ?label ?dctTitle ?dcTitle \n"
        "WHERE {\n"
        " VALUES ?type { owl:Ontology skos:ConceptScheme }\n"
        " ?uri a ?type .\n"
        ' OPTIONAL { ?uri skos:prefLabel ?preflabel FILTER (lang(?preflabel) = "" || langMatches(lang(?preflabel), "en"))}\n'
        ' OPTIONAL { ?uri rdfs:label ?label FILTER (lang(?label) = "" || langMatches(lang(?label), "en"))}\n'
        ' OPTIONAL { ?uri dcterms:title ?dctTitle FILTER (lang(?dctTitle) = "" || langMatches(lang(?dctTitle), "en"))}\n'
        ' OPTIONAL { ?uri dc:title ?dcTitle FILTER (lang(?dcTitle) = "" || langMatches(lang(?dcTitle), "en"))}\n'
        "} LIMIT 1"
    )
    result = graph.query(
        queryString,
        initNs={"owl": OWL, "skos": SKOS, "rdfs": RDFS, "dcterms": DCTERMS, "dc": DC},
    )
    if result is not None and len(result) > 0:
        for row in result:
            for value in row:
                if value is not None:
                    return string_tools.get_first_line(value)
    else:
        return None


def get_description(graph: Graph) -> Optional[str]:
    """Best effort description finding"""

    resultStrings = []
    queryString = (
        "SELECT DISTINCT ?descProp ?description\n"
        "WHERE {\n"
        " VALUES ?descProp { rdfs:description dcterms:description dc:description rdfs:comment dcterms:abstract }"
        " VALUES ?type { owl:Ontology skos:ConceptScheme }\n"
        " ?uri a ?type .\n"
        " ?uri ?descProp ?description .\n"
        ' FILTER (lang(?description) = "" || langMatches(lang(?description), "en"))'
        "}"
    )
    result = graph.query(
        queryString,
        initNs={"owl": OWL, "rdfs": RDFS, "dcterms": DCTERMS, "dc": DC, "skos": SKOS},
    )
    if result is not None and len(result) > 0:
        for row in result:
            descString = (
                f"### {row[0].n3(descriptionNamespaceGraph.namespace_manager)}\n\n"
                f"{row[1]}"
            )
            resultStrings.append(descString)
        return "\n\n".join(resultStrings)
    else:
        return None


def get_track_this_uri(graph: Graph) -> Optional[str]:
    """Tries finding a value for track_this URI defined in the config"""

    queryString = (
        "SELECT DISTINCT ?trackURI\n"
        "WHERE {\n"
        " VALUES ?type { owl:Ontology skos:ConceptScheme }\n"
        " ?uri a ?type .\n"
        f" ?uri <{archivoConfig.track_this_uri}> ?trackURI ."
        "}"
    )
    result = graph.query(queryString, initNs={"owl": OWL, "rdf": RDF, "skos": SKOS})
    if result is not None and len(result) > 0:
        for row in result:
            return str(row[0])
    else:
        return None


# possible rdfs:comments for the databus


def get_comment(graph: Graph) -> Optional[str]:
    """Best effort comment finding"""

    queryString = (
        "SELECT DISTINCT ?dctAbstract ?dctDescription ?dcDescription \n"
        "WHERE {\n"
        " VALUES ?type { owl:Ontology skos:ConceptScheme }\n"
        " ?uri a ?type .\n"
        ' OPTIONAL { ?uri dcterms:description ?dctDescription FILTER (lang(?dctDescription) = "" || langMatches(lang(?dctDescription), "en")) }\n'
        ' OPTIONAL { ?uri dc:description ?dcDescription FILTER (lang(?dcDescription) = "" || langMatches(lang(?dcDescription), "en")) }\n'
        ' OPTIONAL { ?uri rdfs:comment ?rdfsComment FILTER (lang(?rdfsComment) = "" || langMatches(lang(?rdfsComment), "en")) }\n'
        ' OPTIONAL { ?uri dcterms:abstract ?dctAbstract FILTER (lang(?dctAbstract) = "" || langMatches(lang(?dctAbstract), "en")) }\n'
        "} LIMIT 1"
    )
    result = graph.query(
        queryString,
        initNs={"owl": OWL, "rdfs": RDFS, "dcterms": DCTERMS, "dc": DC, "skos": SKOS},
    )
    if result is not None and len(result) > 0:
        for row in result:
            for value in row:
                if value is not None and str(value).strip() != "":
                    return string_tools.get_first_sentence(value)
    else:
        return None


# returns the license if there is any
def get_license(graph: Graph) -> Optional[str]:
    """tries finding the license of the ontology using multiple properties"""

    queryString = (
        "SELECT DISTINCT ?license \n"
        "WHERE {\n"
        " VALUES ?licenseProp { dcterms:license xhv:license cc:license dc:license }\n"
        "VALUES ?type { owl:Ontology skos:ConceptScheme }"
        " ?uri a ?type .\n"
        " ?uri ?licenseProp ?license .\n"
        "} LIMIT 1"
    )
    result = graph.query(
        queryString,
        initNs={
            "skos": SKOS,
            "owl": OWL,
            "dcterms": DCTERMS,
            "xhv": URIRef("http://www.w3.org/1999/xhtml/vocab#"),
            "dc": DC,
            "cc": URIRef("http://creativecommons.org/ns#"),
        },
    )
    if result is not None and len(result) > 0:
        for row in result:
            return row[0]
    else:
        return None


# returns the non information resource of an ontology, representing the entity of the ontology
def get_defined_by_uri(graph: Graph) -> Optional[str]:
    """Fetches the first defined by URI of some entity for further discovery"""

    qString = """
        SELECT DISTINCT ?defbyUri
        WHERE {
            VALUES ?prop { rdfs:isDefinedBy skos:inScheme }
            ?s ?prop ?defbyUri .
        } LIMIT 1
        """
    result = graph.query(qString, initNs={"rdfs": RDFS, "skos": SKOS})
    if result is not None and len(result) > 0:
        for row in result:
            return row[0]
    else:
        return None


def checkShaclReport(report_url: str) -> str:
    shaclReportGraph = get_graph_by_uri(report_url)
    if shaclReportGraph == None:
        return "ERROR"
    violationRef = URIRef("http://www.w3.org/ns/shacl#Violation")
    warningRef = URIRef("http://www.w3.org/ns/shacl#Warning")
    infoRef = URIRef("http://www.w3.org/ns/shacl#Info")
    queryString = (
        "SELECT DISTINCT ?severity \n"
        "WHERE {\n"
        " ?s sh:resultSeverity ?severity . \n"
        "}"
    )
    result = shaclReportGraph.query(
        queryString, initNs={"sh": URIRef("http://www.w3.org/ns/shacl#")}
    )

    resultValues = [row[0] for row in result if row != None]
    if violationRef in resultValues:
        return "VIOLATION"
    elif warningRef in resultValues:
        return "WARNING"
    elif infoRef in resultValues:
        return "INFO"
    else:
        return "OK"


def hacky_shacl_content_severity(text: str) -> str:
    if "sh:resultSeverity sh:Violation" in text:
        return "VIOLATION"
    elif "sh:resultSeverity sh:Warning" in text:
        return "WARNING"
    elif "sh:resultSeverity sh:Info" in text:
        return "INFO"
    else:
        return "OK"


def hacky_shacl_report_severity(shacl_report_url: str) -> str:
    try:
        shaclString = requests.get(shacl_report_url).text
    except Exception as e:
        return "ERROR"

    return hacky_shacl_content_severity(shaclString)


def interpret_shacl_graph(graph: Graph) -> Dict[str, Dict[str, List[str]]]:
    violationRef = URIRef("http://www.w3.org/ns/shacl#Violation")
    warningRef = URIRef("http://www.w3.org/ns/shacl#Warning")
    infoRef = URIRef("http://www.w3.org/ns/shacl#Info")

    resultDict = {"violations": None, "warnings": None, "infos": None}

    queryString = (
        "SELECT DISTINCT ?node ?severity ?problem \n"
        "WHERE {\n"
        "?report a sh:ValidationReport .\n"
        "?report sh:result ?result .\n"
        "?result sh:focusNode ?node .\n"
        "?result sh:resultMessage ?problem .\n"
        "?result sh:resultSeverity ?severity .\n"
        "}"
    )

    result = graph.query(
        queryString, initNs={"sh": URIRef("http://www.w3.org/ns/shacl#")}
    )

    for node, severity, problemText in result:
        if severity == violationRef:
            if resultDict["violations"] is None:
                resultDict["violations"] = {}
            if str(problemText) in resultDict["violations"]:
                resultDict["violations"][str(problemText)].append(str(node))
            else:
                resultDict["violations"][str(problemText)] = [str(node)]
        elif severity == warningRef:
            if resultDict["warnings"] is None:
                resultDict["warnings"] = {}
            if str(problemText) in resultDict["warnings"]:
                resultDict["warnings"][str(problemText)].append(str(node))
            else:
                resultDict["warnings"][str(problemText)] = [str(node)]
        elif severity == infoRef:
            if resultDict["infos"] is None:
                resultDict["infos"] = {}
            if str(problemText) in resultDict["infos"]:
                resultDict["infos"][str(problemText)].append(str(node))
            else:
                resultDict["infos"][str(problemText)] = [str(node)]

    return resultDict
