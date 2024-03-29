from logging import Logger
from typing import Optional, Tuple

import rdflib
import requests
# since pylode is not compatible with rdflib 6.2.0 it will be removed
import pylode

# url for the lode docu service
lodeServiceUrl = "https://w3id.org/lode/owlapi/"

# url for the oops rest service
oopsServiceUrl = " http://oops.linkeddata.es/rest"


def getLodeDocuFile(vocab_uri: str, logger: Logger) -> Tuple[Optional[str], Optional[str]]:
    try:
        response = requests.get(lodeServiceUrl + vocab_uri)
        if response.status_code < 400:
            return response.text, None
        else:
            return None, f"Access Error - Status {response.status_code}"
    except (
        requests.exceptions.TooManyRedirects,
        TimeoutError,
        requests.exceptions.ConnectionError,
        requests.exceptions.ReadTimeout,
    ) as e:
        logger.error("Exeption in loading the LODE-docu", exc_info=True)
        return None, str(e)


def getOOPSReport(parsedRdfString, logger):
    oopsXml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "   <OOPSRequest>\n"
        "   <OntologyURI></OntologyURI>\n"
        f"    <OntologyContent><![CDATA[\n{parsedRdfString}]]></OntologyContent>\n"
        "   <Pitfalls></Pitfalls>\n"
        "   <OutputFormat>RDF/XML</OutputFormat>\n"
        "</OOPSRequest>"
    )
    headers = {"Content-Type": "application/xml"}
    try:
        response = requests.post(
            oopsServiceUrl, data=oopsXml.encode("utf-8"), headers=headers, timeout=30
        )
        if response.status_code < 400:
            return response.text, None
        else:
            logger.error(f"OOPS not acessible: Status {response.status_code}")
            return None, f"Not Accessible - Status {response.status_code}"
    except Exception as e:
        logger.error("Exeption in loading the OOPS-report", exc_info=True)
        return None, str(e)


def get_pylode_doc_string(ont_graph: rdflib.Graph) -> str:
    """Generates Pylode HTML documentation"""

    ont_doc = pylode.OntDoc(ont_graph)
    html_docu = ont_doc.make_html()
    return html_docu
