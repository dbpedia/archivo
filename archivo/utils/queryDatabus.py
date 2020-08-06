import requests
from SPARQLWrapper import SPARQLWrapper, JSON
import traceback
import sys
import rdflib
from io import StringIO
from urllib.error import URLError


databusRepoUrl = "https://databus.dbpedia.org/repo/sparql"


def getLatestMetaFile(group, artifact):
    databusLink = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
    latestMetaFileQuery = (
        "PREFIX dcat: <http://www.w3.org/ns/dcat#>\n"
        "PREFIX dct: <http://purl.org/dc/terms/>\n"
        "PREFIX dataid-cv: <http://dataid.dbpedia.org/ns/cv#>\n"
        "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>\n"
        "PREFIX databus: <https://databus.dbpedia.org/>\n"
        "SELECT DISTINCT ?versionURL ?file WHERE\n"
        "{\n" 
            "?dataset dataid:account databus:ontologies .\n"
            f"?dataset dataid:artifact <{databusLink}>.\n"
            "?dataset dcat:distribution ?distribution .\n"
            "?dataset dataid:version ?versionURL .\n"
            "?distribution <http://dataid.dbpedia.org/ns/cv#type> \'meta\'^^<http://www.w3.org/2001/XMLSchema#string> .\n" 
            "?distribution dcat:downloadURL ?file .\n"
            "?dataset dct:hasVersion ?latestVersion .\n"
            "{ SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {\n"
                "?dataset dataid:account databus:ontologies .\n"
                "?dataset dataid:artifact ?art.\n"
                "?dataset dcat:distribution ?distribution .\n"
                "?distribution <http://dataid.dbpedia.org/ns/cv#type> \'meta\'^^<http://www.w3.org/2001/XMLSchema#string> .\n" 
                "?dataset dct:hasVersion ?v .\n"
                "} GROUP BY ?art #HAVING (?v = MAX(?v))\n"
            "}\n"
        "}"
    )
    #query = latestMetaFileQuery.format(group, artifact)
    sparql = SPARQLWrapper(databusRepoUrl)
    sparql.setQuery(latestMetaFileQuery)
    sparql.setReturnFormat(JSON)
    try:
        results = sparql.query().convert()
    except URLError:
        return False, databusLink, "", "There was an Error querying the databus. Probably an error on the databus side."

    try:
        metaFileUri = results["results"]["bindings"][0]["file"]["value"]
        databusVersionUri = results["results"]["bindings"][0]["versionURL"]["value"]
        req = requests.get(metaFileUri)
        return True, databusLink, databusVersionUri, req.json()
    except KeyError:
        return False, databusLink, "", "There was an error finding the metadata-file"


def getLatestParsedOntology(group, artifact):
    databusLink = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
    query = "\n".join((
        "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>",
        "PREFIX dct:    <http://purl.org/dc/terms/>",
        "PREFIX dcat:   <http://www.w3.org/ns/dcat#>",
        "PREFIX db:     <https://databus.dbpedia.org/>",
        "PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>",
        "PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>",
        "PREFIX dataid-cv: <http://dataid.dbpedia.org/ns/cv#>",
        "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>",
        "",
        "SELECT DISTINCT ?file WHERE {",
        "VALUES ?art { <%s> } ." % databusLink,
        "   ?dataset dataid:account db:ontologies .",
        "   ?dataset dataid:artifact ?art .",
        "   ?dataset dcat:distribution ?distribution .",
        "   ?distribution dataid-cv:type 'parsed'^^xsd:string .",
        "   ?distribution dataid:formatExtension 'ttl'^^xsd:string .",
        "   ?distribution dcat:downloadURL ?file .",
        "   ?dataset dct:hasVersion ?latestVersion .",
        "{",
        "   SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {",
        "    ?dataset dataid:account db:ontologies .",
        "    ?dataset dataid:artifact ?art .",
        "    ?dataset dct:hasVersion ?v .",
            "}",
            "}",
        "}",
    ))
    #query = latestMetaFileQuery.format(group, artifact)
    sparql = SPARQLWrapper(databusRepoUrl)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    try:
        parsedOntoUri = results["results"]["bindings"][0]["file"]["value"]
        req = requests.get(parsedOntoUri)
        graph = rdflib.Graph()
        graph.parse(StringIO(req.text), format="turtle")
        return graph
    except KeyError:
        traceback.print_exc(file=sys.stdout)
    except Exception:
        traceback.print_exc(file=sys.stdout)


def allLatestParsedTurtleFiles():
    query = "\n".join((
        "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>",
        "PREFIX dct:    <http://purl.org/dc/terms/>",
        "PREFIX dcat:   <http://www.w3.org/ns/dcat#>",
        "PREFIX db:     <https://databus.dbpedia.org/>",
        "PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>",    
        "PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>",
        "PREFIX dataid-cv: <http://dataid.dbpedia.org/ns/cv#>",
        "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>",

        "SELECT DISTINCT ?art ?latestVersion ?parsedFile ?metafile WHERE {",
            "?dataset dataid:account db:ontologies .", 
            "?dataset dataid:artifact ?art .",
            "?dataset dcat:distribution ?parsedDst .",
            "?parsedDst dataid-cv:type 'parsed'^^xsd:string .",     
            "?parsedDst dataid:formatExtension 'ttl'^^xsd:string .", 
            "?parsedDst dcat:downloadURL ?parsedFile .",
        
            "?dataset dcat:distribution ?metaDst .",
            "?metaDst dataid-cv:type 'meta'^^xsd:string .",
            "?metaDst dcat:downloadURL ?metafile .",

            "?dataset dct:hasVersion ?latestVersion .",
                "{",
                "SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {",
                    "?dataset dataid:account db:ontologies .",
                    "?dataset dataid:artifact ?art .",
                    "?dataset dct:hasVersion ?v .",
                    "}",
                "}",
        "}",
    ))
    sparql = SPARQLWrapper(databusRepoUrl)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    try:
        ontdata = sparql.query().convert()
    except URLError:
        return None
    result = {}
    for binding in ontdata["results"]["bindings"]:
        try:
            databusUri = binding["art"]["value"]
            if not databusUri in result:
                result[databusUri] = {"parsedFile":binding["parsedFile"]["value"], "meta":binding["metafile"]["value"], "version":binding["latestVersion"]["value"]}
        except KeyError:
            continue

    return result

def latestOriginalOntlogies():
    query = "\n".join((
        "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>",
        "PREFIX dct:    <http://purl.org/dc/terms/>",
        "PREFIX dcat:   <http://www.w3.org/ns/dcat#>",
        "PREFIX db:     <https://databus.dbpedia.org/>",
        "PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>",    
        "PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>",
        "PREFIX dataid-cv: <http://dataid.dbpedia.org/ns/cv#>",
        "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>",

        "SELECT DISTINCT ?art ?latestVersion ?origFile ?metafile WHERE {",
            "?dataset dataid:account db:ontologies .", 
            "?dataset dataid:artifact ?art .",
            "?dataset dcat:distribution ?parsedDst .",
            "?parsedDst dataid-cv:type 'orig'^^xsd:string .",      
            "?parsedDst dcat:downloadURL ?origFile .",
        
            "?dataset dcat:distribution ?metaDst .",
            "?metaDst dataid-cv:type 'meta'^^xsd:string .",
            "?metaDst dcat:downloadURL ?metafile .",

            "?dataset dct:hasVersion ?latestVersion .",
                "{",
                "SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {",
                    "?dataset dataid:account db:ontologies .",
                    "?dataset dataid:artifact ?art .",
                    "?dataset dct:hasVersion ?v .",
                    "}",
                "}",
        "}",
    ))
    sparql = SPARQLWrapper(databusRepoUrl)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    try:
        ontdata = sparql.query().convert()
    except URLError:
        return None
    result = {}
    for binding in ontdata["results"]["bindings"]:
        try:
            databusUri = binding["art"]["value"]
            if not databusUri in result:
                result[databusUri] = {"origFile":binding["origFile"]["value"], "meta":binding["metafile"]["value"], "version":binding["latestVersion"]["value"]}
        except KeyError:
            continue

    return result


if __name__ == "__main__":
    print(latestOriginalOntlogies())