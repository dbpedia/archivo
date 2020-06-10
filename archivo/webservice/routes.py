from webservice import app
from webservice import localPath
from flask import render_template, flash, redirect
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired
import os
from utils.validation import TestSuite
import crawlURIs
from utils import ontoFiles
from utils import archivoConfig
#from utils import ontoFiles

ontoIndex = ontoFiles.loadIndexJsonFromFile(archivoConfig.ontoIndexPath)
fallout = ontoFiles.loadFalloutIndexFromFile(archivoConfig.falloutIndexPath)

archivoPath = os.path.split(app.instance_path)[0]
shaclPath = os.path.join(archivoPath, "shacl")
testingSuite = TestSuite(shaclPath)

class SuggestionForm(FlaskForm):
    suggestUrl = StringField(label="Suggest URL", validators=[DataRequired()])
    submit = SubmitField(label="Suggest")



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