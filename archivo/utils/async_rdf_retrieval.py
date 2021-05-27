import asyncio
import aiohttp
from utils import ontoFiles
from utils.stringTools import rdfHeadersMapping
from utils import inspectVocabs as IV
import requests


def chunk_list(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


async def fetch_one_nt_resource(
    session: aiohttp.ClientSession,
    uri: str,
    acc_header: str,
    error_list: list,
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


async def collect_linked_content(nir, graph, pref_header, logger=None):

    defined_uris = IV.get_defined_URIs(nir, graph)

    # defined_uris = [
    #     "http://dbpedia.org/ontology/zipCode",
    #     "http://dbpedia.org/ontology/youthClub",
    #     "http://dbpedia.org/ontology/year",
    #     "http://dbpedia.org/ontology/Wrestler",
    # ]
    all_nt_strings = []

    retrieval_errors = []

    if logger is not None:
        logger.debug(f"Found {len(defined_uris)} possible candidates")

    for chunk in chunk_list(defined_uris, 100):
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


def gather_linked_content(nir, graph, pref_header, logger=None):
    """Returns a tuple (list_of_nt_strings, retrieval_error_tuples)"""
    return asyncio.run(collect_linked_content(nir, graph, pref_header, logger=logger))


if __name__ == "__main__":
    import time
    import csv

    startTime = time.time()

    resp = requests.get(
        "https://archivo.dbpedia.org/download?o=http%3A//dbpedia.org/ontology/&f=nt&v=2021.01.08-020001"
    )
    graph = IV.get_graph_of_string(resp.text, "application/ntriples")

    nt_list, error_list = asyncio.run(
        concat_defined_graphs(resp.text, graph, "application/rdf+xml")
    )
    print(f"Length of returned graphs: {len(nt_list)}")
    (parsed_triples, triple_count, rapper_errors, _,) = ontoFiles.parse_rdf_from_string(
        "\n".join(nt_list),
        "http://dbpedia.org/ontology/",
        input_type="ntriples",
        output_type="ntriples",
    )
    print(f"Final ontology with {triple_count}")
    with open("./concatted_ont_async.nt", "w+") as concatted_file:
        print(parsed_triples, file=concatted_file)

    with open("./dbpedia_retrieval_errors_async.csv", "w+") as retr_errors_file:
        writer = csv.writer(retr_errors_file)
        for row in error_list:
            writer.writerow(row)

    executionTime = time.time() - startTime
    print("Execution time in seconds: " + str(executionTime))
