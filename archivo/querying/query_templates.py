from string import Template

general_purpose_prefixes = """PREFIX dataid: <http://dataid.dbpedia.org/ns/core#>
PREFIX dct:    <http://purl.org/dc/terms/>
PREFIX dcat:   <http://www.w3.org/ns/dcat#>
PREFIX db:     <https://databus.dbpedia.org/>
PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>
PREFIX dataid-cv: <http://dataid.dbpedia.org/ns/cv#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""

artifact_info_query = Template(
    general_purpose_prefixes
    + """
SELECT DISTINCT ?title ?comment ?versionURL ?version ?metafile ?minLicense ?goodLicense ?lode ?archivoCheck ?consistencyFile ?docuURL ?pylodeURL WHERE {
        VALUES ?art { <$artifact> } .
        ?dataset dataid:account db:ontologies .
        ?dataset dataid:artifact ?art .
        ?dataset dcat:distribution ?metaDst .
        ?metaDst dataid-cv:type 'meta'^^xsd:string .
        ?metaDst dcat:downloadURL ?metafile .
        ?dataset dcat:distribution ?shaclMinLicense .
        ?dataset dcat:distribution ?consistencyReport .
        ?consistencyReport dataid-cv:type 'pelletConsistency'^^xsd:string .
        ?consistencyReport dataid-cv:imports 'FULL'^^xsd:string .
        ?consistencyReport dcat:downloadURL ?consistencyFile .
        ?shaclMinLicense dataid-cv:type 'shaclReport'^^xsd:string .
        ?shaclMinLicense dataid-cv:validates 'minLicense'^^xsd:string .
        ?shaclMinLicense dcat:downloadURL ?minLicense .
        ?dataset dcat:distribution ?shaclGoodLicense .
        ?shaclGoodLicense dataid-cv:type 'shaclReport'^^xsd:string .
        ?shaclGoodLicense dataid-cv:validates 'goodLicense'^^xsd:string .
        ?shaclGoodLicense dcat:downloadURL ?goodLicense .
        ?dataset dcat:distribution ?shaclLode .
        ?shaclLode dataid-cv:type 'shaclReport'^^xsd:string .
        ?shaclLode dataid-cv:validates 'lodeMetadata'^^xsd:string .
        ?shaclLode dcat:downloadURL ?lode .
  	  
        OPTIONAL { ?dataset dcat:distribution ?docuDst .
                ?docuDst dataid-cv:type 'generatedDocu'^^xsd:string .
                ?docuDst dcat:downloadURL ?docuURL .
        }
        OPTIONAL { ?dataset dcat:distribution ?pylodeDocDst .
                ?pylodeDocDst dataid-cv:type 'pyLodeDoc'^^xsd:string .
                ?pylodeDocDst dcat:downloadURL ?pylodeURL .
        }
        OPTIONAL {
                    ?dataset dcat:distribution ?shaclArchivo .
                    ?shaclArchivo dataid-cv:type 'shaclReport'^^xsd:string .
                    ?shaclArchivo dataid-cv:validates 'archivoMetadata'^^xsd:string .
                    ?shaclArchivo dcat:downloadURL ?archivoCheck .
        }
            ?dataset dataid:version ?versionURL .
            ?dataset dct:hasVersion ?version . ?dataset dct:title ?title .
            ?dataset rdfs:comment ?comment .
      }
    """
)

nir_to_lates_versions_query = (
    general_purpose_prefixes
    + """SELECT DISTINCT ?art ?latestVersion ?ntFile ?metafile WHERE {
?dataset dataid:account db:ontologies .
?dataset dataid:artifact ?art .
?dataset dcat:distribution ?parsedDst .
?parsedDst dataid-cv:type 'parsed'^^xsd:string .
?parsedDst dataid:formatExtension 'nt'^^xsd:string .
?parsedDst dcat:downloadURL ?ntFile .
?dataset dcat:distribution ?metaDst .
?metaDst dataid-cv:type 'meta'^^xsd:string .
?metaDst dcat:downloadURL ?metafile .
?dataset dct:hasVersion ?latestVersion .
{
SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {
?dataset dataid:account db:ontologies .
?dataset dataid:artifact ?art .
?dataset dct:hasVersion ?v .
}
}
}
"""
)

get_last_index_template = Template(
    general_purpose_prefixes
    + """SELECT DISTINCT ?downloadURL WHERE {
VALUES ?art { <https://databus.dbpedia.org/ontologies/archivo-indices/ontologies> }
?dataset dataid:artifact ?art .
?dataset dct:hasVersion ?latestVersion .
?dataset dcat:distribution ?dst .
?dst dataid-cv:type '$indextype'^^xsd:string .
?dst dcat:downloadURL ?downloadURL .{
SELECT DISTINCT ?art (MAX(?v) as ?latestVersion) WHERE {
?dataset dataid:artifact ?art .
?dataset dct:hasVersion ?v .
}
}
}
"""
)


get_spo_file_template = Template(
    general_purpose_prefixes
    + """SELECT DISTINCT ?used ?generated {
      SERVICE <https://databus.dbpedia.org/repo/sparql> {
            ?dataset dct:publisher <https://yum-yab.github.io/webid.ttl#onto> .
            ?dataset dcat:distribution/dataid:file ?used .
                ?dataset dct:hasVersion ?vers .
                FILTER(str(?vers) > "$date")
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
