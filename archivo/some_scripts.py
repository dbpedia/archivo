from utils.validation import TestSuite
from utils.queryDatabus import latestNtriples, get_last_official_index
import crawlURIs
from utils.archivoLogs import discovery_logger
import json
import requests
import ast
from utils import inspectVocabs as IV
from utils import ontoFiles
import rdflib
from io import StringIO

ts = TestSuite(".")
# user_output = []

# crawlURIs.handleDevURI("http://open-services.net/ns/core#", "https://raw.githubusercontent.com/oslc-op/oslc-specs/master/specs/core/core-vocab.ttl", "./../testdir", ts, discovery_logger, user_output)


def find_cors_headers():
    latestNtriples = latestNtriples()

    result = {}

    for nir, d in latestNtriples.items():
        metaURL = d["meta"]

        metadata = requests.get(metaURL).json()

        if (
            metadata["logs"]["nir-header"] == ""
            and metadata["logs"]["resource-header"] == ""
        ):
            print(f"No Headers found for {metaURL}")
            continue

        if metadata["logs"]["nir-header"] != "":
            StringIO

        resource_headers = ast.literal_eval(metadata["logs"]["resource-header"])

        if not (
            "Access-Control-Allow-Origin" in metadata["logs"]["nir-header"]
            or "Access-Control-Allow-Origin" in metadata["logs"]["resource-header"]
        ):
            result["None"] = result.get("None", 0) + 1

        if "Access-Control-Allow-Origin" in nir_headers:
            v = nir_headers["Access-Control-Allow-Origin"]
            result[v] = result.get(v, 0) + 1

    return result


def check_ontologies():

    latest_index = get_last_official_index()
    log_file_path = "./bad_archivo_onts.csv"

    for nir, src, _ in latest_index:
        user_output = []
        best_header, _, _ = crawlURIs.determine_best_content_type(
            nir, user_output=user_output, logger=discovery_logger
        )

        if best_header is None:
            with open(log_file_path, "a") as uri_file:
                reason_string = user_output[-1]["message"].replace("\n", " -- ")
                uri_file.write(f"{nir},{src},{reason_string}\n")


def retrieve_defined_graph_as_nt(uri, header, permit_rapper_errors=False):

    response, error_str = download_rdf_string(uri, acc_header=header)

    if error_str is not None:
        return None, f"Error during retrieval of {uri}: " + error_str

    try:
        (
            nt_graph,
            triple_number,
            rapper_errors,
            rapper_warnings,
        ) = ontoFiles.parse_rdf_from_string(
            response.text,
            uri,
            input_type=rdfHeadersMapping[header],
            output_type="ntriples",
        )

        if not permit_rapper_errors and rapper_errors != []:
            return None, f"Error during parsing content of {uri}" + ";".join(
                rapper_errors
            )

        return nt_graph, None
    except Exception as e:
        return None, f"Error during parsing content of {uri}" + str(e)


def concat_defined_graphs(ont_nt_str, graph, pref_header):

    defined_uris = IV.get_defined_URIs(graph)

    all_nt_strings = []
    all_nt_strings.append(ont_nt_str)

    retrieval_errors = []

    for i, uri in enumerate(defined_uris):
        print(f"{i}/{len(defined_uris)} Handling {uri}")
        nt_str, error = retrieve_defined_graph_as_nt(uri, pref_header)
        if error is None:
            all_nt_strings.append(nt_str)
        else:
            retrieval_errors.append(error)

    return "\n".join(all_nt_strings), retrieval_errors


def load_imports_into_archivo(uri, source="user-suggestion"):

    from archivo import run_discovery, get_correct_path
    from utils import archivoConfig, validation

    g = rdflib.Graph()
    g.load(uri)

    imports = [str(o) for _, p, o in g if rdflib.URIRef("http://www.w3.org/2002/07/owl#imports") == p]

    run_discovery(imports, source, archivoConfig.localPath, validation.TestSuite(get_correct_path()))

def check_imports_for_existence(uri: str):

    from urllib.parse import quote
    g = rdflib.Graph()
    g.load(uri)

    imports = [str(o) for _, p, o in g if rdflib.URIRef("http://www.w3.org/2002/07/owl#imports") == p]

    for imp in imports:
        archivo_uri = f"https://archivo.dbpedia.org/info?o={imp}"
        resp = requests.head(archivo_uri, headers={"Accept": "text/html"})
        print(f"URI: {imp} ; Archivo: {archivo_uri}; Status: {resp.status_code}")

if __name__ == "__main__":

    load_imports_into_archivo("https://archivo.dbpedia.org/download?o=http%3A//bdi.si.ehu.es/bdi/ontologies/ExtruOnt/ExtruOnt&f=owl&v=2020.12.14-144514", source="SPO")
