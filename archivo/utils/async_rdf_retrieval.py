import asyncio
from typing import Tuple, List

import aiohttp
from utils import ontoFiles
from utils.stringTools import rdfHeadersMapping
from utils import inspectVocabs as IV


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
) -> (str, str):

    try:
        resp = await session.request(
            "GET", url=uri, headers={"Accept": acc_header}, **kwargs
        )
        if resp.status >= 400:
            error_list.append((uri, f"Status {resp.status}"))
            return None
        data = await resp.text(encoding="UTF-8")
        (nt_graph, _, rapper_errors, _,) = ontoFiles.parse_rdf_from_string(
            data,
            uri,
            input_type=rdfHeadersMapping[acc_header],
            output_type="ntriples",
        )
        if not allow_rapper_errors and rapper_errors != []:
            error_list.append((uri, "Parsing error: " + ";".join(rapper_errors)))

            return None
        else:
            return nt_graph
    except Exception as e:
        error_list.append((uri, str(e)))
        return None


async def collect_linked_content(
    nir, graph, pref_header, concurrent_requests: int, logger=None
) -> Tuple[List[str], List[Tuple[str, str]]]:

    defined_uris = IV.get_defined_uris(nir, graph)

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

            nt_list = await asyncio.gather(*tasks)
            succ_graphs = list(filter(None, nt_list))
            if logger is not None:
                logger.debug(f"Retrieved {len(succ_graphs)} out of {len(chunk)} URIs")
            all_nt_strings = all_nt_strings + succ_graphs

    return all_nt_strings, retrieval_errors


def gather_linked_content(
    nir, graph, pref_header, concurrent_requests: int, logger=None
) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Returns a tuple (list_of_nt_strings, retrieval_error_tuples)"""
    return asyncio.run(
        collect_linked_content(
            nir, graph, pref_header, concurrent_requests, logger=logger
        )
    )
