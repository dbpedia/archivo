from typing import Dict, Optional, List

from querying import query_templates
from crawling import discovery
from webservice import app, db
from webservice.dbModels import (
    OfficialOntology,
    DevelopOntology,
    Fallout,
    Version,
    Ontology,
)
from flask import (
    render_template,
    flash,
    redirect,
    request,
    abort,
    jsonify,
    send_from_directory,
    Response,
    make_response,
)
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField
from wtforms import validators
import os
from utils.validation import TestSuite
from utils import archivo_config, string_tools, database_utils
from querying import query_databus, graph_handling
from flask_accept import accept, accept_fallback
from urllib.parse import quote, unquote
from utils.archivoLogs import webservice_logger
from urllib.error import HTTPError, URLError
import json
import html
from flask_cors import cross_origin

# from flask_sqlalchemy import sqlalchemy as sa
import sqlalchemy
from sqlalchemy.orm import aliased
import io
import csv

from models.user_interaction import check_is_nir_based_on_log, LogLevel, ProcessStepLog

# small hack for the correct path
archivoPath = os.path.split(os.path.dirname(os.path.realpath(__file__)))[0]


class SuggestionForm(FlaskForm):
    suggestUrl = StringField(
        label="Suggest URL", validators=[validators.DataRequired()]
    )
    submit = SubmitField(label="Suggest")


class InfoForm(FlaskForm):
    uris = SelectField(
        "Enter a URI",
        choices=[("", "")]
        + [(ont.uri, ont.uri) for ont in db.session.query(OfficialOntology).all()],
        validators=[validators.InputRequired()],
    )
    submit = SubmitField(label="Get Info")


@app.route("/add", methods=["GET", "POST"])
def suggest_ontology():
    form = SuggestionForm()
    all_ontology_uris = [ont.uri for ont in db.session.query(Ontology.uri).all()]

    suggested_uri = None

    post_request = False
    if form.validate_on_submit():
        suggested_uri = form.suggestUrl.data.strip()
    elif request.method == "POST":
        suggested_uri = request.form.get("suggestUrl", None)
        post_request = True

    if suggested_uri is not None:
        uri = suggested_uri
        output: List[ProcessStepLog] = []
        testingSuite = TestSuite()
        flash("Suggested URL {} for Archivo".format(form.suggestUrl.data))
        archivo_version = discovery.discover_new_uri(
            uri=uri,
            vocab_uri_cache=all_ontology_uris,
            source="user-suggestion",
            test_suite=testingSuite,
            logger=webservice_logger,
            process_log=output,
        )
        if archivo_version:
            dev_version = archivo_version.handle_dev_version()
            dbOnt, dbVersion = database_utils.get_database_entries(archivo_version)
            if dev_version:
                dev_ont, dev_version = database_utils.get_database_entries(dev_version)
                db.session.add(dev_ont)
                db.session.add(dev_version)
                dbOnt.devel = dev_ont.uri
            db.session.add(dbOnt)
            db.session.add(dbVersion)
            db.session.commit()
        elif check_is_nir_based_on_log(output):
            fallout = Fallout(
                uri=uri,
                source="user-suggestion",
                inArchivo=False,
                error=json.dumps([step.to_dict() for step in output]),
            )

            db.session.add(fallout)
            db.session.commit()
        # Adding info about the process
        if archivo_version:
            report_heading = "The Ontology has been accepted and added to Archivo!"
            main_comment = f"Check out this <a href=/info?o={quote(archivo_version.nir)}>page</a> for the overview over the suggested ontology!"
        elif not archivo_version and output[-1].status == LogLevel.INFO:
            report_heading = "The Ontology is already part of Archivo!"
            main_comment = output[-1].message
        else:
            report_heading = "The Ontology has been rejected!"
            main_comment = "Check out the log below for the reason. Click on the boxes for further details!"
        if post_request:
            return jsonify(output)
        else:
            return render_template(
                "add.html",
                report_heading=report_heading,
                main_comment=main_comment,
                process_steps=output,
                form=form,
                title="Archivo - Suggest Ontology",
            )
    return render_template(
        "add.html", process_steps=None, form=form, title="Archivo - Suggest Ontology"
    )


def build_correct_access_info(
    ontology_uri: str, crawling_status: Optional[bool]
) -> Dict:

    if crawling_status:
        return {"status": crawling_status, "message": ""}
    elif crawling_status is None:
        return {
            "status": True,
            "message": "No database entry -> no crawling happened",
        }
    else:
        latestFallout = (
            db.session.query(Fallout)
            .filter_by(ontology=ontology_uri)
            .order_by(Fallout.date.desc())
            .first()
        )
        return {
            "status": crawling_status,
            "message": latestFallout.error,
        }


@app.route("/info/", methods=["GET", "POST"])
@app.route("/info", methods=["GET", "POST"])
@accept("text/html")
def ontology_info_page():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    ontoUri = unquote(ontoUri)
    isDev = True if "dev" in args else False
    form = InfoForm()
    all_ontologies = [ont.uri for ont in db.session.query(OfficialOntology).all()]
    if form.validate_on_submit():
        uri = form.uris.data.strip()
        return redirect(f"/info?o={uri}")
    if ontoUri == "":
        return render_template(
            "info.html",
            general_info={},
            form=form,
            title="Archivo - Ontology Info",
        )
    else:
        foundUri = string_tools.get_uri_from_index(ontoUri, all_ontologies)
        if foundUri is None:
            abort(code=404)
        ont = db.session.query(OfficialOntology).filter_by(uri=foundUri).first()
        general_info = {"hasDev": True if ont.devel is not None else False}
        group, artifact = string_tools.generate_databus_identifier_from_uri(
            foundUri, dev=isDev
        )
        try:
            artifact_info = query_databus.get_info_for_artifact(group, artifact)
            print(artifact_info)
        except HTTPError as e:
            general_info[
                "message"
            ] = f"There seems to be a problem with the databus, please try it again later! {str(e)}"
            return render_template(
                "info.html",
                general_info=general_info,
                form=form,
                title=f"Archivo - Info about {foundUri}",
            )
        except IndexError:
            general_info["message"] = (
                f"It seems there is no Databus artifact for {foundUri}! Please report "
                f"this issue at the github page!"
            )
            return render_template(
                "info.html",
                general_info=general_info,
                form=form,
                title=f"Archivo - Info about {foundUri}",
            )
        else:
            if isDev:
                ont = ont.devel
                general_info["sourceURI"] = ont.uri
            general_info["source"] = ont.source
            general_info["isDev"] = isDev
            general_info["achievement"] = ont.accessDate
            general_info["title"] = artifact_info.title
            general_info["comment"] = artifact_info.description
            general_info[
                "databusArtifact"
            ] = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
            general_info["nir"] = {"regular": foundUri, "encoded": quote(foundUri)}
            # check latest crawling status
            general_info["access"] = build_correct_access_info(
                ont.uri, ont.crawling_status
            )

            # there is a type error, but it is ok since its only gets displayed
            for v_info in artifact_info.version_infos:
                # i know this breaks typing but it is only for the prettier star representation on the webpage
                v_info.stars = string_tools.generate_star_string(v_info.stars)
            artifact_info.version_infos = sorted(
                artifact_info.version_infos, key=lambda v: v.version.label, reverse=True
            )
            return render_template(
                "info.html",
                artifact_info=artifact_info,
                general_info=general_info,
                form=form,
                title=f"Archivo - Info about {artifact_info.title}",
            )


@ontology_info_page.support("text/turtle")
def turtleInfo():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    ontoUri = unquote(ontoUri)
    if not string_tools.get_uri_from_index(
        ontoUri, [ont.uri for ont in db.session.query(Ontology).all()]
    ):
        abort(404)
    return redirect(get_info_as_rdf(ontoUri, "text/turtle"), code=307)


@ontology_info_page.support("application/rdf+xml")
def rdfxmlInfo():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    ontoUri = unquote(ontoUri)
    if not string_tools.get_uri_from_index(
        ontoUri, [ont.uri for ont in db.session.query(Ontology).all()]
    ):
        abort(404)
    return redirect(get_info_as_rdf(ontoUri, "application/rdf+xml"), code=307)


@ontology_info_page.support("application/n-triples")
def ntriplesInfo():
    args = request.args
    ontoUri = args["o"] if "o" in args else ""
    ontoUri = unquote(ontoUri)
    if not string_tools.get_uri_from_index(
        ontoUri, [ont.uri for ont in db.session.query(Ontology).all()]
    ):
        abort(status=404)
    return redirect(get_info_as_rdf(ontoUri, "application/n-triples"), code=307)


@app.route("/home", methods=["GET"])
@app.route("/", methods=["GET"])
def handle_root():
    return redirect("/list")


@app.route("/list", methods=["GET"])
def onto_list():
    args = request.args
    isDev = True if "dev" in args else False
    if isDev:
        ontoType = DevelopOntology
    else:
        ontoType = OfficialOntology

    ontos = retrieve_list_from_database(ontoType)

    return render_template(
        "list.html",
        isDev=isDev,
        Ontologies=ontos,
        ontoNumber=len(ontos),
        graphJSON=get_star_stats(),
        title="Archivo - Ontology Archive",
    )


def get_info_as_rdf(ontology_url: str, mime_type: str):
    group, artifact = string_tools.generate_databus_identifier_from_uri(ontology_url)
    databus_artifact = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
    query_string = query_templates.constrict_info_graph_template.safe_substitute(
        ARTIFACT=databus_artifact
    )
    encodedString = quote(query_string, safe="&=")
    return f"https://databus.dbpedia.org/repo/sparql?default-graph-uri=&query={encodedString}&format={mime_type}&timeout=0&debug=on"


@app.route("/sys/licenses")
def licenses_page():
    return render_template("licenses.html", title="Archivo - Licenses")


@app.route("/download", methods=["GET"])
@accept_fallback
@cross_origin()
def download_ontology():
    args = request.args
    ontoUri = args.get("o", "")
    rdfFormat = args.get("f", "owl")
    version = args.get("v", None)
    ontoUri = unquote(ontoUri)
    scheme = getCorrectScheme(request.headers.get("X-Forwarded-Proto"))
    isDev = True if "dev" in args else False
    return download_handling(
        uri=ontoUri,
        is_dev=isDev,
        version=version,
        rdf_format=rdfFormat,
        source_schema=scheme,
    )


@download_ontology.support("text/turtle")
def turtle_ont_download():
    args = request.args
    ontoUri = args.get("o", "")
    rdfFormat = args.get("f", "ttl")
    isDev = True if "dev" in args else False
    scheme = getCorrectScheme(request.headers.get("X-Forwarded-Proto"))
    version = args.get("v", None)
    return download_handling(
        uri=ontoUri,
        is_dev=isDev,
        version=version,
        rdf_format=rdfFormat,
        source_schema=scheme,
    )


@download_ontology.support("application/rdf+xml")
def rdfxml_ont_download():
    args = request.args
    ontoUri = args.get("o", "")
    rdfFormat = args.get("f", "owl")
    isDev = True if "dev" in args else False
    scheme = getCorrectScheme(request.headers.get("X-Forwarded-Proto"))
    version = args.get("v", None)
    return download_handling(
        uri=ontoUri,
        is_dev=isDev,
        version=version,
        rdf_format=rdfFormat,
        source_schema=scheme,
    )


@download_ontology.support("application/n-triples")
def ntriples_ont_download():
    args = request.args
    ontoUri = args.get("o", "")
    rdfFormat = args.get("f", "nt")
    version = args.get("v", None)
    scheme = getCorrectScheme(request.headers.get("X-Forwarded-Proto"))
    isDev = True if "dev" in args else False
    return download_handling(
        uri=ontoUri,
        is_dev=isDev,
        version=version,
        rdf_format=rdfFormat,
        source_schema=scheme,
    )


def getCorrectScheme(scheme):
    if scheme == "http" or scheme == "https":
        return scheme
    else:
        return "https"


def download_handling(
    uri, is_dev=False, version="", rdf_format="owl", source_schema="http"
):
    ontoUri = unquote(uri)
    foundURI = string_tools.get_uri_from_index(
        ontoUri, [ont.uri for ont in db.session.query(Ontology).all()]
    )
    if foundURI is None:
        abort(code=404)
    group, artifact = string_tools.generate_databus_identifier_from_uri(
        foundURI, dev=is_dev
    )
    try:
        downloadLink = query_databus.get_download_url(
            group, artifact, file_extension=rdf_format, version=version
        )
    except URLError as e:
        abort(
            500,
            f"There seems to be an error with the DBpedia Databus. Try again later. {str(e)}",
        )
    if downloadLink is not None:
        correctUrl = str(source_schema) + "://" + str(downloadLink.split("://")[1])
        correct_mimetype = get_mimetype_of_fileExt(rdf_format)
        resp = Response(  # type: ignore
            '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">\n'
            "<title>Redirecting...</title>\n"
            "<h1>Redirecting...</h1>\n"
            "<p>You should be redirected automatically to target URL: "
            f'<a href="{html.escape(correctUrl)}">{html.escape(correctUrl)}</a>. If'
            " not click the link.",
            status=307,
            mimetype=correct_mimetype,
        )
        resp.headers["Location"] = correctUrl
        return resp
    else:
        abort(code=404)


@app.route("/about")
def about():
    return render_template("about.html", title="Archivo - About Archivo")


@app.route("/api")
def api_page():
    return render_template("api.html", title="Archivo - Ontology Access")


@app.route("/shaclVisualisation")
def shacl_visualisation():
    args = request.args
    shaclURI = args["r"] if "r" in args else None
    if shaclURI is not None:
        g = graph_handling.get_graph_by_uri(shaclURI)
        try:
            results = graph_handling.interpret_shacl_graph(g)
            return render_template("shaclReport.html", report=results)
        except Exception:
            return render_template("shaclReport.html", report=None, link=shaclURI)
    else:
        return abort(code=404)


@app.route("/faq")
def faq():
    return render_template("faq.html", title="Archivo - Frequently Asked Questions")


def get_star_stats():
    with open(
        os.path.join(archivoPath, "stats", "stars_over_time.json"), "r"
    ) as json_file:
        json_data = json.load(json_file)
    return json.dumps(json_data)


@app.route("/rating")
def rating():
    return render_template("rating.html", title="Archivo - Ontology Rating")


@app.route("/onto")
def deliver_vocab():
    # get the mimetype, defaults to html
    mime = request.headers.get("Accept", "text/html")

    # checks for mimetype in accept header
    if "application/rdf+xml" in mime:
        return send_from_directory(app.config["VOCAB_FOLDER"], "vocab.rdf")
    elif "text/turtle" in mime:
        return send_from_directory(app.config["VOCAB_FOLDER"], "vocab.ttl")
    elif "application/ntriples" in mime:
        return send_from_directory(app.config["VOCAB_FOLDER"], "vocab.nt")
    else:
        return render_template("vocab.html")


@app.route("/falloutdl")
def fallout_download():
    fallout_not_in_archivo = (
        db.session.query(Fallout)
        .filter_by(inArchivo=False)
        .order_by(Fallout.date.desc())
        .all()
    )

    output = io.StringIO()
    writer: csv.writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)

    for falloutobj in fallout_not_in_archivo:
        writer.writerow(
            (falloutobj.uri, falloutobj.source, str(falloutobj.date), falloutobj.error)
        )

    resp = make_response(output.getvalue())
    resp.headers["Content-type"] = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=archivo-fallout.csv"

    return resp


def retrieve_list_from_database(onto_type: type[Ontology]):
    isDev = True if onto_type == DevelopOntology else False

    latest_version_fun = sqlalchemy.func.row_number().over(
        order_by=Version.version.desc(), partition_by=Version.ontology
    )
    latest_version_fun = latest_version_fun.label("latest_version_fun")

    version_query = db.session.query(Version, latest_version_fun)

    version_query = version_query.subquery(name="version_query", with_labels=True)

    version_alias = aliased(Version, alias=version_query)

    q = (
        db.session.query(onto_type, version_alias)
        .filter(version_alias.ontology == onto_type.uri)
        .filter(version_query.c.latest_version_fun == 1)
    )

    query_result = q.all()
    result_list = []
    last_ont_uri = ""

    for ont, version in query_result:

        group, artifact = string_tools.generate_databus_identifier_from_uri(ont.uri)
        databus_uri = f"https://databus.dbpedia.org/ontologies/{group}/{artifact}"
        infoURL = f"/info?o={ont.official}&dev" if isDev else f"/info?o={ont.uri}"

        # set the crawl error none means no crawl yet
        if ont.crawling_status or ont.crawling_status is None:
            crawlStatus = True
            crawlError = ""
        else:
            crawlStatus = False
            # crawlError = f"{str(fallout.date)} : {fallout.error}"
            crawlError = infoURL

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
            "addition_date": ont.accessDate.strftime("%Y.%m.%d-%H%M%S"),
            "databusURI": databus_uri,
            "source": ont.source,
            "triples": version.triples,
            "crawling": {"status": crawlStatus, "error": crawlError},
            "stars": string_tools.generate_star_string(version.stars),
            "semVersion": version.semanticVersion,
            "parsing": version.parsing,
            "minLicense": version.licenseI,
            "goodLicense": version.licenseII,
            "consistency": version.consistency,
            "lodeSeverity": version.lodeSeverity,
            "latestVersion": version.version.strftime("%Y.%m.%d-%H%M%S"),
        }
        result_list.append(result)
        last_ont_uri = ont.uri

    return result_list


def get_mimetype_of_fileExt(fileExt: str):
    if fileExt == "owl" or fileExt == "rdf":
        return "application/rdf+xml"
    elif fileExt == "ttl":
        return "text/turtle"
    elif fileExt == "nt":
        return "application/n-triples"
    else:
        return "text/plain"
