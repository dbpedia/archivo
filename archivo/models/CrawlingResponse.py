from dataclasses import dataclass

import requests

from archivo.models.ContentNegotiation import RDF_Type


@dataclass
class CrawlingResponse:
    """Represents the response of the best effort crawling"""
    nir: str
    response: requests.Response
    rdf_content: str
    rdf_type: RDF_Type
    triple_number: int
