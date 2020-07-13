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
from flask_accept import accept
from urllib.parse import quote

ontoIndex = ontoFiles.loadIndexJsonFromFile(archivoConfig.ontoIndexPath)
fallout = ontoFiles.loadFalloutIndexFromFile(archivoConfig.falloutIndexPath)

archivoPath = os.path.split(app.instance_path)[0]
shaclPath = os.path.join(archivoPath, "shacl")
testingSuite = TestSuite(shaclPath)

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
        success, isNir, message = crawlURIs.handleNewUri(form.suggestUrl.data.strip(), ontoIndex, archivoConfig.localPath, fallout, "user-suggestion", False, testSuite=testingSuite)
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
        if not crawlURIs.checkIndexForUri(ontoUri, ontoIndex):
            abort(status=404) 
        try:
            indexUri = crawlURIs.checkIndexForUri(ontoUri, ontoIndex)
            if indexUri == None:
                return  render_template("info.html", info={"message":f"ERROR: Couln't find {ontoUri} in the Archivo Index."}, form=form)
            group, artifact = stringTools.generateGroupAndArtifactFromUri(indexUri)
            source = ontoIndex[indexUri]["source"]
            success, databusLink, versionLink, metadata = queryDatabus.getLatestMetaFile(group, artifact)
            if success:
                info = generateInfoDict(metadata, source, databusLink, versionLink)
            else:
                info = {"message":metadata}
            info["addedDate"] = ontoIndex[indexUri]["accessed"]
            return render_template("info.html", info=info, form=form)
        except KeyError:
            traceback.print_exc(file=sys.stdout)
            return render_template("info.html", info={"message":f"ERROR: {ontoUri} is not in the Archivo Index."}, form=form)
    return render_template("info.html", info={"message":"Enter an ontology URI!"}, form=form)

@vocabInfo.support("text/turtle")
def turtleInfo():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    if not crawlURIs.checkIndexForUri(ontoUri, ontoIndex):
        abort(status=404) 
    return redirect(getRDFInfoLink(ontoUri, "text/turtle"), code=303)

@vocabInfo.support("application/rdf+xml")
def rdfxmlInfo():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    if not crawlURIs.checkIndexForUri(ontoUri, ontoIndex):
        abort(status=404) 
    return redirect(getRDFInfoLink(ontoUri, "application/rdf+xml"), code=303)

@vocabInfo.support("application/n-triples")
def ntriplesInfo():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    if not crawlURIs.checkIndexForUri(ontoUri, ontoIndex):
        abort(status=404) 
    return redirect(getRDFInfoLink(ontoUri, "application/n-triples"), code=303)

@app.route("/list", methods=["GET"])
@app.route("/", methods=["GET"])
def ontoList():
    ontos = []
    for uri in ontoIndex:
        group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
        ontos.append((uri, f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"))
    return render_template("list.html", len=len(ontos), Ontologies=ontos)


        
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
        "PREFIX  owl: <http://www.w3.org/2002/07/owl#>",
        "PREFIX  dc: <http://purl.org/dc/elements/1.1/>",
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
        return render_template("doc.html", markdownDoc=f"Prblem loading the page from <https://raw.githubusercontent.com/dbpedia/Archivo/master/README.md>: Status {req.status_code}")
    readme_file = req.text
    md_template_string = markdown.markdown(
        readme_file, extensions=["fenced_code", "sane_lists", "tables"]
    )

    return render_template("doc.html", markdownDoc=md_template_string)