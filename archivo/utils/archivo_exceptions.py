from typing import List, Union

import requests


class InvalidNIRException(Exception):
    """Exception for invalid NIR for an Ontology Candidate"""


class UnknownRDFFormatException(Exception):
    """Exception if RDF format cannot be determined"""


class UnavailableContentException(Exception):
    """Raised if HTTP content is not available (status > 400)"""

    def __init__(self, response: Union[requests.Response, str]):
        if isinstance(response, requests.Response):
            if response.history:
                starting_url = response.history[0].url
                msg = f"Content is unavailable for {response.request.method} to {response.url} (started with {starting_url}): Status {response.status_code}"
            else:
                msg = f"Content is unavailable for {response.request.method} to {response.url}: Status {response.status_code}"
        else:
            msg = response

        super().__init__(msg)


class UnparseableRDFException(Exception):
    """Raised if RDF string is not parseable without errors"""
