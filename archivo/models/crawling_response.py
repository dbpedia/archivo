from dataclasses import dataclass

import requests

from models.content_negotiation import RDF_Type
from utils.parsing import RapperParsingInfo


@dataclass
class CrawlingResponse:
    """Represents the response of the best effort crawling"""

    uri: str
    response: requests.Response
    rdf_type: RDF_Type
    parsing_info: RapperParsingInfo
