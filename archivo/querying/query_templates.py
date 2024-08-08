from string import Template
from utils import archivo_config

general_purpose_prefixes = """PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX dcat: <http://www.w3.org/ns/dcat#>
PREFIX db: <https://databus.dbpedia.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX dataid-cv: <https://dataid.dbpedia.org/databus-cv#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX databus: <https://dataid.dbpedia.org/databus#>\n
"""

artifact_info_query = Template(
    general_purpose_prefixes
    + """SELECT DISTINCT ?dataset ?version ?metafile ?shaclMinLicense ?shaclGoodLicense ?consistencyReport ?shaclLode ?lodeDocu ?pylodeDoc ?title ?abstract ?shaclArchivo WHERE {
  VALUES ?art { <$ARTIFACT> } .

  ?dataset dct:title ?title .
  ?dataset dct:abstract ?abstract .
  ?dataset databus:artifact ?art .
  ?dataset dct:hasVersion ?version .

  # metafile
  ?dataset dcat:distribution ?metadistrib. 
  ?metadistrib dataid-cv:type 'meta'.
  ?metadistrib databus:file ?metafile .

  # min license report
  ?dataset dcat:distribution ?minLicenseDistrib .
  ?minLicenseDistrib dataid-cv:type 'shaclReport' .
  ?minLicenseDistrib dataid-cv:validates 'minLicense' .
  ?minLicenseDistrib databus:file ?shaclMinLicense .

  # consistency report
  ?dataset dcat:distribution ?consistencyReportDistrib .
  ?consistencyReportDistrib dataid-cv:type 'pelletConsistency' .
  ?consistencyReportDistrib dataid-cv:imports 'FULL' .
  ?consistencyReportDistrib databus:file ?consistencyReport .

  # good license
  ?dataset dcat:distribution ?shaclGoodLicenseDistrib .
  ?shaclGoodLicenseDistrib dataid-cv:type 'shaclReport' .
  ?shaclGoodLicenseDistrib dataid-cv:validates 'goodLicense' .
  ?shaclGoodLicenseDistrib databus:file ?shaclGoodLicense .

  # lode shacl
  ?dataset dcat:distribution ?shaclLodeDistrib .
  ?shaclLodeDistrib dataid-cv:type 'shaclReport' .
  ?shaclLodeDistrib dataid-cv:validates 'lodeMetadata' .
  ?shaclLodeDistrib databus:file ?shaclLode .

  OPTIONAL {
    ?dataset dcat:distribution ?lodeDocuDistrib .
    ?lodeDocuDistrib dataid-cv:type 'generatedDocu' .
    ?lodeDocuDistrib databus:file ?lodeDocu .
  }

  OPTIONAL {
    ?dataset dcat:distribution ?pylodeDocDistrib .
    ?pylodeDocDistrib dataid-cv:type 'pyLodeDoc' .
    ?pylodeDocDistrib databus:file ?pylodeDoc .
  }

  OPTIONAL {
    ?dataset dcat:distribution ?shaclArchivoDistrib .
    ?shaclArchivoDistrib dataid-cv:type 'shaclReport'^^xsd:string .
    ?shaclArchivoDistrib dataid-cv:validates 'archivoMetadata'^^xsd:string .
    ?shaclArchivoDistrib databus:file ?shaclArchivo .
  }
}"""
)

nir_to_lates_versions_query = (
    general_purpose_prefixes
    + """SELECT DISTINCT ?art ?latestVersion ?ntFile ?metafile WHERE {
?dataset databus:artifact ?art .
?dataset dcat:distribution ?parsedDst .
?parsedDst dataid-cv:type 'parsed' .
?parsedDst databus:formatExtension 'nt'.
?parsedDst dcat:downloadURL ?ntFile .
?dataset dcat:distribution ?metaDst .
?metaDst dataid-cv:type 'meta' .
?metaDst dcat:downloadURL ?metafile .
?dataset dct:hasVersion ?latestVersion .
{
SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {
?dataset databus:artifact ?art .
?dataset dct:hasVersion ?v .
}
}
}
"""
)

get_last_index_template = Template(
  general_purpose_prefixes
  + f"""SELECT DISTINCT ?downloadURL WHERE {{
VALUES ?art {{ <{archivo_config.DATABUS_BASE}/{archivo_config.DATABUS_USER}/archivo-indices/ontologies> }}
?dataset databus:artifact ?art .
?dataset dct:hasVersion ?latestVersion .
?dataset dcat:distribution ?dst .
?dst dataid-cv:type '$INDEXTYPE' .
?dst dcat:downloadURL ?downloadURL .{{
SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {{
?dataset databus:artifact ?art .
?dataset dct:hasVersion ?v .
}}
}}
}}"""
)


get_spo_file_template = Template(
    general_purpose_prefixes
    + """SELECT DISTINCT ?used ?generated {
      SERVICE <$DATABUSEP> {
            ?dataset databus:account db:ontologies .
            ?dataset dcat:distribution/databus:file ?used .
                ?dataset dct:hasVersion ?vers .
                FILTER(str(?vers) > "$DATE")
      }
      ?mod prov:generated ?generated .
         ?mod a  <https://mods.tools.dbpedia.org/ns/rdf#SpoMod> .
      ?mod prov:used ?used .
}
"""
)

void_uris_query = (
    general_purpose_prefixes
    + """PREFIX void: <http://rdfs.org/ns/void#>
SELECT DISTINCT ?URI {
?mod prov:generated ?generated .
{ SELECT ?URI WHERE {
?generated void:propertyPartition [
void:property ?URI
] .
}
}
UNION
{ SELECT DISTINCT ?URI WHERE {
?generated void:classPartition [
void:class ?URI
] .
}
}
}
"""
)

constrict_info_graph_template = Template(
    general_purpose_prefixes
    + """
CONSTRUCT {?s ?p ?o . ?dist ?p2 ?o2 . }
{?s databus:artifact <$ARTIFACT>.
?s ?p ?o . ?s dcat:distribution ?dist . ?dist ?p2 ?o2 . }"""
)
