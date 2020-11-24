import re
import os
from urllib.parse import urlparse, urldefrag

urlRegex = r"https?://(?:www\.)?(.+?)/(.*)"

# regex for parsing the file ending of an url
uriFileExtensionRegex = re.compile(r"^.*\/.+(\.\w+)$")

# should be extended maybe
fileTypeDict = {
    "turtle": ".ttl",
    "rdf+xml": ".rdf",
    "ntriples": ".nt",
    "rdf+n3": ".n3",
    "html": ".html",
    "xml": ".xml",
}

# regex to get the content type
contentTypeRegex = re.compile(r"\w+/([\w+-]+)(?:.*)?")

# sentenceRegex
sentenceRegex = re.compile(r"(.*?\.) [A-Z]")


def generateGroupAndArtifactFromUri(url, dev=False):
    parsedObj = urlparse(url)
    # replacing the port with --
    group = parsedObj.netloc.replace(":", "--")
    artifact = parsedObj.path + "#" + parsedObj.fragment
    artifact = artifact.strip("#/~")
    artifact = (
        artifact.replace("/", "--")
        .replace("_", "--")
        .replace(".", "--")
        .replace("#", "--")
        .replace("~", "--")
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


def getFirstLine(text):
    label = None
    for line in text.split("\n"):
        if line.strip() != "":
            label = line.strip()
            break
    return label


def getFirstSentence(text):
    matches = sentenceRegex.findall(text)
    if matches is not None and len(matches) > 0:
        return matches[0].replace("\n", " ")
    else:
        return text.replace("\n", " ")


def isNoneOrEmpty(string):
    if string is not None and string != "":
        return False
    else:
        return True


def getFileExtensionFromUri(uri):
    match = uriFileExtensionRegex.match(uri)
    if match is not None:
        return match.group(1)
    else:
        return ""


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


def getFileEnding(response):
    fileEnding = ""
    if "Content-Type" in response.headers.keys():
        contentType = response.headers["content-type"]
        match = contentTypeRegex.search(contentType)
        if match is not None:
            fileEnding = fileTypeDict.get(match.group(1), "")

    if fileEnding == "":
        fileEnding = getFileExtensionFromUri(response.url)

    if fileEnding == "":
        fileEnding = ".file"
    return fileEnding


def deleteAllFilesInDirAndDir(directory):
    if not os.path.isdir(directory):
        return
    for filename in os.listdir(directory):
        if os.path.isfile(os.path.join(directory, filename)):
            os.remove(os.path.join(directory, filename))
    os.rmdir(directory)


def generateStarString(number: int):
    return "★" * number + "☆" * (4 - number)


def check_uri_equality(uri1, uri2):
    if urldefrag(uri1)[0] == urldefrag(uri2)[0]:
        return True
    else:
        return False


def get_uri_from_index(uri, index):
    for indexUri in index:
        if check_uri_equality(uri, indexUri):
            return indexUri
    return None
