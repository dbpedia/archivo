import requests, sys, requests, traceback, rdflib
from SPARQLWrapper import SPARQLWrapper, JSON
from io import StringIO
from urllib.error import URLError
from utils import ontoFiles, inspectVocabs, stringTools
from utils.stringTools import generateStarString
from datetime import datetime
import csv

databusRepoUrl = "https://databus.dbpedia.org/repo/sparql"

mods_uri = "https://akswnc7.informatik.uni-leipzig.de/mods/sparql"


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
        "?distribution <http://dataid.dbpedia.org/ns/cv#type> 'meta'^^<http://www.w3.org/2001/XMLSchema#string> .\n"
        "?distribution dcat:downloadURL ?file .\n"
        "?dataset dct:hasVersion ?latestVersion .\n"
        "{ SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {\n"
        "?dataset dataid:account databus:ontologies .\n"
        "?dataset dataid:artifact ?art.\n"
        "?dataset dcat:distribution ?distribution .\n"
        "?distribution <http://dataid.dbpedia.org/ns/cv#type> 'meta'^^<http://www.w3.org/2001/XMLSchema#string> .\n"
        "?dataset dct:hasVersion ?v .\n"
        "} GROUP BY ?art #HAVING (?v = MAX(?v))\n"
        "}\n"
        "}"
    )
    # query = latestMetaFileQuery.format(group, artifact)
    sparql = SPARQLWrapper(databusRepoUrl)
    sparql.setQuery(latestMetaFileQuery)
    sparql.setReturnFormat(JSON)
    try:
        results = sparql.query().convert()
    except URLError:
        return (
            False,
            databusLink,
            "",
            "There was an Error querying the databus. Probably an error on the databus side.",
        )

    try:
        metaFileUri = results["results"]["bindings"][0]["file"]["value"]
        databusVersionUri = results["results"]["bindings"][0]["versionURL"]["value"]
        req = requests.get(metaFileUri)
        return True, databusLink, databusVersionUri, req.json()
    except KeyError:
        return False, databusLink, "", "There was an error finding the metadata-file"


def getInfoForArtifact(group, artifact):
    databusLink = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
    query = "\n".join(
        (
            "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>",
            "PREFIX dct:    <http://purl.org/dc/terms/>",
            "PREFIX dcat:   <http://www.w3.org/ns/dcat#>",
            "PREFIX db:     <https://databus.dbpedia.org/>",
            "PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>",
            "PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>",
            "PREFIX dataid-cv: <http://dataid.dbpedia.org/ns/cv#>",
            "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>",
            "SELECT DISTINCT ?title ?comment ?versionURL ?version ?metafile ?minLicense ?goodLicense ?lode ?consistencyFile ?docuURL WHERE {",
            "VALUES ?art { <%s> } ." % databusLink,
            "?dataset dataid:account db:ontologies .",
            "?dataset dataid:artifact ?art .",
            "?dataset dcat:distribution ?metaDst .",
            "?metaDst dataid-cv:type 'meta'^^xsd:string .",
            "?metaDst dcat:downloadURL ?metafile .",
            "?dataset dcat:distribution ?shaclMinLicense .",
            "?dataset dcat:distribution ?consistencyReport .",
            "?consistencyReport dataid-cv:type 'pelletConsistency'^^xsd:string .",
            "?consistencyReport dataid-cv:imports 'FULL'^^xsd:string .",
            "?consistencyReport dcat:downloadURL ?consistencyFile .",
            "?shaclMinLicense dataid-cv:type 'shaclReport'^^xsd:string .",
            "?shaclMinLicense dataid-cv:validates 'minLicense'^^xsd:string .",
            "?shaclMinLicense dcat:downloadURL ?minLicense .",
            "?dataset dcat:distribution ?shaclGoodLicense .",
            "?shaclGoodLicense dataid-cv:type 'shaclReport'^^xsd:string .",
            "?shaclGoodLicense dataid-cv:validates 'goodLicense'^^xsd:string .",
            "?shaclGoodLicense dcat:downloadURL ?goodLicense .",
            "?dataset dcat:distribution ?shaclLode .",
            "?shaclLode dataid-cv:type 'shaclReport'^^xsd:string .",
            "?shaclLode dataid-cv:validates 'lodeMetadata'^^xsd:string .",
            "?shaclLode dcat:downloadURL ?lode .",
            "OPTIONAL {" "?dataset dcat:distribution ?docuDst .",
            "?docuDst dataid-cv:type 'generatedDocu'^^xsd:string .",
            "?docuDst dcat:downloadURL ?docuURL .",
            "}",
            "?dataset dataid:version ?versionURL .",
            "?dataset dct:hasVersion ?version ." "?dataset dct:title ?title .",
            "?dataset rdfs:comment ?comment .",
            "}",
        )
    )
    sparql = SPARQLWrapper(databusRepoUrl)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    version_infos = []
    try:
        results = results["results"]["bindings"]
    except KeyError:
        return False, version_infos, f"No data found for {databusLink}"
    try:
        title = sorted(results, key=lambda binding: binding["version"]["value"])[0][
            "title"
        ]["value"]
        comment = sorted(results, key=lambda binding: binding["version"]["value"])[0][
            "comment"
        ]["value"]
    except Exception as e:
        return None, None, None

    for binding in results:
        version = binding.get("version", {"value": ""})["value"]
        versionURL = binding.get("versionURL", {"value": ""})["value"]
        metafile = binding.get("metafile", {"value": ""})["value"]
        minLicenseURL = binding.get("minLicense", {"value": ""})["value"]
        goodLicenseURL = binding.get("goodLicense", {"value": ""})["value"]
        lodeShaclURL = binding.get("lode", {"value": ""})["value"]
        consistencyURL = binding["consistencyFile"]["value"]
        try:
            docuURL = binding["docuURL"]["value"]
        except KeyError:
            docuURL = None
        try:
            metadata = requests.get(metafile).json()
        except URLError:
            metadata = {}

        parsing = True if metadata["logs"]["rapper-errors"] == [] or metadata["logs"]["rapper-errors"] == "" else False
        stars = ontoFiles.measureStars(
            metadata["logs"]["rapper-errors"],
            metadata["test-results"]["License-I"],
            metadata["test-results"]["consistent"],
            metadata["test-results"]["consistent-without-imports"],
            metadata["test-results"]["License-II"],
        )
        isConsistent = lambda s: True if s == "Yes" else False
        version_infos.append(
            {
                "minLicense": {
                    "conforms": metadata["test-results"]["License-I"],
                    "url": minLicenseURL,
                },
                "goodLicense": {
                    "conforms": metadata["test-results"]["License-II"],
                    "url": goodLicenseURL,
                },
                "lode": {
                    "severity": inspectVocabs.hackyShaclInspection(lodeShaclURL),
                    "url": lodeShaclURL,
                },
                "version": {"label": version, "url": versionURL},
                "consistent": {
                    "conforms": isConsistent(metadata["test-results"]["consistent"]),
                    "url": consistencyURL,
                },
                "triples": metadata["ontology-info"]["triples"],
                "parsing": {
                    "conforms": parsing,
                    "errors": metadata["logs"]["rapper-errors"],
                },
                "semversion": metadata["ontology-info"]["semantic-version"],
                "stars": stars,
                "docuURL": docuURL,
            }
        )
    return title, comment, version_infos


def getLatestParsedOntology(group, artifact):
    databusLink = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
    query = "\n".join(
        (
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
        )
    )
    # query = latestMetaFileQuery.format(group, artifact)
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


def getDownloadURL(group, artifact, fileExt="owl", version=None):
    databusLink = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
    queryString = [
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
        "   ?distribution dataid:formatExtension '%s'^^xsd:string ." % fileExt,
        "   ?distribution dcat:downloadURL ?file .",
    ]
    if version is None:
        queryString.extend(
            [
                "   ?dataset dct:hasVersion ?latestVersion .",
                "{",
                "   SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {",
                "    ?dataset dataid:account db:ontologies .",
                "    ?dataset dataid:artifact ?art .",
                "    ?dataset dct:hasVersion ?v .",
                "}",
                "}",
            ]
        )
    else:
        queryString.append("   ?dataset dct:hasVersion '%s'^^xsd:string ." % version)
    queryString.append("}")
    sparql = SPARQLWrapper(databusRepoUrl)
    sparql.setQuery("\n".join(queryString))
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    try:
        return results["results"]["bindings"][0]["file"]["value"]
    except KeyError:
        return None
    except IndexError:
        return None


def allLatestParsedTurtleFiles():
    query = "\n".join(
        (
            "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>",
            "PREFIX dct:    <http://purl.org/dc/terms/>",
            "PREFIX dcat:   <http://www.w3.org/ns/dcat#>",
            "PREFIX db:     <https://databus.dbpedia.org/>",
            "PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>",
            "PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>",
            "PREFIX dataid-cv: <http://dataid.dbpedia.org/ns/cv#>",
            "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>",
            "SELECT DISTINCT ?art ?title ?latestVersion ?ttlFile ?owlFile ?ntFile ?metafile WHERE {",
            "?dataset dataid:account db:ontologies .",
            "?dataset dataid:artifact ?art .",
            "?dataset dct:title ?title .",
            "?dataset dcat:distribution ?turtleDst .",
            "?turtleDst dataid-cv:type 'parsed'^^xsd:string .",
            "?turtleDst dataid:formatExtension 'ttl'^^xsd:string .",
            "?turtleDst dcat:downloadURL ?ttlFile .",
            "?dataset dcat:distribution ?owlDst .",
            "?owlDst dataid-cv:type 'parsed'^^xsd:string .",
            "?owlDst dataid:formatExtension 'owl'^^xsd:string .",
            "?owlDst dcat:downloadURL ?owlFile .",
            "?dataset dcat:distribution ?ntDst .",
            "?ntDst dataid-cv:type 'parsed'^^xsd:string .",
            "?ntDst dataid:formatExtension 'nt'^^xsd:string .",
            "?ntDst dcat:downloadURL ?ntFile .",
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
        )
    )
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
            title = binding["title"]["value"]
            if databusUri not in result:
                result[databusUri] = {
                    "title": title,
                    "ttlFile": binding["ttlFile"]["value"],
                    "owlFile": binding["owlFile"]["value"],
                    "ntFile": binding["ntFile"]["value"],
                    "meta": binding["metafile"]["value"],
                    "version": binding["latestVersion"]["value"],
                }
        except KeyError:
            continue

    return result


def latestNtriples():
    query = "\n".join(
        (
            "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>",
            "PREFIX dct:    <http://purl.org/dc/terms/>",
            "PREFIX dcat:   <http://www.w3.org/ns/dcat#>",
            "PREFIX db:     <https://databus.dbpedia.org/>",
            "PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>",
            "PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>",
            "PREFIX dataid-cv: <http://dataid.dbpedia.org/ns/cv#>",
            "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>",
            "SELECT DISTINCT ?art ?latestVersion ?ntFile ?metafile WHERE {",
            "?dataset dataid:account db:ontologies .",
            "?dataset dataid:artifact ?art .",
            "?dataset dcat:distribution ?parsedDst .",
            "?parsedDst dataid-cv:type 'parsed'^^xsd:string .",
            "?parsedDst dataid:formatExtension 'nt'^^xsd:string .",
            "?parsedDst dcat:downloadURL ?ntFile .",
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
        )
    )
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
            if databusUri not in result:
                result[databusUri] = {
                    "ntFile": binding["ntFile"]["value"],
                    "meta": binding["metafile"]["value"],
                    "version": binding["latestVersion"]["value"],
                }
        except KeyError:
            continue

    return result


def getLatestInfoForAll():
    query = "\n".join(
        (
            "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>",
            "PREFIX dct:    <http://purl.org/dc/terms/>",
            "PREFIX dcat:   <http://www.w3.org/ns/dcat#>",
            "PREFIX db:     <https://databus.dbpedia.org/>",
            "PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>",
            "PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>",
            "PREFIX dataid-cv: <http://dataid.dbpedia.org/ns/cv#>",
            "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>",
            "SELECT DISTINCT ?art ?title ?comment ?latestVersion ?metafile ?minLicense ?goodLicense ?lode ?consistencyFile ?docuURL WHERE {",
            "?dataset dataid:account db:ontologies .",
            "?dataset dataid:artifact ?art .",
            "?dataset dcat:distribution ?metaDst .",
            "?metaDst dataid-cv:type 'meta'^^xsd:string .",
            "?metaDst dcat:downloadURL ?metafile .",
            "?dataset dcat:distribution ?shaclMinLicense .",
            "?dataset dcat:distribution ?consistencyReport .",
            "?consistencyReport dataid-cv:type 'pelletConsistency'^^xsd:string .",
            "?consistencyReport dataid-cv:imports 'FULL'^^xsd:string .",
            "?consistencyReport dcat:downloadURL ?consistencyFile .",
            "?shaclMinLicense dataid-cv:type 'shaclReport'^^xsd:string .",
            "?shaclMinLicense dataid-cv:validates 'minLicense'^^xsd:string .",
            "?shaclMinLicense dcat:downloadURL ?minLicense .",
            "?dataset dcat:distribution ?shaclGoodLicense .",
            "?shaclGoodLicense dataid-cv:type 'shaclReport'^^xsd:string .",
            "?shaclGoodLicense dataid-cv:validates 'goodLicense'^^xsd:string .",
            "?shaclGoodLicense dcat:downloadURL ?goodLicense .",
            "?dataset dcat:distribution ?shaclLode .",
            "?shaclLode dataid-cv:type 'shaclReport'^^xsd:string .",
            "?shaclLode dataid-cv:validates 'lodeMetadata'^^xsd:string .",
            "?shaclLode dcat:downloadURL ?lode .",
            "OPTIONAL {" "?dataset dcat:distribution ?docuDst .",
            "?docuDst dataid-cv:type 'generatedDocu'^^xsd:string .",
            "?docuDst dcat:downloadURL ?docuURL .",
            "}",
            "{",
            "SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {",
            "?dataset dataid:account db:ontologies .",
            "?dataset dataid:artifact ?art .",
            "?dataset dct:hasVersion ?v .",
            "}",
            "}",
            "?dataset dct:hasVersion ?latestVersion.",
            "?dataset dct:title ?title .",
            "?dataset rdfs:comment ?comment .",
            "}",
        )
    )
    sparql = SPARQLWrapper(databusRepoUrl)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    info_dict = {}

    try:
        results = results["results"]["bindings"]
    except KeyError:
        return False, version_infos, f"No data found for {databusLink}"

    for binding in results:

        artifactURL = binding.get("art", {"value": ""})["value"]
        info_dict[artifactURL] = {}

        info_dict[artifactURL]["title"] = binding.get("title", {"value": ""})["value"]
        info_dict[artifactURL]["version"] = binding.get("latestVersion", {"value": ""})[
            "value"
        ]
        info_dict[artifactURL]["metafile"] = binding.get("metafile", {"value": ""})[
            "value"
        ]
        info_dict[artifactURL]["minLicenseURL"] = binding.get(
            "minLicense", {"value": ""}
        )["value"]
        info_dict[artifactURL]["goodLicenseURL"] = binding.get(
            "goodLicense", {"value": ""}
        )["value"]
        lodeShaclURL = binding.get("lode", {"value": ""})["value"]
        consistencyURL = binding["consistencyFile"]["value"]
        try:
            docuURL = binding["docuURL"]["value"]
        except KeyError:
            docuURL = None

        parsing = True if metadata["logs"]["rapper-errors"] == "" else False
        stars = ontoFiles.measureStars(
            metadata["logs"]["rapper-errors"],
            metadata["test-results"]["License-I"],
            metadata["test-results"]["consistent"],
            metadata["test-results"]["consistent-without-imports"],
            metadata["test-results"]["License-II"],
        )
        isConsistent = lambda s: True if s == "Yes" else False
        version_infos.append(
            {
                "minLicense": {
                    "conforms": metadata["test-results"]["License-I"],
                    "url": minLicenseURL,
                },
                "goodLicense": {
                    "conforms": metadata["test-results"]["License-II"],
                    "url": goodLicenseURL,
                },
                "lode": {
                    "severity": inspectVocabs.hackyShaclInspection(lodeShaclURL),
                    "url": lodeShaclURL,
                },
                "version": {"label": version, "url": versionURL},
                "consistent": {
                    "conforms": isConsistent(metadata["test-results"]["consistent"]),
                    "url": consistencyURL,
                },
                "triples": metadata["ontology-info"]["triples"],
                "parsing": {
                    "conforms": parsing,
                    "errors": metadata["logs"]["rapper-errors"],
                },
                "semversion": metadata["ontology-info"]["semantic-version"],
                "stars": stars,
                "docuURL": docuURL,
            }
        )
    return title, comment, version_infos


def loadLastIndex():
    query = "\n".join(
        (
            "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>",
            "PREFIX dct:    <http://purl.org/dc/terms/>",
            "PREFIX dcat:   <http://www.w3.org/ns/dcat#>",
            "PREFIX db:     <https://databus.dbpedia.org/>",
            "PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>",
            "PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>",
            "SELECT DISTINCT ?downloadURL WHERE {",
            "VALUES ?art { <https://databus.dbpedia.org/ontologies/archivo-indices/ontologies> }",
            "?dataset dataid:artifact ?art .",
            "?dataset dct:hasVersion ?latestVersion .",
            "?dataset dcat:distribution ?dst .",
            "?dst dcat:downloadURL ?downloadURL ." "{",
            "SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {",
            "?dataset dataid:artifact ?art .",
            "?dataset dct:hasVersion ?v .",
            "}",
            "}",
            "}",
        )
    )
    sparql = SPARQLWrapper(databusRepoUrl)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    try:
        downloadURL = results["results"]["bindings"][0]["downloadURL"]["value"]
    except (KeyError, IndexError):
        return None

    csvString = requests.get(downloadURL).text
    csvIO = StringIO(csvString)

    return [tp for tp in csv.reader(csvIO, delimiter=",")]


def get_last_official_index():
    query = "\n".join(
        (
            "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>",
            "PREFIX dct:    <http://purl.org/dc/terms/>",
            "PREFIX dcat:   <http://www.w3.org/ns/dcat#>",
            "PREFIX db:     <https://databus.dbpedia.org/>",
            "PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>",
            "PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>",
            "PREFIX dataid-cv: <http://dataid.dbpedia.org/ns/cv#>",
            "SELECT DISTINCT ?downloadURL WHERE {",
            "VALUES ?art { <https://databus.dbpedia.org/ontologies/archivo-indices/ontologies> }",
            "?dataset dataid:artifact ?art .",
            "?dataset dct:hasVersion ?latestVersion .",
            "?dataset dcat:distribution ?dst .",
            "?dst dataid-cv:type 'official'^^xsd:string .",
            "?dst dcat:downloadURL ?downloadURL ." "{",
            "SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {",
            "?dataset dataid:artifact ?art .",
            "?dataset dct:hasVersion ?v .",
            "}",
            "}",
            "}",
        )
    )
    sparql = SPARQLWrapper(databusRepoUrl)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    try:
        downloadURL = results["results"]["bindings"][0]["downloadURL"]["value"]
    except (KeyError, IndexError):
        return None

    csvString = requests.get(downloadURL).text
    csvIO = StringIO(csvString)

    return [tp for tp in csv.reader(csvIO, delimiter=",")]


def get_last_dev_index():
    query = "\n".join(
        (
            "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>",
            "PREFIX dct:    <http://purl.org/dc/terms/>",
            "PREFIX dcat:   <http://www.w3.org/ns/dcat#>",
            "PREFIX db:     <https://databus.dbpedia.org/>",
            "PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>",
            "PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>",
            "PREFIX dataid-cv: <http://dataid.dbpedia.org/ns/cv#>",
            "SELECT DISTINCT ?downloadURL WHERE {",
            "VALUES ?art { <https://databus.dbpedia.org/ontologies/archivo-indices/ontologies> }",
            "?dataset dataid:artifact ?art .",
            "?dataset dct:hasVersion ?latestVersion .",
            "?dataset dcat:distribution ?dst .",
            "?dst dataid-cv:type 'dev'^^xsd:string .",
            "?dst dcat:downloadURL ?downloadURL ." "{",
            "SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {",
            "?dataset dataid:artifact ?art .",
            "?dataset dct:hasVersion ?v .",
            "}",
            "}",
            "}",
        )
    )
    sparql = SPARQLWrapper(databusRepoUrl)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    try:
        downloadURL = results["results"]["bindings"][0]["downloadURL"]["value"]
    except (KeyError, IndexError):
        return None

    csvString = requests.get(downloadURL).text
    csvIO = StringIO(csvString)

    return [tp for tp in csv.reader(csvIO, delimiter=",")]

def get_SPOs():
    query = "\n".join(
        (
            "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>",
            "PREFIX dct:    <http://purl.org/dc/terms/>",
            "PREFIX dcat:   <http://www.w3.org/ns/dcat#>",
            "PREFIX prov: <http://www.w3.org/ns/prov#>"
            "SELECT DISTINCT ?used ?generated {",
            "SERVICE <https://databus.dbpedia.org/repo/sparql> {",
            "?s dct:publisher <https://yum-yab.github.io/webid.ttl#onto> .",
            "?s dcat:distribution/dataid:file ?used .",
            "}",
            "?mod prov:generated ?generated .",
            "?mod prov:used ?used .",
            "}",
        )
    )
    sparql = SPARQLWrapper(mods_uri)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    print("Query got called!")
    results = sparql.query().convert()

    try:
        results = results["results"]["bindings"]
    except KeyError:
        return None

    for binding in results:
        spo_csv_uri = binding["generated"]["value"]
        print(binding["used"]["value"])
        try:
            csv_doc = requests.get(spo_csv_uri).text
        except Exception:
            continue
        csv_IO = StringIO(csv_doc)
        distinct_spo_uris = []
        for tp in csv.reader(csv_IO, delimiter=";"):
            try:
                uri = tp[0]
            except Exception:
                continue
            if stringTools.get_uri_from_index(uri, distinct_spo_uris) == None:
                distinct_spo_uris.append(uri)
        yield distinct_spo_uris


if __name__ == "__main__":
    getDownloadURL("datashapes.org", "dash", fileExt="ttl", version="2020.07.16-115603")
