from webservice import app, db, dbModels
from flask import render_template, flash, redirect, request, abort
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField
from wtforms import validators
import os
from utils.validation import TestSuite
import crawlURIs
from utils import archivoConfig, queryDatabus, stringTools, inspectVocabs
import traceback
import sys
import requests
import markdown
from flask_accept import accept, accept_fallback
from urllib.parse import quote, unquote, urlparse
from utils.archivoLogs import webservice_logger
from datetime import datetime
import dbUtils
from urllib.error import HTTPError, URLError
import json

archivoPath = os.path.split(app.instance_path)[0]
testingSuite = TestSuite()


class SuggestionForm(FlaskForm):
    suggestUrl = StringField(
        label="Suggest URL", validators=[validators.DataRequired()]
    )
    submit = SubmitField(label="Suggest")


class InfoForm(FlaskForm):
    uris = SelectField(
        "Enter a URI",
        choices=[("", "")]
        + [
            (ont.uri, ont.uri)
            for ont in db.session.query(dbModels.OfficialOntology).all()
        ],
        validators=[validators.InputRequired()],
    )
    submit = SubmitField(label="Get Info")


@app.route("/add", methods=["GET", "POST"])
def addOntology():
    form = SuggestionForm()
    allOnts = [ont.uri for ont in db.session.query(dbModels.Ontology.uri).all()]
    if form.validate_on_submit():
        uri = form.suggestUrl.data.strip()
        output = []
        success, isNir, archivo_version = crawlURIs.handleNewUri(
            uri,
            allOnts,
            archivoConfig.localPath,
            "user-suggestion",
            False,
            testSuite=testingSuite,
            logger=webservice_logger,
            user_output=output,
        )
        if success:
            succ, dev_message, dev_version = archivo_version.handleTrackThis()
            dbOnt, dbVersion = dbUtils.getDatabaseEntry(archivo_version)
            if succ:
                dev_ont, dev_version = dbUtils.getDatabaseEntry(dev_version)
                db.session.add(dev_ont)
                db.session.add(dev_version)
                dbOnt.devel = dev_ont.uri
            db.session.add(dbOnt)
            db.session.add(dbVersion)
            db.session.commit()
        elif not success and isNir:
            fallout = dbModels.Fallout(
                uri=uri,
                source="user-suggestion",
                inArchivo=False,
                error="\n".join(map(str, output)),
            )
            db.session.add(fallout)
            db.session.commit()
        flash("Suggested URL {} for Archivo".format(form.suggestUrl.data))
        return render_template("add.html", process_steps=output, form=form)
    return render_template("add.html", process_steps=None, form=form)


@app.route("/info/", methods=["GET", "POST"])
@app.route("/info", methods=["GET", "POST"])
@accept("text/html")
def vocabInfo():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    ontoUri = unquote(ontoUri)
    isDev = True if "dev" in args else False
    form = InfoForm()
    allOntos = [ont.uri for ont in db.session.query(dbModels.OfficialOntology).all()]
    if form.validate_on_submit():
        uri = form.uris.data.strip()
        return redirect(f"/info?o={uri}")
    if ontoUri != "":
        foundUri = stringTools.get_uri_from_index(ontoUri, allOntos)
        if foundUri is None:
            abort(status=404)
        ont = (
            db.session.query(dbModels.OfficialOntology).filter_by(uri=foundUri).first()
        )
        general_info = {}
        general_info["hasDev"] = True if ont.devel is not None else False
        group, artifact = stringTools.generateGroupAndArtifactFromUri(
            foundUri, dev=isDev
        )
        try:
            title, comment, versions_info = queryDatabus.getInfoForArtifact(
                group, artifact
            )
        except HTTPError as e:
            general_info[
                "message"
            ] = f"There seems to be a problem with the databus, please try it again later! {str(e)}"
            return render_template("info.html", general_info=general_info, form=form)
        if isDev:
            ont = ont.devel
            general_info["sourceURI"] = ont.uri
        general_info["source"] = ont.source
        general_info["isDev"] = isDev
        general_info["archivement"] = ont.accessDate
        general_info["title"] = title
        general_info["comment"] = comment
        general_info[
            "databusArtifact"
        ] = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        general_info["nir"] = {"regular": foundUri, "encoded": quote(foundUri)}
        for v in versions_info:
            v["stars"] = stringTools.generateStarString(v["stars"])
        return render_template(
            "info.html",
            versions_info=sorted(
                versions_info, key=lambda d: d["version"]["label"], reverse=True
            ),
            general_info=general_info,
            form=form,
        )
    return render_template(
        "info.html", general_info={"message": "Enter an ontology URI"}, form=form
    )


@vocabInfo.support("text/turtle")
def turtleInfo():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    ontoUri = unquote(ontoUri)
    if not stringTools.get_uri_from_index(
        ontoUri, [ont.uri for ont in db.session.query(dbModels.Ontology).all()]
    ):
        abort(status=404)
    return redirect(getRDFInfoLink(ontoUri, "text/turtle"), code=307)


@vocabInfo.support("application/rdf+xml")
def rdfxmlInfo():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    ontoUri = unquote(ontoUri)
    if not stringTools.get_uri_from_index(
        ontoUri, [ont.uri for ont in db.session.query(dbModels.Ontology).all()]
    ):
        abort(status=404)
    return redirect(getRDFInfoLink(ontoUri, "application/rdf+xml"), code=307)


@vocabInfo.support("application/n-triples")
def ntriplesInfo():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    ontoUri = unquote(ontoUri)
    if not stringTools.get_uri_from_index(
        ontoUri, [ont.uri for ont in db.session.query(dbModels.Ontology).all()]
    ):
        abort(status=404)
    return redirect(getRDFInfoLink(ontoUri, "application/n-triples"), code=307)


@app.route("/list", methods=["GET"])
@app.route("/", methods=["GET"])
def onto_list():
    args = request.args
    isDev = True if "dev" in args else False
    if isDev:
        ontoType = dbModels.DevelopOntology
    else:
        ontoType = dbModels.OfficialOntology
    ontologies = db.session.query(ontoType).all()
    ontos = []
    for ont in ontologies:
        group, artifact = stringTools.generateGroupAndArtifactFromUri(ont.uri)
        databus_uri = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        v = (
            db.session.query(dbModels.Version)
            .filter_by(ontology=ont.uri)
            .order_by(dbModels.Version.version.desc())
            .first()
        )
        if v is None:
            webservice_logger.critical(f"Couldn't find any data for {ont.uri}")
            continue
        if ont.crawling_status or ont.crawling_status == None:
            crawlStatus = True
            crawlError = ""
        else:
            crawlStatus = False
            latestFallout = (
                db.session.query(dbModels.Fallout)
                .filter_by(ontology=ont.uri)
                .order_by(dbModels.Fallout.date.desc())
                .first()
            )
            crawlError = f"{str(latestFallout.date)} : {latestFallout.error}"

        infoURL = f"/info?o={ont.official}&dev" if isDev else f"/info?o={ont.uri}"
        downloadURL = (
            f"/download?o={quote(ont.official)}&dev"
            if isDev
            else f"/download?o={quote(ont.uri)}"
        )
        result = {
            "ontology": {
                "label": ont.title,
                "URL": ont.uri,
                "infoURL": infoURL,
                "downloadURL": downloadURL,
            },
            "databusURI": databus_uri,
            "source": ont.source,
            "triples": v.triples,
            "crawling": {"status": crawlStatus, "error": crawlError},
            "stars": stringTools.generateStarString(v.stars),
            "semVersion": v.semanticVersion,
            "parsing": v.parsing,
            "minLicense": v.licenseI,
            "goodLicense": v.licenseII,
            "consistency": v.consistency,
            "lodeSeverity": v.lodeSeverity,
            "latestVersion": v.version.strftime("%Y.%m.%d-%H%M%S"),
        }
        ontos.append(result)
    return render_template(
        "list.html",
        isDev=isDev,
        Ontologies=ontos,
        ontoNumber=len(ontos),
        graphJSON=get_star_stats(),
    )


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
    queryString = "\n".join(
        (
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
            "?s ?p ?o . ?s dcat:distribution ?dist . ?dist ?p2 ?o2 . }&format=%s&timeout=0&debug=on"
            % mimeType,
        )
    )
    encodedString = quote(queryString, safe="&=")
    return f"https://databus.dbpedia.org/repo/sparql?default-graph-uri=&query={encodedString}"


@app.route("/sys/licenses")
def licensesPage():
    return render_template("licenses.html")


@app.route("/download", methods=["GET"])
@accept_fallback
def downloadOntology():
    args = request.args
    ontoUri = args.get("o", "")
    rdfFormat = args.get("f", "owl")
    version = args.get("v", None)
    ontoUri = unquote(ontoUri)
    referrer = request.headers.get("Referer", request.url)
    scheme = getCorrectScheme(request.headers.get("X-Forwarded-Proto"))
    isDev = True if "dev" in args else False
    return downloadHandling(
        uri=ontoUri,
        isDev=isDev,
        version=version,
        rdfFormat=rdfFormat,
        sourceSchema=scheme,
    )


@downloadOntology.support("text/turtle")
def turtleDownload():
    args = request.args
    ontoUri = args.get("o", "")
    rdfFormat = args.get("f", "ttl")
    isDev = True if "dev" in args else False
    scheme = getCorrectScheme(request.headers.get("X-Forwarded-Proto"))
    referrer = request.headers.get("Referer", request.url)
    version = args.get("v", None)
    return downloadHandling(
        uri=ontoUri,
        isDev=isDev,
        version=version,
        rdfFormat=rdfFormat,
        sourceSchema=scheme,
    )


@downloadOntology.support("application/rdf+xml")
def rdfxmlDownload():
    args = request.args
    ontoUri = args.get("o", "")
    rdfFormat = args.get("f", "owl")
    isDev = True if "dev" in args else False
    scheme = getCorrectScheme(request.headers.get("X-Forwarded-Proto"))
    referrer = request.headers.get("Referer", request.url)
    version = args.get("v", None)
    return downloadHandling(
        uri=ontoUri,
        isDev=isDev,
        version=version,
        rdfFormat=rdfFormat,
        sourceSchema=scheme,
    )


@downloadOntology.support("application/n-triples")
def ntriplesDownload():
    args = request.args
    ontoUri = args.get("o", "")
    rdfFormat = args.get("f", "nt")
    version = args.get("v", None)
    scheme = getCorrectScheme(request.headers.get("X-Forwarded-Proto"))
    isDev = True if "dev" in args else False
    return downloadHandling(
        uri=ontoUri,
        isDev=isDev,
        version=version,
        rdfFormat=rdfFormat,
        sourceSchema=scheme,
    )


def getCorrectScheme(scheme):
    if scheme == "http" or scheme == "https":
        return scheme
    else:
        return "https"


def downloadHandling(
    uri, isDev=False, version="", rdfFormat="owl", sourceSchema="http"
):
    ontoUri = unquote(uri)
    foundURI = stringTools.get_uri_from_index(
        ontoUri, [ont.uri for ont in db.session.query(dbModels.Ontology).all()]
    )
    if foundURI == None:
        abort(status=404)
    group, artifact = stringTools.generateGroupAndArtifactFromUri(foundURI, dev=isDev)
    try:
        downloadLink = queryDatabus.getDownloadURL(
            group, artifact, fileExt=rdfFormat, version=version
        )
    except URLError as e:
        abort(
            500,
            f"There seems to be an error with the DBpedia Databus. Try again later. {str(e)}",
        )
    if downloadLink != None:
        correctUrl = str(sourceSchema) + "://" + str(downloadLink.split("://")[1])
        return redirect(correctUrl, code=307)
    else:
        abort(status=404)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/api")
def api_page():
    return render_template("api.html")


@app.route("/shaclVisualisation")
def shaclVisualisation():
    args = request.args
    shaclURI = args["r"] if "r" in args else None
    if shaclURI != None:
        g = inspectVocabs.getGraphOfVocabFile(shaclURI)
        results = inspectVocabs.interpretShaclGraph(g)
        return render_template("shaclReport.html", report=results)
    else:
        return abort(status=404)


@app.route("/faq")
def faq():
    return render_template("faq.html")


def get_star_stats():
    with open(
        os.path.join(archivoPath, "stats", "stars_over_time.json"), "r"
    ) as json_file:
        json_data = json.load(json_file)
    return json.dumps(json_data)


@app.route("/rating")
def rating():
    return render_template("rating.html")
