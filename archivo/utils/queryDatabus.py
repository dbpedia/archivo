import requests
from SPARQLWrapper import SPARQLWrapper, JSON


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

#print(getLatestMetaFile("w3id.org", "gom"))