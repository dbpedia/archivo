from typing import List, Optional
import requests
from models import content_negotiation
from models.crawling_response import CrawlingResponse
from utils import parsing

from models.user_interaction import LogLevel, ProcessStepLog


class UnavailableException(Exception):
    def __init__(self, response: requests.Response):
        self.message = (
            f"Ontology Unavailable at {response.url}: Status {response.status_code}"
        )
        super().__init__(self.message)


def download_rdf_string(
    uri: str, acc_header: str, encoding="utf-8", timeout_seconds: int = 30
) -> requests.Response:
    headers = {"Accept": acc_header}
    response = requests.get(
        uri, headers=headers, timeout=timeout_seconds, allow_redirects=True
    )

    # set encoding to UTF-8
    if encoding is not None:
        response.encoding = encoding

    if response.status_code < 400:
        return response
    else:
        raise UnavailableException(response)


def handle_parsing(
    uri: str,
    response: requests.Response,
    rdf_type: content_negotiation.RDF_Type,
    user_output: Optional[List[ProcessStepLog]] = None,
) -> CrawlingResponse:
    """Parses the rdf out of a given response and the supposed RDF serialisation type"""

    if not user_output:
        user_output = []

    parsing_info = parsing.get_triples_from_rdf_string(
        response.text, uri, input_type=rdf_type
    )

    # append user output notification
    header_string = content_negotiation.get_accept_header(rdf_type)
    error_message = "\n".join(parsing_info.errors[:20])
    if len(parsing_info.errors) > 20:
        error_message += f"\nand {len(parsing_info.errors) - 20} more lines"

    message = f"Triples Parsed: {str(parsing_info.triple_number)} \nErrors during parsing: \n{error_message}"
    status = LogLevel.INFO if parsing_info.triple_number > 0 else LogLevel.WARNING
    user_output.append(
        ProcessStepLog(
            status=status,
            stepname=f"Parsing with header {header_string}",
            message=message,
        )
    )

    return CrawlingResponse(uri, response, rdf_type, parsing_info)


def determine_best_content_type(
    uri: str, user_output: List[ProcessStepLog]
) -> Optional[CrawlingResponse]:
    """Tests multiple RDF content types for the most yielding triples"""

    if user_output is None:
        user_output = []

    results: List[CrawlingResponse] = []

    for rdf_type in content_negotiation.RDF_Type:
        header = content_negotiation.get_accept_header(rdf_type)
        try:
            response = download_rdf_string(uri, acc_header=header)
            crawling_result = handle_parsing(
                uri, response, rdf_type, user_output=user_output
            )
        except Exception as e:
            user_output.append(
                ProcessStepLog(
                    status=LogLevel.ERROR,
                    stepname=f"Loading and parsing from {uri} with header {header}",
                    message=f"{str(e)}",
                )
            )
        else:
            results.append(crawling_result)
            # break if the ontology is really huge
            if crawling_result.parsing_info.triple_number > 200000:
                user_output.append(
                    ProcessStepLog(
                        status=LogLevel.INFO,
                        stepname=f"Loading and parsing from {uri} with header {header}",
                        message=f"Parsed {crawling_result.parsing_info.triple_number} triples with {len(crawling_result.parsing_info.errors)} Errors and {len(crawling_result.parsing_info.warnings)} Warnings. Since this is a huge ontology other formats wont be tested.",
                    )
                )
                break
            else:
                user_output.append(
                    ProcessStepLog(
                        status=LogLevel.INFO,
                        stepname=f"Loading and parsing from {uri} with header {header}",
                        message=f"Parsed {crawling_result.parsing_info.triple_number} triples with {len(crawling_result.parsing_info.errors)} Errors and {len(crawling_result.parsing_info.warnings)} Warnings.",
                    )
                )

    # find best result
    parseable_results = [r for r in results if r.parsing_info.triple_number > 0]

    if len(parseable_results) == 0:
        return None
    else:
        results.sort(key=lambda x: x.triple_number, reverse=True)
        return results[0]
