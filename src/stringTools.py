import re
import os

urlRegex=r"https?://(?:www\.)?(.+?)/(.*)"

# regex for parsing the file ending of an url
uriFileExtensionRegex = re.compile(r"^.*\/.+(\.\w+)$")

#should be extended maybe
fileTypeDict = {"turtle": ".ttl", "rdf+xml": ".rdf", "ntriples": ".nt", "rdf+n3":".n3", "html":".html", "xml":".xml"}

# regex to get the content type
contentTypeRegex = re.compile(r"\w+/([\w+-]+)(?:.*)?")

def isNoneOrEmpty(string):
  if string != None and string != "":
    return False
  else:
    return True

def getFileExtensionFromUri(uri):
  match = uriFileExtensionRegex.match(uri)
  if match != None:
    return match.group(1)
  else:
    return ""

def generateGroupAndArtifactFromUri(vocab_uri):
  matcher=re.search(urlRegex, vocab_uri)
  if matcher != None:
    groupId=matcher.group(1)
    artifact=matcher.group(2)
  else:
    return None, None
  if artifact != "":
    if artifact[-1] == "#" or artifact[-1] == "/":
      artifact=artifact[:-1]
    artifact=artifact.replace("/", "--").replace("_", "--").replace(".", "--")
  else:
    artifact="vocabulary"
  return groupId, artifact


def getLastModifiedFromResponse(response):
  if "last-modified" in response.headers.keys():
    lastMod = response.headers["last-modified"]
    if not "GMT" in lastMod:
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
  fileEnding=""
  if "Content-Type" in response.headers.keys():
    contentType = response.headers["content-type"]
    match = contentTypeRegex.search(contentType)
    if match != None:
      fileEnding = fileTypeDict.get(match.group(1), "")
  
  if fileEnding == "":
    fileEnding = getFileExtensionFromUri(response.url)
  
  if fileEnding == "":
    fileEnding = ".file"
  return fileEnding
    
  

def deleteAllFilesInDir(directory):
  if not os.path.isdir(directory):
    return
  for filename in os.listdir(directory):
    if os.path.isfile(os.path.join(directory, filename)):
      os.remove(os.path.join(directory, filename))