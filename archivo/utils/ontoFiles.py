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

def parse_rdf_from_string(rdf_string, base_uri, input_type=None, output_type="ntriples"):
  if input_type == None:
    command = ['rapper', '-I', base_uri, '-g', '-', '-o', output_type]
  else:
    command = ['rapper', '-I', base_uri, '-i', input_type, '-', '-o', output_type]

  process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, input=bytes(rdf_string, 'utf-8'))
  triples = getTripleNumberFromRapperLog(process.stderr.decode('utf-8'))
  errors, warnings = returnRapperErrors(process.stderr.decode('utf-8'))
  return process.stdout.decode('utf-8'), triples, errors, warnings

def get_triples_from_rdf_string(rdf_string, base_uri, input_type=None):
  if input_type == None:
    command = ['rapper', '-I', base_uri, '-g', '-']
  else:
    command = ['rapper', '-I', base_uri, '-i', input_type, '-']

  process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, input=bytes(rdf_string, 'utf-8'))
  triples = getTripleNumberFromRapperLog(process.stderr.decode('utf-8'))
  errors, _ = returnRapperErrors(process.stderr.decode('utf-8'))
  return triples, errors

def getLatestVersionFromArtifactDir(artifactDir):
  try:
    versionDirs = [dir for dir in os.listdir(artifactDir) if os.path.isdir(os.path.join(artifactDir, dir)) and dir != "target"]
    versionDirs.sort(reverse=True)
    latestVersion = versionDirs[0]
    latestVersionDir = os.path.join(artifactDir, latestVersion)
    return latestVersionDir
  except IndexError:
    return None
  except FileNotFoundError:
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

def altWriteVocabInformation(pathToFile, definedByUri, lastModified, rapperErrors, rapperWarnings, etag, tripleSize, bestHeader, licenseViolationsBool, licenseWarningsBool, consistentWithImports, consistentWithoutImports, lodeConform, accessed, headerString, nirHeader, contentLenght, semVersion, snapshot_url):
  vocabinfo = {"test-results":{}, "http-data":{}, "ontology-info":{}, "logs":{}}
  vocabinfo["ontology-info"] = {"non-information-uri":definedByUri, "snapshot-url":snapshot_url,"semantic-version":semVersion, "triples":tripleSize, "stars":measureStars(rapperErrors, licenseViolationsBool, consistentWithImports, consistentWithoutImports, licenseWarningsBool)}
  vocabinfo["test-results"] = {"consistent":consistentWithImports, "consistent-without-imports":consistentWithoutImports, "License-I":licenseViolationsBool, "License-II":licenseWarningsBool, "lode-conform":lodeConform}
  vocabinfo["http-data"] = {"accessed":str(accessed), "lastModified":lastModified, "best-header":bestHeader, "content-length":contentLenght, "e-tag":etag}
  vocabinfo["logs"] = {"rapper-errors":rapperErrors, "rapper-warnings":rapperWarnings, "nir-header":nirHeader, "resource-header":headerString}
  
  with open(pathToFile, "w+") as outfile:
    json.dump(vocabinfo, outfile, indent=4, sort_keys=True)


def getParsedRdf(sourcefile, sourceUri=None, logger=None, silent=True):
  if sourceUri == None:
    process = subprocess.Popen(["rapper", "-g", sourcefile, "-o", "rdfxml"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  else:
    process = subprocess.Popen(["rapper", "-I", sourceUri, "-g", sourcefile, "-o", "rdfxml"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  
  stdout, stderr=process.communicate()
  if logger != None and not silent:
    logger.debug(stderr.decode("utf-8"))
  
  return stdout.decode("utf-8")

def parseRDFSource(sourcefile, filepath, outputType, sourceUri=None,deleteEmpty=True, logger=None, inputFormat=None, silent=True):
  rapperCommand = ["rapper",  sourcefile, "-o", outputType]
  if inputFormat == None:
    inputList = ["-g"]
  else:
    inputList = ["-i", inputFormat]
  rapperCommand[1:1] = inputList
  if sourceUri != None:
    rapperCommand[1:1] = ["-I", sourceUri]
  with open(filepath, "w+") as ontfile:
    process = subprocess.Popen(rapperCommand, stdout=ontfile, stderr=subprocess.PIPE)
    stderr=process.communicate()[1].decode("utf-8")
    if logger != None and not silent:
      logger.debug(stderr)
  if deleteEmpty:
    returnedTriples = getTripleNumberFromRapperLog(stderr)
    if returnedTriples == None or returnedTriples == 0:
      if logger != None and not silent:
        logger.warning("Parsed file empty, deleting...")
      os.remove(filepath)
  return returnRapperErrors(stderr)

def getParsedTriples(filepath, inputFormat=None):
  if inputFormat == None:
    process = subprocess.Popen(["rapper", "-c", "-g", filepath], stderr=subprocess.PIPE)
  else:
    process = subprocess.Popen(["rapper", "-c", "-i", inputFormat, filepath], stderr=subprocess.PIPE)

  try:
    stderr = process.communicate()[1].decode("utf-8")
  except UnicodeDecodeError:
    return None, None
  return getTripleNumberFromRapperLog(stderr), returnRapperErrors(stderr)[0]



def measureStars(rapperErrors, licenseI, consistent, consistentWithoutImports, licenseII):
  stars = 0
  if rapperErrors == "":
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
