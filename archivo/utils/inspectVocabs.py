import os
import sys
import rdflib
from rdflib import OWL, RDFS, RDF, URIRef, ConjunctiveGraph
from rdflib.namespace import DCTERMS, DC
import json
import traceback
from utils import stringTools
from urllib.parse import quote as urlQuote

def getGraphOfVocabFile(filepath):
    try:  
        rdfFormat=rdflib.util.guess_format(filepath)
        graph = rdflib.Graph()
        graph.parse(filepath, format=rdfFormat)
        return graph
    except Exception:
        print("Error in parsing:")
        traceback.print_exc(file=sys.stdout)
        return None

def getTurtleGraph(graph, base=None):    
    return graph.serialize(format='turtle', encoding="utf-8", base=base).decode("utf-8")

def getAllClassUris(graph):
    queryString=(
        "SELECT DISTINCT ?classUri \n"
        "WHERE {\n"
        " VALUES ?prop { void:property void:class }\n"
        " ?s ?prop ?classUri .\n"
        "}"
    )
    result = graph.query(queryString, initNs={"void":URIRef("http://rdfs.org/ns/void#")})
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

#Relevant properties:
# rdfs:label
# rdfs:comment
# rdfs:description
# dcterms:license
# dcterms:title
# dcterms:description
# dcterms:abstract
# dc:title
# dc:description

# Returns the relevant rdfs info about a ontology (uri, rdfs:label, rdfs:comment, rdfs:description)
def getRelevantRDFSVocabInfo(graph):
    queryString=(
        "SELECT DISTINCT ?uri ?label ?comment ?description \n"
        "WHERE {\n"
        " ?uri a owl:Ontology .\n"
        " OPTIONAL { ?uri rdfs:label ?label FILTER langMatches(lang(?label), \"en\")}\n"    
        " OPTIONAL { ?uri rdfs:comment ?comment }\n"    
        " OPTIONAL { ?uri rdfs:description ?description }\n"
        "} LIMIT 1"
        )
    result=graph.query(queryString, initNs={"owl": OWL, "rdfs":RDFS})
    if result != None and len(result) > 0:
        for row in result:
            return row
    else:
        return (None, None, None, None)

# returns the NIR-URI if it got a owl:Ontology prop, else None
def getNIRUri(graph):
    queryString=(
        "SELECT DISTINCT ?uri\n"
        "WHERE {\n"
        " ?uri a owl:Ontology .\n"
        "} LIMIT 1"
        )
    result = graph.query(queryString, initNs={"owl": OWL, "rdf":RDF})
    if result != None and len(result) > 0:
        for row in result:
            return row[0]
    else:
        return None



# Returns the possible labels for a ontology
def getLabel(graph):
    queryString=(
        "SELECT DISTINCT ?label ?dctTitle ?dcTitle \n"
        "WHERE {\n"
        " ?uri a owl:Ontology .\n"
        " OPTIONAL { ?uri rdfs:label ?label FILTER (lang(?label) = \"\" || langMatches(lang(?label), \"en\"))}\n"    
        " OPTIONAL { ?uri dcterms:title ?dctTitle FILTER (lang(?dctTitle) = \"\" || langMatches(lang(?dctTitle), \"en\"))}\n"
        " OPTIONAL { ?uri dc:title ?dcTitle FILTER (lang(?dcTitle) = \"\" || langMatches(lang(?dcTitle), \"en\"))}\n"
        "} LIMIT 1"
        )
    result=graph.query(queryString, initNs={"owl": OWL, "rdfs":RDFS, "dcterms":DCTERMS, "dc":DC})
    if result != None and len(result) > 0:
        for row in result:
            for value in row:
                if value != None:
                    return stringTools.getFirstLine(value)
    else:
        return None

# returns the possible descriptions for a ontology
def getPossibleDescriptions(graph):
    queryString=(
        "SELECT DISTINCT ?rdfsDescription ?dctDescription ?dcDescription ?rdfsComment ?dctAbstract\n"
        "WHERE {\n"
        " ?uri a owl:Ontology .\n"
        " OPTIONAL { ?uri rdfs:description ?rdfsDescription }\n"
        " OPTIONAL { ?uri dcterms:description ?dctDescription }\n"
        " OPTIONAL { ?uri dc:description ?dcDescription }\n"    
        " OPTIONAL { ?uri rdfs:comment ?rdfsComment }\n"
        " OPTIONAL { ?uri dcterms:abstract ?dctAbstract }\n"
        "} LIMIT 1"
        )
    result=graph.query(queryString, initNs={"owl": OWL, "rdfs":RDFS, "dcterms":DCTERMS, "dc":DC})
    if result != None and len(result) > 0:
        for row in result:
            return row
    else:
        return None

def getDescription(graph):
    resultStrings = []
    queryString=(
        "SELECT DISTINCT ?descProp ?description\n"
        "WHERE {\n"
        " VALUES ?descProp { rdfs:description dcterms:description dc:description rdfs:comment dcterms:abstract }"
        " ?uri a owl:Ontology .\n"
        " ?uri ?descProp ?description .\n"
        " FILTER (lang(?description) = \"\" || langMatches(lang(?description), \"en\"))"
        "}"
        )
    result=graph.query(queryString, initNs={"owl": OWL, "rdfs":RDFS, "dcterms":DCTERMS, "dc":DC})
    if result != None and len(result) > 0:
        for row in result:
            descString = (
                f"# {row[0].n3(graph.namespace_manager)}\n"
                f"{row[1]}"
            )
            resultStrings.append(descString)
        return "\n\n".join(resultStrings)
    else:
        return None


# possible rdfs:comments for the databus

def getComment(graph):
    queryString=(
        "SELECT DISTINCT ?dctAbstract ?dctDescription ?dcDescription \n"
        "WHERE {\n"
        " ?uri a owl:Ontology .\n"
        " OPTIONAL { ?uri dcterms:description ?dctDescription FILTER (lang(?dctDescription) = \"\" || langMatches(lang(?dctDescription), \"en\")) }\n"
        " OPTIONAL { ?uri dc:description ?dcDescription FILTER (lang(?dcDescription) = \"\" || langMatches(lang(?dcDescription), \"en\")) }\n"    
        " OPTIONAL { ?uri rdfs:comment ?rdfsComment FILTER (lang(?rdfsComment) = \"\" || langMatches(lang(?rdfsComment), \"en\")) }\n"
        " OPTIONAL { ?uri dcterms:abstract ?dctAbstract FILTER (lang(?dctAbstract) = \"\" || langMatches(lang(?dctAbstract), \"en\")) }\n"
        "} LIMIT 1"
        )
    result=graph.query(queryString, initNs={"owl": OWL, "rdfs":RDFS, "dcterms":DCTERMS, "dc":DC})
    if result != None and len(result) > 0:
        for row in result:
            for value in row:
                if value != None and str(value).strip() != "":
                    return stringTools.getFirstSentence(value)
    else:
        return None

# returns the license if there is any
def getLicense(graph):
    queryString=(
        "SELECT DISTINCT ?license \n"
        "WHERE {\n"
        " VALUES ?licenseProp { dcterms:license xhv:license cc:license }"
        " ?uri a owl:Ontology .\n"
        " ?uri ?licenseProp ?license .\n"   
        "} LIMIT 1"
        )
    result=graph.query(queryString, initNs={"owl": OWL, "dcterms": DCTERMS, "xhv":URIRef("http://www.w3.org/1999/xhtml/vocab#"), "cc":URIRef("http://creativecommons.org/ns#")})
    if result != None and len(result) > 0:
        for row in result:
            return row[0]
    else:
        return None
# returns the relevant dcterms values (uri, dcterms:license, dcterms:title, dcterms:abstract, dcterms:description)
def getRelevantDCTERMSVocabInfo(graph):
    queryString=(
        "SELECT DISTINCT ?uri ?license ?title ?abstract ?description \n"
        "WHERE {\n"
        " ?uri a owl:Ontology .\n"
        " OPTIONAL { ?uri dcterms:license ?license }\n"   
        " OPTIONAL { ?uri dcterms:title ?title }\n" 
        " OPTIONAL { ?uri dcterms:abstract ?astract }\n"
        " OPTIONAL { ?uri dcterms:description ?description }\n"
        "} LIMIT 1"
        )
    result=graph.query(queryString, initNs={"owl": OWL, "dcterms": DCTERMS})
    if result != None and len(result) > 0:
        for row in result:
            return row
    else:
        return (None, None, None, None, None)


# returns the relevant dc values (uri, dc:title, dc:description)
def getRelevantDCVocabInfo(graph):
    queryString=(
        "SELECT DISTINCT ?uri ?title ?description\n"
        "WHERE {\n"
        " ?uri a owl:Ontology .\n"
        " OPTIONAL { ?uri dc:title ?title }\n"
        " OPTIONAL { ?uri dc:description ?description }\n"    
        "} LIMIT 1"
        )
    result=graph.query(queryString, initNs={"owl": OWL, "dc": DC})
    if result != None and len(result) > 0:
        for row in result:
            return row
    else:
        return (None, None, None)

# returns the non information resource of an ontology, representing the entity of the ontology
def getDefinedByUri(ontgraph):
    result=ontgraph.query(
        """
        SELECT DISTINCT ?defbyUri
        WHERE {
            ?s rdfs:isDefinedBy ?defbyUri .
        } LIMIT 1
        """ )
    if result != None and len(result) > 0:
        for row in result:
            return row[0]
    else:
        return None


def getOntologyReport(rootdir):
    for group in os.listdir(rootdir):
        if not os.path.isdir(rootdir + os.sep +group):
            continue
        for artifact in os.listdir(rootdir + os.sep + group):
            versionDir=rootdir + os.sep + group + os.sep + artifact
            if not os.path.isdir(versionDir):
                continue
            for version in os.listdir(versionDir):
                if not os.path.isdir(versionDir + os.sep + version):
                   continue
                dataPath=versionDir + os.sep + version
                filepath = dataPath + os.sep + artifact + ".ttl"
                jsonPath = dataPath + os.sep + artifact + ".json"
                if not os.path.isfile(filepath):
                    continue
                print("File: " + filepath)
                graph = getGraphOfVocabFile(filepath)
                vocab_uri, vocab_license = getRelevantDCTERMSVocabInfo(graph)[:2]
                if vocab_uri != None:
                    print("Uri: ",vocab_uri.n3())
                if vocab_license != None:
                    print("License: ",vocab_license.n3())
                with open(jsonPath) as json_file:
                    data = json.load(json_file)
                    if data["lastModified"] != "":
                        print("LastModified: ", data["lastModified"])
                    if data["rapperErrorLog"] != "":
                        print("RapperErrors: ", data["rapperErrorLog"])


def changeMetadata(rootdir):
    for groupdir in [dir for dir in os.listdir(rootdir) if os.path.isdir(os.path.join(rootdir, dir))]:
        for artifactDir in [dir for dir in os.listdir(os.path.join(rootdir, groupdir)) if os.path.isdir(os.path.join(rootdir, groupdir, dir))]:
            print("Generating metadata for", groupdir, artifactDir)
            versionDirs = [dir for dir in os.listdir(os.path.join(rootdir, groupdir, artifactDir)) if os.path.isdir(os.path.join(rootdir, groupdir, artifactDir, dir)) and dir != "target"]
            if versionDirs == []:
                print("Couldnt find version for", groupdir, artifactDir)
                continue
            versionDir = versionDirs[0]  
            #filepath = os.path.join(rootdir, groupdir, artifactDir, versionDir, artifactDir + "_type=parsed.ttl")
            jsonPath = os.path.join(rootdir, groupdir, artifactDir, versionDir, artifactDir + "_type=meta.json")
            if not os.path.isfile(jsonPath):
                continue
            with open(jsonPath, "r") as jsonFile:
                metadata = json.load(jsonFile)

            with open(jsonPath, "w") as jsonFile:
                metadata["semantic-version"] = "0.0.1"
                json.dump(metadata, jsonFile, indent=4, sort_keys=True)

def loadNQuadsFile(filepath):
    conGraph = ConjunctiveGraph()
    conGraph.parse(filepath)

    print(len([x for x in conGraph.store.contexts()]))

def checkShaclReport(shaclReportGraph):
    if shaclReportGraph == None:
        print("No report graph available", file=sys.stderr)
        return "Error, no graph available"
    violationRef = URIRef('http://www.w3.org/ns/shacl#Violation')
    warningRef = URIRef('http://www.w3.org/ns/shacl#Warning')
    queryString=(
        "SELECT DISTINCT ?severity \n"
        "WHERE {\n"
        " ?s sh:resultSeverity ?severity . \n"   
        "}"
        )
    result=shaclReportGraph.query(queryString, initNs={"sh":URIRef("http://www.w3.org/ns/shacl#")})

    resultValues = [row[0] for row in result if row != None]
    if violationRef in resultValues:
        return "Violation"
    elif warningRef in resultValues:
        return "Warning"
    else:
        return "OK"

graph = getGraphOfVocabFile("/home/denis/Workspace/Job/Archivo/testdir/purl.org/NET--biol--ns/2020.06.18-153052/NET--biol--ns_type=parsed.ttl")

label = getLabel(graph)

print(label)