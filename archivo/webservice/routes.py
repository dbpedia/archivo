from webservice import app
from webservice import localPath
from flask import render_template, flash, redirect
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField
from wtforms import validators
import os
from utils.validation import TestSuite
import crawlURIs
from utils import ontoFiles, archivoConfig, queryDatabus, stringTools

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


@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
def index():
    form = SuggestionForm()
    if form.validate_on_submit():
        success, isNir, message = crawlURIs.handleNewUri(form.suggestUrl.data.strip(), ontoIndex, localPath, fallout, "user-suggestion", False, testSuite=testingSuite)
        if success:
            ontoFiles.writeIndexJsonToFile(ontoIndex, archivoConfig.ontoIndexPath)
        elif not success and isNir:
            ontoFiles.writeFalloutIndexToFile(archivoConfig.falloutIndexPath, fallout)
        flash("Suggested URL {} for Archivo".format(form.suggestUrl.data))
        return render_template("index.html", responseText=message, form=form)
    return render_template('index.html', responseText="Suggest Url",form=form)

@app.route("/vocab-info", methods=["GET", "POST"])
def vocabInfo():
    form = InfoForm()
    if form.validate_on_submit():
        try:
            uri = form.uris.data.strip()
            source = ontoIndex[uri]["source"]
            group, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
            success, databusLink, metadata = queryDatabus.getLatestMetaFile(group, artifact)
            if success:
                info = generateInfoDict(metadata, source, databusLink)
            else:
                info = {"message":metadata}
        except KeyError:
            info = {"message":f"There was an error retrieving the metadata from {databusLink}."}
        return render_template("vocabInfo.html", info=info, form=form)
    return render_template("vocabInfo.html", info={"message":"Enter an ontology URI!"}, form=form)
        
def generateInfoDict(metadata, source, databusLink):
    info = {}
    info["databusLink"] = databusLink
    info["source"] = source
    info["semVersion"] = metadata["ontology-info"]["semantic-version"]
    info["stars"] = str(metadata["ontology-info"]["stars"])
    info["triples"] = str(metadata["ontology-info"]["triples"])
    info["accessed"] = metadata["http-data"]["accessed"]
    return info
