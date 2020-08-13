from webservice import app
from flask import render_template, flash, redirect, request, abort
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField
from wtforms import validators
import os
from utils.validation import TestSuite
import crawlURIs
from utils import ontoFiles, archivoConfig, queryDatabus, stringTools
import traceback
import sys
import requests
import markdown
from flask_accept import accept, accept_fallback
from urllib.parse import quote
from utils.archivoLogs import webservice_logger
from datetime import datetime


ontoIndex = ontoFiles.loadIndexJsonFromFile(archivoConfig.ontoIndexPath)
fallout = ontoFiles.loadFalloutIndexFromFile(archivoConfig.falloutIndexPath)
archivoPath = os.path.split(app.instance_path)[0]
testingSuite = TestSuite(archivoPath)

class SuggestionForm(FlaskForm):
    suggestUrl = StringField(label="Suggest URL", validators=[validators.DataRequired()])
    submit = SubmitField(label="Suggest")

class InfoForm(FlaskForm):
    uris = SelectField("Enter a URI", choices=[("","")]+[(uri,uri) for uri in ontoIndex], validators=[validators.InputRequired()])
    submit = SubmitField(label="Get Info")


@app.route('/add', methods=['GET', 'POST'])
def index():
    form = SuggestionForm()
    if form.validate_on_submit():
        success, isNir, message = crawlURIs.handleNewUri(form.suggestUrl.data.strip(), ontoIndex, archivoConfig.localPath, fallout, "user-suggestion", False, testSuite=testingSuite, logger=webservice_logger)
        if success:
            ontoFiles.writeIndexJsonToFile(ontoIndex, archivoConfig.ontoIndexPath)
        elif not success and isNir:
            ontoFiles.writeFalloutIndexToFile(archivoConfig.falloutIndexPath, fallout)
        flash("Suggested URL {} for Archivo".format(form.suggestUrl.data))
        return render_template("add.html", responseText=message, form=form)
    return render_template('add.html', responseText="",form=form)

@app.route("/info/", methods=["GET", "POST"])
@app.route("/info", methods=["GET", "POST"])
@accept("text/html")
def vocabInfo():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    form = InfoForm()
    if form.validate_on_submit():
        uri = form.uris.data.strip()
        return redirect(f"/info?o={uri}")
    if ontoUri != "":
        if crawlURIs.checkIndexForUri(ontoUri, ontoIndex) == None:
            abort(status=404)
        indexUri = crawlURIs.checkIndexForUri(ontoUri, ontoIndex)
        group, artifact = stringTools.generateGroupAndArtifactFromUri(indexUri)
        title, comment, versions_info = queryDatabus.getInfoForArtifact(group, artifact)
        general_info = {}
        general_info["source"] = ontoIndex[indexUri]["source"]
        general_info["archivement"] = ontoIndex[indexUri]["accessed"]
        general_info["title"] = title
        general_info["comment"] = comment
        general_info["databusArtifact"] = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        return render_template("info.html", versions_info=sorted(versions_info, key=lambda d: d["version"]["label"], reverse=True), general_info=general_info, form=form)
    return render_template("info.html", general_info={"message":"Enter an ontology URI!"}, form=form)

@vocabInfo.support("text/turtle")
def turtleInfo():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    if not crawlURIs.checkIndexForUri(ontoUri, ontoIndex):
        abort(status=404) 
    return redirect(getRDFInfoLink(ontoUri, "text/turtle"), code=307)

@vocabInfo.support("application/rdf+xml")
def rdfxmlInfo():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    if not crawlURIs.checkIndexForUri(ontoUri, ontoIndex):
        abort(status=404) 
    return redirect(getRDFInfoLink(ontoUri, "application/rdf+xml"), code=307)

@vocabInfo.support("application/n-triples")
def ntriplesInfo():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    if not crawlURIs.checkIndexForUri(ontoUri, ontoIndex):
        abort(status=404) 
    return redirect(getRDFInfoLink(ontoUri, "application/n-triples"), code=307)

@app.route("/list", methods=["GET"])
@app.route("/", methods=["GET"])
def ontoList():
    ontos = []
    allOntosInfo = queryDatabus.allLatestParsedTurtleFiles()
    for uri in ontoIndex:
        group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
        databus_uri = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        latestFallout = getLatestFallout()
        try:
            infoDict = allOntosInfo[databus_uri]
            downloadURIs = {"ttl":infoDict.get("ttlFile", ""), "owl":infoDict.get("owlFile", ""), "nt":infoDict.get("ntFile", "")}
            title = infoDict.get("title", uri)
            available = (False, latestFallout[uri]) if uri in latestFallout else (True, None)
        except KeyError:
            webservice_logger.warning(f"Could't find databus artifact for {uri}")
            downloadUri = None
            

        ontos.append(({"title":title, "uri":uri}, databus_uri, downloadURIs, available))
    return render_template("list.html", len=len(ontos), Ontologies=ontos, ontoNumber=len(ontoIndex))


        
def generateInfoDict(metadata, source, databusLink, latestReleaseLink):
    info = {}
    info["parseable"] = True if metadata["ontology-info"]["triples"] > 0 else False
    info["databusLink"] = databusLink
    info["latestRelease"] = latestReleaseLink
    info["source"] = source
    info["semVersion"] = metadata["ontology-info"]["semantic-version"]
    info["stars"] = str(metadata["ontology-info"]["stars"])
    info["triples"] = str(metadata["ontology-info"]["triples"])
    info["accessed"] = metadata["http-data"]["accessed"]
    info["licenseI"] = metadata["test-results"]["License-I"]
    info["licenseII"] = metadata["test-results"]["License-II"]
    info["consistent"] = metadata["test-results"]["consistent"]
    return info


def getRDFInfoLink(ontologyUrl, mimeType):
    group, artifact = stringTools.generateGroupAndArtifactFromUri(ontologyUrl)
    databusArtifact = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
    queryString = "\n".join((
        "PREFIX dcterm: <http://purl.org/dc/terms/>",
        "PREFIX owl: <http://www.w3.org/2002/07/owl#>",
        "PREFIX dc: <http://purl.org/dc/elements/1.1/>",
        "PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>",
        "PREFIX dct:    <http://purl.org/dc/terms/>",
        "PREFIX dcat:   <http://www.w3.org/ns/dcat#>",
        "PREFIX db:     <https://databus.dbpedia.org/>",
        "PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>",
        "PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>",
        "PREFIX archivo: <http://akswnc7.informatik.uni-leipzig.de/dstreitmatter/archivo/>",
        "",
        "CONSTRUCT {?s ?p ?o . ?dist ?p2 ?o2 . }",
        "{?s dataid:artifact <%s>." % databusArtifact, 
        "?s ?p ?o . ?s dcat:distribution ?dist . ?dist ?p2 ?o2 . }&format=%s&timeout=0&debug=on" % mimeType,
    ))
    encodedString= quote(queryString, safe="&=")
    return f"https://databus.dbpedia.org/repo/sparql?default-graph-uri=&query={encodedString}"

@app.route("/doc", methods=["GET"])
def docPage():
    req = requests.get("https://raw.githubusercontent.com/dbpedia/Archivo/master/README.md")
    
    if req.status_code > 400:
        return render_template("doc.html", markdownDoc=f"Problem loading the page from <https://raw.githubusercontent.com/dbpedia/Archivo/master/README.md>: Status {req.status_code}")
    readme_file = req.text
    md_template_string = markdown.markdown(
        readme_file, extensions=["fenced_code", "sane_lists", "tables"]
    )

    return render_template("doc.html", markdownDoc=md_template_string)

@app.route("/sys/licenses")
def licensesPage():
    return render_template("licenses.html")

@app.route("/download", methods=["GET"])
@accept_fallback
def downloadOntology():
    args = request.args
    ontoUri = args.get("o", "")
    rdfFormat = args.get("f", "")
    if not crawlURIs.checkIndexForUri(ontoUri, ontoIndex):
        abort(status=404)
    group, artifact = stringTools.generateGroupAndArtifactFromUri(ontoUri)
    if rdfFormat == "":
        rdfFormat = "owl"
    downloadLink =queryDatabus.getLatestTurtleURL(group, artifact, fileExt=rdfFormat)

    if downloadLink != None:
        return redirect(downloadLink, code=307)
    else:
        abort(status=404)


@downloadOntology.support("text/turtle")
def turtleDownload():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    rdfFormat = args["f"] if "f" in args else ""
    if not crawlURIs.checkIndexForUri(ontoUri, ontoIndex):
        abort(status=404)
    group, artifact = stringTools.generateGroupAndArtifactFromUri(ontoUri)
    if rdfFormat == "":
        rdfFormat = "ttl"
    downloadLink =queryDatabus.getLatestTurtleURL(group, artifact, fileExt=rdfFormat)
    if downloadLink != None:
        return redirect(downloadLink, code=307)
    else:
        abort(status=404)

@downloadOntology.support("application/rdf+xml")
def rdfxmlDownload():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    rdfFormat = args["f"] if "f" in args else ""
    if not crawlURIs.checkIndexForUri(ontoUri, ontoIndex):
        abort(status=404)
    group, artifact = stringTools.generateGroupAndArtifactFromUri(ontoUri)
    if rdfFormat == "":
        rdfFormat = "owl"
    downloadLink =queryDatabus.getLatestTurtleURL(group, artifact, fileExt=rdfFormat)
    if downloadLink != None:
        return redirect(downloadLink, code=307)
    else:
        abort(status=404)

@downloadOntology.support("application/n-triples")
def ntriplesDownload():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    rdfFormat = args["f"] if "f" in args else ""
    if not crawlURIs.checkIndexForUri(ontoUri, ontoIndex):
        abort(status=404)
    group, artifact = stringTools.generateGroupAndArtifactFromUri(ontoUri)
    if rdfFormat == "":
        rdfFormat = "nt"
    downloadLink =queryDatabus.getLatestTurtleURL(group, artifact, fileExt=rdfFormat)
    if downloadLink != None:
        return redirect(downloadLink, code=307)
    else:
        abort(status=404)

@app.route("/home")
def home():
    return render_template("home.html")

def getLatestFallout():
    falloutOntos = {}
    lastTime = datetime.strptime(fallout[-1][1], "%Y-%m-%d %H:%M:%S.%f")
    for t in fallout[::-1]:
        try:
            distance = lastTime - datetime.strptime(t[1], "%Y-%m-%d %H:%M:%S.%f")
            if distance.seconds > 10800:
                break
            if not t[0] in falloutOntos: 
                falloutOntos[t[0]] = str(t[1]) + t[4]
        except IndexError:
            break
    return falloutOntos
