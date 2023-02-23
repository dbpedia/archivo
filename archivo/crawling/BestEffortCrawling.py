from logging import Logger
from typing import List, Dict, Optional
from dataclasses import dataclass

import requests

from archivo.models import ContentNegotiation
from archivo.models.CrawlingResponse import CrawlingResponse
from archivo.utils import parsing


class UnavailableException(Exception):

    def __init__(self, response: requests.Response):
        self.message = f"Ontology Unavailable at {response.url}: Status {response.status_code}"
        super().__init__(self.message)


def download_rdf_string(uri: str, acc_header: str, encoding="utf-8", timeout_seconds: int = 30) -> requests.Response:
    headers = {"Accept": acc_header}
    response = requests.get(uri, headers=headers, timeout=timeout_seconds, allow_redirects=True)

    # set encoding to UTF-8
    if encoding is not None:
        response.encoding = encoding

    if response.status_code < 400:
        return response
    else:
        raise UnavailableException(response)


def handle_parsing(uri: str,
                   response: requests.Response,
                   rdf_type: ContentNegotiation.RDF_Type,
                   user_output: List[Dict] = None) -> CrawlingResponse:
    triples, errors = parsing.get_triples_from_rdf_string(
        response.text,
        uri,
        input_type=rdf_type
    )

    # append user output notification
    header_string = ContentNegotiation.get_accept_header(rdf_type)
    message = "Triples Parsed: {} \nErrors during parsing: \n{}".format(
        str(triples), "\n".join(errors[:20]))
    status = triples > 0
    user_output.append(
        {
            "status": status,
            "step": f"Parsing with header {header_string}",
            "message": message,
        }
    )

    return CrawlingResponse(uri, response, response.text, rdf_type, triples)


def determine_best_content_type(uri: str, user_output: List[Dict]) -> Optional[CrawlingResponse]:
    """Tests multiple RDF content types for the most yielding triples"""

    if user_output is None:
        user_output = []

    results: List[CrawlingResponse] = []

    for rdf_type in ContentNegotiation.RDF_Type:
        header = ContentNegotiation.get_accept_header(rdf_type)
        try:
            response = download_rdf_string(uri, acc_header=header)
            crawling_result = handle_parsing(uri, response, rdf_type, user_output=user_output)
        except Exception as e:
            user_output.append(
                {
                    "status": False,
                    "step": f"Loading and parsing from {uri} with header {header}",
                    "message": f"{str(e)}",
                }
            )
        else:
            results.append(crawling_result)
            # break if the ontology is really huge
            if crawling_result.triple_number > 200000:
                break

    # find best result
    parseable_results = [r for r in results if r.triple_number > 0]

    if len(parseable_results) == 0:
        return None
    else:
        results.sort(key=lambda x: x.triples, reverse=True)
        return results[0]

