import os
import sys
import json
import subprocess
import re
import csv
from utils import stringTools, inspectVocabs

rapperErrorsRegex=re.compile(r"^rapper: Error.*$")
rapperWarningsRegex=re.compile(r"^rapper: Warning.*$")
rapperTriplesRegex=re.compile(r"rapper: Parsing returned (\d+) triples")

profileCheckerRegex=re.compile(r"(OWL2_DL|OWL2_QL|OWL2_EL|OWL2_RL|OWL2_FULL): OK")
pelletInfoProfileRegex = re.compile(r"OWL Profile = (.*)\n")

def returnRapperErrors(rapperLog):
  errorMatches = []
  warningMatches = []
  for line in rapperLog.split("\n"):
    if rapperErrorsRegex.match(line):
      errorMatches.append(line)
    elif rapperWarningsRegex.match(line):
      warningMatches.append(line)
  return ";".join(errorMatches), ";".join(warningMatches)

def getTripleNumberFromRapperLog(rapperlog):
  match = rapperTriplesRegex.search(rapperlog)
  if match != None:
    return int(match.group(1))
  else:
    return None

def getLatestVersionFromArtifactDir(artifactDir):
  try:
    versionDirs = [dir for dir in os.listdir(artifactDir) if os.path.isdir(os.path.join(artifactDir, dir)) and dir != "target"]
    versionDirs.sort(reverse=True)
    latestVersion = versionDirs[0]
    latestVersionDir = os.path.join(artifactDir, latestVersion)
    return latestVersionDir
  except IndexError:
    print(f"No versions for {artifactDir}")
    return None
  except FileNotFoundError:
    print(f"Couldn't find artifact {artifactDir}")
    return None
  


#removes recursively all dirs that are empty or just contain empty files or directories
def deleteEmptyDirsRecursive(startpath):
  if os.path.isdir(startpath):
    for pathname in os.listdir(startpath):
      if os.path.isdir(startpath + os.sep + pathname):
        deleteEmptyDirsRecursive(startpath + os.sep + pathname)
      elif os.path.isfile(startpath + os.sep + pathname):
        if os.stat(startpath + os.sep + pathname).st_size == 0:
          os.remove(startpath + os.sep + pathname)
    if len(os.listdir(startpath)) == 0:
      os.rmdir(startpath)
  else:
    print(f"Not a directory: {startpath}")

def altWriteVocabInformation(pathToFile, definedByUri, lastModified, rapperErrors, rapperWarnings, etag, tripleSize, bestHeader, licenseViolationsBool, licenseWarningsBool, consistentWithImports, consistentWithoutImports, lodeConform, accessed, headerString, nirHeader, contentLenght, semVersion):
  vocabinfo = {"test-results":{}, "http-data":{}, "ontology-info":{}, "logs":{}}
  vocabinfo["ontology-info"] = {"non-information-uri":definedByUri, "semantic-version":semVersion, "triples":tripleSize, "stars":measureStars(tripleSize, licenseViolationsBool, consistentWithImports, consistentWithoutImports, licenseWarningsBool)}
  vocabinfo["test-results"] = {"consistent":consistentWithImports, "consistent-without-imports":consistentWithoutImports, "License-I":licenseViolationsBool, "License-II":licenseWarningsBool, "lode-conform":lodeConform}
  vocabinfo["http-data"] = {"accessed":accessed, "lastModified":lastModified, "best-header":bestHeader, "content-length":contentLenght, "e-tag":etag}
  vocabinfo["logs"] = {"rapper-errors":rapperErrors, "rapper-warnings":rapperWarnings, "nir-header":nirHeader, "resource-header":headerString}
  
  with open(pathToFile, "w+") as outfile:
    json.dump(vocabinfo, outfile, indent=4, sort_keys=True)


def writeVocabInformation(pathToFile, definedByUri, lastModified, rapperErrors, rapperWarnings, etag, tripleSize, bestHeader, licenseViolationsBool, licenseWarningsBool, consistentWithImports, consistentWithoutImports, lodeConform, accessed, headerString, nirHeader, contentLenght, semVersion=None):
  vocabInformation={}
  vocabInformation["non-information-uri"] = definedByUri
  vocabInformation["accessed"] = accessed
  vocabInformation["lastModified"] = lastModified
  vocabInformation["rapperErrors"] = rapperErrors
  vocabInformation["rapperWarnings"] = rapperWarnings
  vocabInformation["E-Tag"] = etag
  vocabInformation["triples"] = tripleSize
  vocabInformation["best-header"] = bestHeader
  vocabInformation["License-I"] = licenseViolationsBool
  vocabInformation["License-II"] = licenseWarningsBool
  vocabInformation["consistent"] = consistentWithImports
  vocabInformation["consistent-without-imports"] = consistentWithoutImports
  vocabInformation["resource-header"] = headerString
  vocabInformation["NIR-header"] = nirHeader
  vocabInformation["content-length"] = contentLenght
  vocabInformation["lode-conform"] = lodeConform
  if semVersion != None:
    vocabInformation["semantic-version"] = semVersion

  with open(pathToFile, "w+") as outfile:
    json.dump(vocabInformation, outfile, indent=4, sort_keys=True)

def getParsedRdf(sourcefile, sourceUri=None, silent=True):
  if sourceUri == None:
    process = subprocess.Popen(["rapper", "-g", sourcefile, "-o", "rdfxml"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  else:
    process = subprocess.Popen(["rapper", "-I", sourceUri, "-g", sourcefile, "-o", "rdfxml"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  
  stdout, stderr=process.communicate()
  if not silent:
    print(stderr.decode("utf-8"))
  
  return stdout.decode("utf-8")

def parseRDFSource(sourcefile, filepath, outputType, sourceUri=None,deleteEmpty=True, silent=False):
  with open(filepath, "w+") as ontfile:
    if sourceUri == None:
      process = subprocess.Popen(["rapper", "-g", sourcefile, "-o", outputType], stdout=ontfile, stderr=subprocess.PIPE)
    else:
      process = subprocess.Popen(["rapper", "-I", sourceUri,"-g", sourcefile, "-o", outputType], stdout=ontfile, stderr=subprocess.PIPE)
    
    stderr=process.communicate()[1].decode("utf-8")
    if not silent:
      print(stderr)
  if deleteEmpty:
    returnedTriples = getTripleNumberFromRapperLog(stderr)
    if not silent:
      print("Returned Triples: ", returnedTriples)
    if returnedTriples == None or returnedTriples == 0:
      if not silent:
        print("Parsed file empty, deleting...")
      os.remove(filepath)
  return returnRapperErrors(stderr)

def getParsedTriples(filepath):
  process = subprocess.Popen(["rapper", "-c", "-g", filepath], stderr=subprocess.PIPE)
  try:
    stderr = process.communicate()[1].decode("utf-8")
  except UnicodeDecodeError:
    print("There was a decoding error at parsing " + filepath)
    return None
  return getTripleNumberFromRapperLog(stderr)

def loadIndexJson():
  with open(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "indices", "vocab_index.json"), "r") as indexfile:
    jsonIndex = json.load(indexfile)
  return jsonIndex

def loadIndexJsonFromFile(filepath):
  with open(filepath, "r") as indexfile:
    jsonIndex = json.load(indexfile)
  return jsonIndex

def loadSimpleIndex():
  if not os.path.isfile(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "vocab_index.txt")):
    return []
  with open(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "vocab_index.txt"), "r") as indexfile:
    lines = [line.rstrip() for line in indexfile]
  return lines

def writeSimpleIndex(index):
  with open(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "vocab_index.txt"), "w") as indexfile: 
    print("\n".join(index), file=indexfile)


def writeIndex(index):
  with open(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "vocab_index.tsv"), "w") as indexfile:
    writer = csv.writer(indexfile, delimiter="\t")
    writer.writerows(index)

def checkIfUriInIndex(uri, index):
  for i, uriObj in enumerate(index):
    if uriObj["vocab-uri"] == uri:
      return i
  return None

def writeIndexJson(index):
  with open(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "indices","vocab_index.json"), "w+") as indexfile:
    json.dump(index, indexfile, indent=4, sort_keys=True)

def writeIndexJsonToFile(index, filepath):
  with open(filepath, "w+") as indexfile:
    json.dump(index, indexfile, indent=4, sort_keys=True)

def loadFalloutIndex():
  if not os.path.isfile(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "fallout_index.csv")):
    return []
  with open(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "fallout_index.csv"), "r") as csvfile:
    reader = csv.reader(csvfile)
    return [row for row in reader]

def loadFalloutIndexFromFile(filepath):
  with open(filepath, "r") as csvfile:
    reader = csv.reader(csvfile)
    return [row for row in reader]

def writeFalloutIndex(index):
  with open(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "fallout_index.csv"), "w+") as csvfile: 
    writer = csv.writer(csvfile, delimiter=",")
    for row in index:
      writer.writerow(row)

def writeFalloutIndexToFile(filepath, index):
  with open(filepath, "w+") as csvfile: 
    writer = csv.writer(csvfile, delimiter=",")
    for row in index:
      writer.writerow(row)

def readCsvFile(pathToFile):
  with open(pathToFile, "r") as csvfile:
    reader = csv.reader(csvfile)
    return set([row[0] for row in reader])

def secondColumnOfTSV(pathToFile):
  with open(pathToFile, "r") as csvfile:
    reader = csv.reader(csvfile, delimiter="\t")
    return set([row[1] for row in reader])

def loadListFile(pathToFile):
  with open(pathToFile, "r") as listFile:
    lines = [line.strip() for line in listFile]
  return lines

def measureStars(triples, licenseI, consistent, consistentWithoutImports, licenseII):
  stars = 0
  if triples > 0:
    stars = stars + 1
  if licenseI == True:
    stars = stars + 1

  if not stars == 2:
    return stars

  if consistent == "Yes" or consistentWithoutImports == "Yes":
    stars = stars + 1
  if licenseII == True:
    stars = stars + 1
  return stars

def inspectMetadata(rootdir):

  resultData = {"filenumber": 0}

  exptKeys = set(["triples", "E-Tag", "rapperErrors", "rapperWarnings", "lastModified", "content-length", "semantic-version", "NIR-header", "resource-header", "accessed"])

  for groupdir in [dir for dir in os.listdir(rootdir) if os.path.isdir(os.path.join(rootdir, dir))]:
    for artifactDir in [dir for dir in os.listdir(os.path.join(rootdir, groupdir)) if os.path.isdir(os.path.join(rootdir, groupdir, dir))]:
      print("Generating metadata for", groupdir, artifactDir, file=sys.stderr)
      versionDirs = [dir for dir in os.listdir(os.path.join(rootdir, groupdir, artifactDir)) if os.path.isdir(os.path.join(rootdir, groupdir, artifactDir, dir)) and dir != "target"]
      if versionDirs == []:
        print("Couldnt find version for", groupdir, artifactDir, file=sys.stderr)
        continue
      versionDir = versionDirs[0]  
      #filepath = os.path.join(rootdir, groupdir, artifactDir, versionDir, artifactDir + "_type=parsed.ttl")
      jsonPath = os.path.join(rootdir, groupdir, artifactDir, versionDir, artifactDir + "_type=meta.json")
      if not os.path.isfile(jsonPath):
        print("Couldnt find metadata", file=sys.stderr)
        continue
      resultData["filenumber"] += 1 
      with open(jsonPath, "r") as jsonFile:
        metadata = json.load(jsonFile)

      for key in set(metadata.keys()) - exptKeys:
        if key in resultData.keys():
          if str(metadata[key]) in resultData[key].keys():
            oldNumber = resultData[key][str(metadata[key])]
            resultData[key][str(metadata[key])] = oldNumber + 1
          else:
            resultData[key][str(metadata[key])] = 1
        else:
          resultData[key] = {str(metadata[key]) : 1}
  print(json.dumps(resultData, indent=1))

def checkIndexValidity():
  index = loadIndexJson()
  for uri in index:
    similarUris = []
    for otherUri in index:
      if uri in otherUri:
        similarUris.append(otherUri)
    similarUris.remove(uri)
    if similarUris != []:
      print("Multiple occasions:", uri, ";".join(similarUris))

def getProfile(pelletInfoPath, pelletInfoPathNoImports, profilePath):
  profiles = []
  for pelletInfo in (pelletInfoPath, pelletInfoPathNoImports):
    if os.path.isfile(pelletInfo):
      with open(pelletInfo, "r") as pelletInfoFile:
        content = pelletInfoFile.read()
        match = pelletInfoProfileRegex.search(content)
        if match != None:
          profiles.append(match.group(1).strip().replace(" ", ""))
  if os.path.isfile(profilePath):
    with open(profilePath, "r") as profileFile:
      content = profileFile.read()
      for match in profileCheckerRegex.finditer(content):
        profiles.append(match.group(1).replace("_", ""))
  return profiles
  

def genStats(rootdir):
  index = loadIndexJson()
  
  exptKeys = set(["triples", "e-tag", "rapper-errors", "rapper-warnings", "lastModified", "content-length", "semantic-version", "nir-header", "resource-header", "accessed", "non-information-uri"])

  resultData = {}
  resultData["found-files"] = 0
  resultData["triples"] = {"Zero": 0, "<100" : 0, "<1000" : 0, "<10000" : 0, "<100000" : 0, ">100000" : 0 }
  resultData["profiles"] = {}
  resultData["stars"] = {"0 Stars":0, "1 Stars" : 0, "2 Stars":0, "3 Stars":0, "4 Stars":0}
  resultData["best-header"] = {}

  for indexUri in index.keys():
    groupId, artifact =  stringTools.generateGroupAndArtifactFromUri(indexUri)

    if not os.path.isdir(os.path.join(rootdir, groupId, artifact)):
      print("Couldnt find data for", indexUri, file=sys.stderr)
      continue
    versionDirs = [dir for dir in os.listdir(os.path.join(rootdir, groupId, artifact)) if os.path.isdir(os.path.join(rootdir, groupId, artifact, dir)) and dir != "target"]
    if versionDirs == []:
        print("Couldnt find version for", groupId, artifact, file=sys.stderr)
        continue
    versionDir = versionDirs[0] 
    filesPath = os.path.join(rootdir, groupId, artifact, versionDir)
    jsonPath = os.path.join(filesPath, artifact + "_type=meta.json")
    if not os.path.isfile(jsonPath):
      print("Couldnt find metadata", file=sys.stderr)
      continue
    lodeShaclReport = os.path.join(filesPath, artifact + "_type=shaclReport_validates=lodeMetadata.ttl")
    if not os.path.isfile(lodeShaclReport):
      print("Couldnt find shacl report", file=sys.stderr)
      continue
    resultData["found-files"] = resultData["found-files"] + 1
    lodeShaclGraph = inspectVocabs.getGraphOfVocabFile(lodeShaclReport)
    with open(jsonPath, "r") as jsonFile:
      metadata = json.load(jsonFile)

    best_header = metadata["http-data"]["best-header"]
    if best_header in resultData["best-header"]:
      resultData["best-header"][best_header] = resultData["best-header"][best_header] + 1
    else:
       resultData["best-header"][best_header] = 1
    
    for key in metadata["test-results"]:
      val = str(metadata["test-results"][key])
      if key in resultData:
        if val in resultData[key]:
          resultData[key][val] = resultData[key][val] + 1
        else:
          resultData[key][val] = 1
      else:
        resultData[key] = {val : 1}
    
    stars = metadata["ontology-info"]["stars"]

    resultData["stars"][str(stars)+ " Stars"] = resultData["stars"][str(stars)+ " Stars"] + 1
    
    tripleNumber = metadata["ontology-info"]["triples"]
    if tripleNumber == 0:
      triplesString = "Zero"
    elif tripleNumber < 100:
      triplesString = "<100"
    elif tripleNumber < 1000:
      triplesString = "<1000"
    elif tripleNumber < 10000:
      triplesString = "<10000"
    elif tripleNumber < 100000:
      triplesString = "<100000"
    else:
      triplesString = ">100000"
    
    resultData["triples"][triplesString] = resultData["triples"][triplesString] + 1

    lodeValue = inspectVocabs.checkShaclReport(lodeShaclGraph)
    if "lodeShaclValue" in resultData:
      if lodeValue in resultData["lodeShaclValue"]:
        oldNumber = resultData["lodeShaclValue"][lodeValue]
        resultData["lodeShaclValue"][lodeValue] = oldNumber +1
      else:
        resultData["lodeShaclValue"][lodeValue] = 1
    else:
      resultData["lodeShaclValue"] = {lodeValue : 1}

    profiles = getProfile(os.path.join(filesPath, artifact + "_type=pelletInfo_imports=FULL.txt"), os.path.join(filesPath, artifact + "_type=pelletInfo_imports=NONE.txt"), os.path.join(filesPath, artifact + "_type=profile.txt"))  
    profiles = list(set(profiles))
    profiles.sort()
    if profiles == []:
      profiles = "Error - couldnt determine profile"
    else:
      profiles = ";".join(profiles)

    if profiles in resultData["profiles"]:
      oldNumber = resultData["profiles"][profiles]
      resultData["profiles"][profiles] = oldNumber +1
    else:
      resultData["profiles"][profiles] = 1

  print(json.dumps(resultData, indent=1, sort_keys=True))
     
    
