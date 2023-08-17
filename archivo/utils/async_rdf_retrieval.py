import asyncio
from typing import Tuple, List, Optional

import aiohttp

from archivo.models.content_negotiation import RDF_Type
from archivo.utils import graph_handling

from archivo.models import content_negotiation
from archivo.utils import parsing
from archivo.utils.parsing import RapperParsingResult, RapperParsingInfo
import itertools


def chunk_list(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


async def fetch_one_nt_resource(
    session: aiohttp.ClientSession,
    uri: str,
    acc_header: str,
    error_list: List[Tuple[str, str]],
    allow_rapper_errors=False,
    **kwargs,
) -> Optional[RapperParsingResult]:

    try:
        resp = await session.request(
            "GET", url=uri, headers={"Accept": acc_header}, **kwargs
        )
        if resp.status >= 400:
            error_list.append((uri, f"Status {resp.status}"))
            return None
        data = await resp.text(encoding="UTF-8")

        parsing_result = parsing.parse_rdf_from_string(
            data,
            uri,
            input_type=content_negotiation.get_rdf_type(acc_header),
            output_type=content_negotiation.RDF_Type.N_TRIPLES,
        )
        if not allow_rapper_errors and parsing_result.parsing_info.errors != []:
            error_list.append(
                (uri, "Parsing error: " + ";".join(parsing_result.parsing_info.errors))
            )

            return None
        else:
            return parsing_result
    except Exception as e:
        error_list.append((uri, str(e)))
        return None


async def collect_linked_content(
    nir, graph, pref_header, concurrent_requests: int, logger=None
) -> Tuple[List[RapperParsingResult], List[Tuple[str, str]]]:

    defined_uris = graph_handling.get_defined_uris(nir, graph)

    all_nt_strings = []

    retrieval_errors = []

    if logger is not None:
        logger.debug(f"Found {len(defined_uris)} possible candidates")

    for chunk in chunk_list(defined_uris, concurrent_requests):
        tasks = []
        async with aiohttp.ClientSession() as session:
            for uri in chunk:
                tasks.append(
                    fetch_one_nt_resource(
                        session=session,
                        uri=uri,
                        acc_header=pref_header,
                        error_list=retrieval_errors,
                    )
                )

            parsing_result_list = await asyncio.gather(*tasks)
            succ_graphs = list(filter(None, parsing_result_list))
            if logger is not None:
                logger.debug(f"Retrieved {len(succ_graphs)} out of {len(chunk)} URIs")
            all_nt_strings = all_nt_strings + succ_graphs

    return all_nt_strings, retrieval_errors


def gather_linked_content(
    nir, graph, pref_header, concurrent_requests: int, logger=None
) -> Tuple[List[RapperParsingResult], List[Tuple[str, str]]]:
    """Returns a tuple (list_of_nt_strings, retrieval_error_tuples)"""
    return asyncio.run(
        collect_linked_content(
            nir, graph, pref_header, concurrent_requests, logger=logger
        )
    )


def join_ntriples_results(results: List[RapperParsingResult]) -> RapperParsingResult:
    """Joins multiple ntriples results to one big, deduplicated result"""

    triple_set = set()

    # deduplicate ntriples
    for parsing_result in results:
        for triple in parsing_result.parsed_rdf.split("\n"):
            if triple.strip() != "":
                triple_set.add(triple)

    triple_number = len(triple_set)

    errors = []
    warnings = []

    for pr in results:
        errors += pr.parsing_info.errors
        warnings += pr.parsing_info.warnings

    pi = RapperParsingInfo(triple_number, warnings, errors)

    return RapperParsingResult("\n".join(triple_set), RDF_Type.N_TRIPLES, pi)
