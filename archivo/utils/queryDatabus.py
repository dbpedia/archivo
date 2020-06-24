import requests
from SPARQLWrapper import SPARQLWrapper, JSON
import traceback
import sys
import rdflib
from io import StringIO


databusRepoUrl = "https://databus.dbpedia.org/repo/sparql"


def getLatestMetaFile(group, artifact):
    databusLink = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
    latestMetaFileQuery = (
        "PREFIX dcat: <http://www.w3.org/ns/dcat#>\n"
        "PREFIX dct: <http://purl.org/dc/terms/>\n"
        "PREFIX dataid-cv: <http://dataid.dbpedia.org/ns/cv#>\n"
        "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>\n"
        "PREFIX databus: <https://databus.dbpedia.org/>\n"
        "SELECT DISTINCT ?file WHERE\n"
        "{\n" 
            "?dataset dataid:account databus:ontologies .\n"
            f"?dataset dataid:artifact <{databusLink}>.\n"
            "?dataset dcat:distribution ?distribution .\n"
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
    results = sparql.query().convert()
    try:
        metaFileUri = results["results"]["bindings"][0]["file"]["value"]
        req = requests.get(metaFileUri)
        return True, databusLink, req.json()
    except KeyError:
        return False, databusLink, ""


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