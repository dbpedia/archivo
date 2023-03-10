import hashlib
import re
import os
from pathlib import Path
from typing import Tuple, Optional, List
from urllib.parse import urlparse, urldefrag

__URL_REGEX = r"https?://(?:www\.)?(.+?)/(.*)"

rdfHeadersMapping = {
    "application/rdf+xml": "rdfxml",
    "application/ntriples": "ntriples",
    "text/turtle": "turtle",
    # "application/xhtml": "rdfa",
}

file_ending_mapping = {
    "application/rdf+xml": "owl",
    "application/ntriples": "nt",
    "text/turtle": "ttl",
    "application/xhtml": "html",
    "*/*": "file",
}

# regex to get the content type
contentTypeRegex = re.compile(r"\w+/([\w+-]+)(?:.*)?")

# sentenceRegex
sentenceRegex = re.compile(r"(.*?\.) [A-Z]")


class SetupException(Exception):
    """Risen when something during setup went wrong"""
    pass


def get_local_directory() -> str:
    """Returns the path of the local Archivo lib directory to find related files"""

    utils_path = Path(os.path.realpath(__file__))
    local_path = str(utils_path.parent.parent.absolute())
    if os.path.isdir(os.path.join(local_path, "shacl")) and os.path.isfile(
            os.path.join(local_path, "helpingBinaries", "DisplayAxioms.jar")
    ):
        return local_path
    else:
        raise SetupException(f"Wrong local path: {local_path}")


def generate_databus_identifier_from_uri(url: str, dev: bool = False) -> Tuple[Optional[str], Optional[str]]:
    parsed_obj = urlparse(url)
    # replacing the port with --
    group = parsed_obj.netloc.replace(":", "--")
    artifact = parsed_obj.path + "#" + parsed_obj.fragment
    artifact = artifact.strip("#/~:")
    artifact = (
        artifact.replace("/", "--")
        .replace("_", "--")
        .replace(".", "--")
        .replace("#", "--")
        .replace("~", "--")
        .replace(":", "--")
    )
    if artifact == "":
        artifact = "defaultArtifact"

    if group.startswith("www."):
        group = group.replace("www.", "", 1)
    # none of them can be the empty string or all breaks
    if group == "" or artifact == "":
        return None, None

    if dev:
        artifact = artifact + "--DEV"

    return group, artifact


def get_first_line(text: str) -> str:
    label = None
    for line in text.split("\n"):
        if line.strip() != "":
            label = line.strip()
            break
    return label


def get_first_sentence(text: str) -> str:
    matches = sentenceRegex.findall(text)
    if matches is not None and len(matches) > 0:
        return matches[0].replace("\n", " ")
    else:
        return text.replace("\n", " ")


def is_none_or_empty(string: str) -> bool:
    if string is not None and string != "":
        return False
    else:
        return True


def getLastModifiedFromResponse(response):
    if "last-modified" in response.headers.keys():
        lastMod = response.headers["last-modified"]
        if "GMT" not in lastMod:
            print("WARNING: No GMT time", response.url)
        return lastMod
    else:
        return ""


def getEtagFromResponse(response):
    if "ETag" in response.headers.keys():
        return response.headers["ETag"]
    else:
        return ""


def getContentLengthFromResponse(response):
    if "content-length" in response.headers.keys():
        return response.headers["content-length"]
    else:
        return ""


def deleteAllFilesInDirAndDir(directory):
    if not os.path.isdir(directory):
        return
    for filename in os.listdir(directory):
        if os.path.isfile(os.path.join(directory, filename)):
            os.remove(os.path.join(directory, filename))
    os.rmdir(directory)


def generate_star_string(star_count: int) -> str:
    return "★" * star_count + "☆" * (4 - star_count)


def check_uri_equality(uri1: str, uri2: str) -> bool:
    if urldefrag(uri1)[0] == urldefrag(uri2)[0]:
        return True
    else:
        return False


def get_uri_from_index(uri: str, index: List[str]) -> Optional[str]:
    for indexUri in index:
        if check_uri_equality(uri, indexUri):
            return indexUri
    return None


def get_consistency_status(s: str) -> str:
    if s == "Yes":
        return "CONSISTENT"
    elif "error" in s.lower():
        return "ERROR"
    else:
        return "INCONSISTENT"


def get_content_stats(content: bytes) -> Tuple[str, int]:
    return hashlib.sha256(content).hexdigest(), len(content)
