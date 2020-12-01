import os
import sys
import rdflib
import requests
from rdflib import OWL, RDFS, RDF, URIRef, ConjunctiveGraph, Graph
from rdflib.namespace import DCTERMS, DC, SKOS
import json
import traceback
from utils import stringTools, archivoConfig
from urllib.parse import quote as urlQuote
from io import StringIO

descriptionNamespaceGraph = Graph()
descriptionNamespaceGraph.bind("dct", DCTERMS)
descriptionNamespaceGraph.bind("dc", DC)
descriptionNamespaceGraph.bind("rdfs", RDFS)


def getGraphOfVocabFile(filepath, logger=None):
    try:
        rdfFormat = rdflib.util.guess_format(filepath)
        graph = rdflib.Graph()
        graph.parse(filepath, format=rdfFormat)
        return graph
    except Exception as e:
        if logger is not None:
            logger.exception("Exception in rdflib parsing", exc_info=True)
        else:
            print(f"Problem parsing {filepath}" + str(e))
        return None


def get_graph_of_string(rdf_string, format):
    graph = rdflib.Graph()
    graph.parse(StringIO(rdf_string), format=format)
    return graph


def getTurtleGraph(graph, base=None):
    return graph.serialize(format="turtle", encoding="utf-8", base=base).decode("utf-8")


def getAllClassUris(graph):
    queryString = (
        "SELECT DISTINCT ?classUri \n"
        "WHERE {\n"
        " VALUES ?prop { void:property void:class }\n"
        " ?s ?prop ?classUri .\n"
        "}"
    )
    result = graph.query(
        queryString, initNs={"void": URIRef("http://rdfs.org/ns/void#")}
    )
    if result == None:
        return []
    else:
        return [str(line[0]) for line in result if len(line) > 0]


def getAllPropsAndClasses(graph):
    resultSet = set()
    voidProp = URIRef("http://rdfs.org/ns/void#property")
    voidClass = URIRef("http://rdfs.org/ns/void#class")
    for subj, pred, obj in graph:
        if pred == voidClass or pred == voidProp:
            resultSet.add(str(obj))
    return resultSet


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


def getOwlVersionIRI(graph):
    queryString = (
        "SELECT DISTINCT ?versionIRI\n"
        "WHERE {\n"
        " VALUES ?type { owl:Ontology skos:ConceptScheme }\n"
        " ?uri a ?type .\n"
        " ?uri owl:versionIRI ?versionIRI ."
        "} LIMIT 1"
    )
    result = graph.query(queryString, initNs={"owl": OWL, "rdf": RDF, "skos": SKOS})
    if result != None and len(result) > 0:
        for row in result:
            return row[0]
    else:
        return None


# returns the NIR-URI if it got a owl:Ontology prop, else None
def getNIRUri(graph):
    queryString = (
        "SELECT DISTINCT ?uri\n"
        "WHERE {\n"
        " VALUES ?type { owl:Ontology skos:ConceptScheme }\n"
        " ?uri a ?type .\n"
        "} LIMIT 1"
    )
    result = graph.query(queryString, initNs={"owl": OWL, "rdf": RDF, "skos": SKOS})
    if result != None and len(result) > 0:
        for row in result:
            return row[0]
    else:
        return None


# Returns the possible labels for a ontology
def getLabel(graph):
    queryString = (
        "SELECT DISTINCT ?label ?dctTitle ?dcTitle \n"
        "WHERE {\n"
        " VALUES ?type { owl:Ontology skos:ConceptScheme }\n"
        " ?uri a ?type .\n"
        ' OPTIONAL { ?uri rdfs:label ?label FILTER (lang(?label) = "" || langMatches(lang(?label), "en"))}\n'
        ' OPTIONAL { ?uri dcterms:title ?dctTitle FILTER (lang(?dctTitle) = "" || langMatches(lang(?dctTitle), "en"))}\n'
        ' OPTIONAL { ?uri dc:title ?dcTitle FILTER (lang(?dcTitle) = "" || langMatches(lang(?dcTitle), "en"))}\n'
        "} LIMIT 1"
    )
    result = graph.query(
        queryString,
        initNs={"owl": OWL, "skos": SKOS, "rdfs": RDFS, "dcterms": DCTERMS, "dc": DC},
    )
    if result != None and len(result) > 0:
        for row in result:
            for value in row:
                if value != None:
                    return stringTools.getFirstLine(value)
    else:
        return None


def getDescription(graph):
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
    if result != None and len(result) > 0:
        for row in result:
            descString = (
                f"### {row[0].n3(descriptionNamespaceGraph.namespace_manager)}\n\n"
                f"{row[1]}"
            )
            resultStrings.append(descString)
        return "\n\n".join(resultStrings)
    else:
        return None


def getTrackThisURI(graph):
    queryString = (
        "SELECT DISTINCT ?trackURI\n"
        "WHERE {\n"
        " VALUES ?type { owl:Ontology skos:ConceptScheme }\n"
        " ?uri a ?type .\n"
        f" ?uri <{archivoConfig.track_this_uri}> ?trackURI ."
        "}"
    )
    result = graph.query(queryString, initNs={"owl": OWL, "rdf": RDF, "skos": SKOS})
    if result != None and len(result) > 0:
        for row in result:
            return str(row[0])
    else:
        return None


# possible rdfs:comments for the databus


def getComment(graph):
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
    if result != None and len(result) > 0:
        for row in result:
            for value in row:
                if value != None and str(value).strip() != "":
                    return stringTools.getFirstSentence(value)
    else:
        return None


# returns the license if there is any
def getLicense(graph):
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
    if result != None and len(result) > 0:
        for row in result:
            return row[0]
    else:
        return None


# returns the non information resource of an ontology, representing the entity of the ontology
def getDefinedByUri(ontgraph):
    qString = """
        SELECT DISTINCT ?defbyUri
        WHERE {
            VALUES ?prop { rdfs:isDefinedBy skos:inScheme }
            ?s ?prop ?defbyUri .
        } LIMIT 1
        """
    result = ontgraph.query(qString, initNs={"rdfs": RDFS, "skos": SKOS})
    if result != None and len(result) > 0:
        for row in result:
            return row[0]
    else:
        return None


def changeMetadata(rootdir):
    for groupdir in [
        dir for dir in os.listdir(rootdir) if os.path.isdir(os.path.join(rootdir, dir))
    ]:
        for artifactDir in [
            dir
            for dir in os.listdir(os.path.join(rootdir, groupdir))
            if os.path.isdir(os.path.join(rootdir, groupdir, dir))
        ]:
            print("Generating metadata for", groupdir, artifactDir)
            versionDirs = [
                dir
                for dir in os.listdir(os.path.join(rootdir, groupdir, artifactDir))
                if os.path.isdir(os.path.join(rootdir, groupdir, artifactDir, dir))
                and dir != "target"
            ]
            if versionDirs == []:
                print("Couldnt find version for", groupdir, artifactDir)
                continue
            versionDir = versionDirs[0]
            # filepath = os.path.join(rootdir, groupdir, artifactDir, versionDir, artifactDir + "_type=parsed.ttl")
            jsonPath = os.path.join(
                rootdir,
                groupdir,
                artifactDir,
                versionDir,
                artifactDir + "_type=meta.json",
            )
            if not os.path.isfile(jsonPath):
                continue
            with open(jsonPath, "r") as jsonFile:
                metadata = json.load(jsonFile)

            with open(jsonPath, "w") as jsonFile:
                metadata["semantic-version"] = "0.0.1"
                json.dump(metadata, jsonFile, indent=4, sort_keys=True)


def checkShaclReport(reportURL):
    shaclReportGraph = getGraphOfVocabFile(reportURL)
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


def hackyShaclStringInpection(text):
    if "sh:resultSeverity sh:Violation" in text:
        return "VIOLATION"
    elif "sh:resultSeverity sh:Warning" in text:
        return "WARNING"
    elif "sh:resultSeverity sh:Info" in text:
        return "INFO"
    else:
        return "OK"


def hackyShaclInspection(shaclURL):

    try:
        shaclString = requests.get(shaclURL).text
    except Exception as e:
        return "ERROR"

    if "sh:resultSeverity sh:Violation" in shaclString:
        return "VIOLATION"
    elif "sh:resultSeverity sh:Warning" in shaclString:
        return "WARNING"
    elif "sh:resultSeverity sh:Info" in shaclString:
        return "INFO"
    else:
        return "OK"


def interpretShaclGraph(graph):
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
            if resultDict["violations"] == None:
                resultDict["violations"] = {}
            if str(problemText) in resultDict["violations"]:
                resultDict["violations"][str(problemText)].append(str(node))
            else:
                resultDict["violations"][str(problemText)] = [str(node)]
        elif severity == warningRef:
            if resultDict["warnings"] == None:
                resultDict["warnings"] = {}
            if str(problemText) in resultDict["warnings"]:
                resultDict["warnings"][str(problemText)].append(str(node))
            else:
                resultDict["warnings"][str(problemText)] = [str(node)]
        elif severity == infoRef:
            if resultDict["infos"] == None:
                resultDict["infos"] = {}
            if str(problemText) in resultDict["infos"]:
                resultDict["infos"][str(problemText)].append(str(node))
            else:
                resultDict["infos"][str(problemText)] = [str(node)]

    return resultDict
