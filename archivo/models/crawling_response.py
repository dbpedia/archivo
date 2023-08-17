from dataclasses import dataclass

import requests

from archivo.models.content_negotiation import RDF_Type
from archivo.utils.parsing import RapperParsingInfo

@dataclass
class CrawlingResponse:
    """Represents the response of the best effort crawling"""
    nir: str
    response: requests.Response
    rdf_type: RDF_Type
    parsing_info: RapperParsingInfo
