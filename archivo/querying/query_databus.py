from logging import Logger

import requests
from typing import Callable, Optional, Dict, List, Generator, Iterator

from SPARQLWrapper import SPARQLWrapper, JSON
from io import StringIO

from models.databus_responses import (
    ArtifactInformation,
    VersionInformation,
    BooleanTestResult,
    SeverityTestResult,
    ContentTestResult,
    Link,
)
from utils import string_tools, archivo_config
from querying import graph_handling, query_templates
from datetime import datetime, timedelta
import csv

__DATABUS_REPO_URL = f"{archivo_config.DATABUS_BASE}/sparql"

__MOD_ENDPOINT = "https://mods.tools.dbpedia.org/sparql"


def get_value_of_key_fun(key: str) -> Callable:
    return lambda binding: binding[key]["value"]


def get_info_for_artifact(group: str, artifact: str) -> ArtifactInformation:
    """Returns the info for a given group and artifact"""

    artifact_url = f"{archivo_config.DATABUS_BASE}/{archivo_config.DATABUS_USER}/{group}/{artifact}"

    query = query_templates.artifact_info_query.safe_substitute(ARTIFACT=artifact_url)
    sparql = SPARQLWrapper(__DATABUS_REPO_URL)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    version_infos = []

    def get_version_val(b) -> str:
        return b["version"]["value"]

    results = results["results"]["bindings"]
    title = sorted(results, key=get_version_val, reverse=True)[0]["title"]["value"]
    comment = sorted(results, key=get_version_val, reverse=True)[0]["abstract"]["value"]

    for binding in results:
        version = binding.get("version", {"value": ""})["value"]
        versionURL = binding.get("dataset", {"value": ""})["value"]
        metafile = binding.get("metafile", {"value": ""})["value"]
        minLicenseURL = binding.get("shaclMinLicense", {"value": ""})["value"]
        goodLicenseURL = binding.get("shaclGoodLicense", {"value": ""})["value"]
        lodeShaclURL = binding.get("shaclLode", {"value": ""})["value"]
        consistencyURL = binding["consistencyReport"]["value"]

        metadata = requests.get(metafile).json()

        try:
            archivo_test_url = binding["shaclArchivo"]["value"]
            archivo_test_severity = graph_handling.hacky_shacl_report_severity(
                archivo_test_url
            )
        except KeyError:
            archivo_test_url = None
            archivo_test_severity = None

        parsing = (
            True
            if metadata["logs"]["rapper-errors"] == []
            or metadata["logs"]["rapper-errors"] == ""
            else False
        )
        # select docu url, pref pylode doc
        docuURL = binding.get("pylodeURL", {}).get("value", None)
        if docuURL is None:
            docuURL = binding.get("docuURL", {}).get("value", None)

        version_infos.append(
            VersionInformation(
                min_license=BooleanTestResult(
                    metadata["test-results"]["License-I"], minLicenseURL
                ),
                good_license=BooleanTestResult(
                    metadata["test-results"]["License-II"], goodLicenseURL
                ),
                lode_conformity=SeverityTestResult(
                    graph_handling.hacky_shacl_report_severity(lodeShaclURL),
                    lodeShaclURL,
                ),
                archivo_conformity=SeverityTestResult(
                    archivo_test_severity, archivo_test_url
                ),
                consistency=SeverityTestResult(
                    string_tools.get_consistency_status(
                        metadata["test-results"]["consistent"]
                    ),
                    consistencyURL,
                ),
                parsing=ContentTestResult(
                    parsing, "\n".join(metadata["logs"]["rapper-errors"])
                ),
                version=Link(version, versionURL),
                triples=metadata["ontology-info"]["triples"],
                semantic_version=metadata["ontology-info"]["semantic-version"],
                stars=string_tools.stars_from_meta_dict(metadata),
                documentation_url=docuURL,
            )
        )

    return ArtifactInformation(
        title=title, description=comment, version_infos=version_infos
    )


def find_previous_version(versions, target_file, target_version):
    target_datetime = datetime.strptime(target_version, '%Y.%m.%d-%H%M%S')
    previous_version = None
    
    for version_dict in versions:
        if target_file in version_dict['file']['value']:
            version_str = version_dict['version']['value']
            version_datetime = datetime.strptime(version_str, '%Y.%m.%d-%H%M%S')
            if version_datetime < target_datetime:
                if previous_version is None or version_datetime > datetime.strptime(previous_version, '%Y.%m.%d-%H%M%S'):
                    previous_version = version_str

    return previous_version


def find_closest_version(versions, target_file, target_version):
    target_datetime = datetime.strptime(target_version, '%Y.%m.%d-%H%M%S')
    closest_version = None
    min_diff = float('inf')
    
    for version_dict in versions:
        if target_file in version_dict['file']['value']:
            version_str = version_dict['version']['value']
            version_datetime = datetime.strptime(version_str, '%Y.%m.%d-%H%M%S')
            diff = abs((version_datetime - target_datetime).total_seconds())
            
            if diff < min_diff:
                min_diff = diff
                closest_version = version_str

    return closest_version


def get_download_url(
    group: str, artifact: str, file_extension: str = "owl", version: str = None, versionMatching: str = 'exact'
) -> Optional[str]:

    artifact_id = f"{archivo_config.DATABUS_BASE}/{archivo_config.DATABUS_USER}/{group}/{artifact}"
    queryString = [
        query_templates.general_purpose_prefixes,
        "",
        "SELECT DISTINCT ?file WHERE {",
        "VALUES ?art { <%s> } ." % artifact_id,
        "   ?dataset databus:artifact ?art .",
        "   ?dataset dcat:distribution ?distribution .",
        "   ?distribution dataid-cv:type 'parsed' .",
        "   ?distribution databus:formatExtension '%s' ." % file_extension,
        "   ?distribution databus:file ?file .",
    ]
    if version is None:
        queryString.extend(
            [
                "   ?dataset dct:hasVersion ?latestVersion .",
                "{",
                "   SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {",
                "    ?dataset databus:artifact ?art .",
                "    ?dataset dct:hasVersion ?v .",
                "}",
                "}",
            ]
        )
    else:
        if versionMatching == 'exact':
            queryString.extend(["   ?dataset dct:hasVersion '%s'." % version])
        else:
            # Fetching all the version because timestamp comparison 
            # with SPARQL was not working as expected
            queryAvailableVersions = [
                query_templates.general_purpose_prefixes,
                "",
                "SELECT DISTINCT ?file ?version WHERE {",
                "VALUES ?art { <%s> } ." % artifact_id,
                "   ?dataset databus:artifact ?art .",
                "   ?dataset dcat:distribution ?distribution .",
                "   ?distribution dataid-cv:type 'parsed' .",
                "   ?distribution databus:formatExtension '%s' ." % file_extension,
                "   ?distribution databus:file ?file .",
                "   ?dataset dct:hasVersion ?version .",
                "}"
            ]
            sparql_versions = SPARQLWrapper(__DATABUS_REPO_URL)
            sparql_versions.setQuery("\n".join(queryAvailableVersions))
            sparql_versions.setReturnFormat(JSON)
            #print("\n".join(queryAvailableVersions))
            results = sparql_versions.query().convert()
            

            versions = results["results"]["bindings"]

            if versionMatching == 'before':
                previous_version = find_previous_version(versions, group, version)
                queryString.extend(["   ?dataset dct:hasVersion '%s'." % previous_version])

            if versionMatching == 'beforeOrClosest':
                previous_version = find_previous_version(versions, group, version)
                # In case there is no version before, fall back to the the closest version
                if previous_version:
                    queryString.extend(["   ?dataset dct:hasVersion '%s'." % previous_version])
                else:
                    versionMatching = 'closest'

            if versionMatching == 'closest':
                closest_version = find_closest_version(versions, group, version)
                queryString.extend(["   ?dataset dct:hasVersion '%s'." % closest_version])

    queryString.append("}")

    print("\n".join(queryString))
    sparql = SPARQLWrapper(__DATABUS_REPO_URL)
    sparql.setQuery("\n".join(queryString))
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    try:
        return results["results"]["bindings"][0]["file"]["value"]
    except KeyError:
        return None
    except IndexError:
        return None


def nir_to_latest_version_files() -> Dict[str, Dict[str, str]]:
    """Returns a dict with the NIR being the key and value being another dict with entries:
    ntFile -> URL of the parsed ntriples of the ontology
    meta -> URL of the metadata json file
    version -> databus version string (YYYY.MM.DD-HHMMSS)"""

    sparql = SPARQLWrapper(__DATABUS_REPO_URL)
    sparql.setQuery(query_templates.nir_to_lates_versions_query)
    sparql.setReturnFormat(JSON)

    query_response = sparql.query().convert()
    result = {}
    for binding in query_response["results"]["bindings"]:
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


def get_last_official_index() -> Optional[List[List[str]]]:
    query = query_templates.get_last_index_template.safe_substitute(
        INDEXTYPE="official"
    )
    sparql = SPARQLWrapper(__DATABUS_REPO_URL)
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


def get_last_dev_index() -> Optional[List[List[str]]]:
    query = query_templates.get_last_index_template.safe_substitute(INDEXTYPE="dev")
    sparql = SPARQLWrapper(__DATABUS_REPO_URL)
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


def get_identifier_on_databus(
    date: datetime = None, logger: Logger = None
) -> Iterator[str]:
    # returns spos in a generator which are not older than two weeks
    today = datetime.today()
    if date is None:
        last_week = today - timedelta(days=21)
        deadline_str = last_week.strftime("%Y.%m.%d-%H%M%S")
    else:
        deadline_str = date.strftime("%Y.%m.%d-%H%M%S")

    query = query_templates.get_spo_file_template.safe_substitute(
        DATE=deadline_str, DATABUSEP=__DATABUS_REPO_URL
    )
    sparql = SPARQLWrapper(__MOD_ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    try:
        results = results["results"]["bindings"]
    except KeyError:
        yield

    if len(results) == 0 and logger is not None:
        logger.error(f"Couldn't find any new SPOs since {deadline_str}")

    for binding in results:
        spo_csv_uri = binding["generated"]["value"]
        try:
            csv_doc = requests.get(spo_csv_uri).text
        except Exception:
            continue
        csv_IO = StringIO(csv_doc)
        distinct_spo_uris: List[str] = []
        for tp in csv.reader(csv_IO, delimiter=";"):
            try:
                uri = tp[0]
            except Exception:
                continue
            if string_tools.get_uri_from_index(uri, distinct_spo_uris) is None:
                distinct_spo_uris.append(uri)
        yield distinct_spo_uris


# returns a distinct list of VOID classes and properties
def get_distinct_void_uris() -> Iterator[str]:

    sparql = SPARQLWrapper(__MOD_ENDPOINT)
    sparql.setQuery(query_templates.void_uris_query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    if "results" not in results:
        yield
    for binding in results:
        yield binding["URI"]["value"]


if __name__ == "__main__":
    print(
        get_download_url("datashapes.org", "dash", file_extension="ttl", version=None)
    )
