from webservice import app
from flask import render_template, flash, redirect, request
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
def vocabInfo():
    ontoUri = request.query_string.decode("utf-8")
    form = InfoForm()
    if form.validate_on_submit():
        uri = form.uris.data.strip()
        return redirect(f"/info?{uri}")
    if ontoUri != "":
        try:
            indexUri = crawlURIs.checkIndexForUri(ontoUri, ontoIndex)
            if indexUri == None:
                return  render_template("info.html", info={"message":f"ERROR: Couln't find {ontoUri} in the Archivo Index."}, form=form)
            group, artifact = stringTools.generateGroupAndArtifactFromUri(indexUri)
            source = ontoIndex[indexUri]["source"]
            success, databusLink, metadata = queryDatabus.getLatestMetaFile(group, artifact)
            if success:
                info = generateInfoDict(metadata, source, databusLink)
            else:
                info = {"message":metadata}
            return render_template("info.html", info=info, form=form)
        except KeyError:
            traceback.print_exc(file=sys.stdout)
            return render_template("info.html", info={"message":f"ERROR: {ontoUri} is not in the Archivo Index."}, form=form)
    return render_template("info.html", info={"message":"Enter an ontology URI!"}, form=form)

@app.route("/list", methods=["GET"])
@app.route("/", methods=["GET"])
def ontoList():
    ontos = [uri for uri in ontoIndex]
    return render_template("list.html", len=len(ontos), Ontologies=ontos)
        
def generateInfoDict(metadata, source, databusLink):
    info = {}
    info["databusLink"] = databusLink
    info["source"] = source
    info["semVersion"] = metadata["ontology-info"]["semantic-version"]
    info["stars"] = str(metadata["ontology-info"]["stars"])
    info["triples"] = str(metadata["ontology-info"]["triples"])
    info["accessed"] = metadata["http-data"]["accessed"]
    return info


@app.route("/doc", methods=["GET"])
def docPage():
    readme_file = requests.get("https://raw.githubusercontent.com/dbpedia/Archivo/master/README.md").text
    md_template_string = markdown.markdown(
        readme_file, extensions=["fenced_code", "sane_lists"]
    )

    return render_template("doc.html", markdownDoc=md_template_string)