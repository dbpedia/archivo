from typing import Dict, Callable, Iterable

import requests

from querying import query_databus

# url to get all vocabs and their resource
lovOntologiesURL = "https://lov.linkeddata.es/dataset/lov/api/v2/vocabulary/list"

# prefix.cc complete urls
prefixccURLs = "http://prefix.cc/context"


def get_lov_urls() -> Iterable[str]:
    req = requests.get(lovOntologiesURL)
    json_data = req.json()
    return [dataObj["uri"] for dataObj in json_data]


def get_prefix_cc_urls() -> Iterable[str]:
    req = requests.get(prefixccURLs)
    json_data = req.json()
    prefixOntoDict = json_data["@context"]
    return [prefixOntoDict[prefix] for prefix in prefixOntoDict]


def get_bioregistry_urls() -> Iterable[str]:
    url = "https://raw.githubusercontent.com/biopragmatics/bioregistry/main/exports/registry/registry.json"
    resp_json = requests.get(url).json()

    relevant_keys = ["download_rdf", "download_owl"]

    for identifier, info_dict in resp_json.items():

        url = None
        for key in relevant_keys:

            url = info_dict[key]
            if url:
                break

        if url:
            yield url


SOURCES_GETFUN_MAPPING: Dict[str, Callable] = {
    "LOV": get_lov_urls,
    "prefix.cc": get_prefix_cc_urls,
    # "VOID mod": query_databus.get_distinct_void_uris,
    "bioregistry.io": get_bioregistry_urls,
}
