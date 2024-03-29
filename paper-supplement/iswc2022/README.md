# ISWC 2022 "Reproducibility crisis analysis" provenance information

## Outage Measurement

- [Table of all outages](https://docs.google.com/spreadsheets/d/1bL0cnzxPP2y46Z-byf56oHNwREnid1cG0affctbD9fI/edit#gid=281687190)
- [Outage per crawl](https://docs.google.com/spreadsheets/d/1bL0cnzxPP2y46Z-byf56oHNwREnid1cG0affctbD9fI/edit#gid=694221323)
- [Outage per ontology](https://docs.google.com/spreadsheets/d/1bL0cnzxPP2y46Z-byf56oHNwREnid1cG0affctbD9fI/edit#gid=1207680809)
- [Evaluation functions for generating the data](/iswc2022/archivo_data/iswc_eval.py)

## Archivo Source Evaluation
- [Ontology by source and addition](https://databus.dbpedia.org/ontologies/archivo-indices/ontologies/2021.11.21-220000/ontologies_type=official.csv)

## LOD a lot term evaluation

- [LOD-a-lot HDT file download](http://lod-a-lot.lod.labs.vu.nl/data/LOD_a_lot_v1.hdt)
- Queries/Commands to analyze LOD-a-lot
  - property usage with jena-hdt sparql
   
    > bash bin/hdtsparql.sh LOD_a_lot_v1.hdt "$(cat query.sparql)"

    - cat query.sparql

            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?pred (COUNT(*) AS ?count) WHERE {
                ?sub ?pred ?obj .
            }
            GROUP BY ?pred
            order by desc(?count)
   
  - class usage with hdt-cpp
    > hdtSearch -q "? http://www.w3.org/1999/02/22-rdf-syntax-ns#type ?" /data/LOD_a_lot_v1.hdt  
    |  awk 'BEGIN { OFS = ","} {count[$3]++} END{for (i in count) print i,count[i]}' > c-distrib.csv
- List of terms from LOD-a-lot [properties](https://x.tools.dbpedia.org/archivo/hdt-java/hdt-jena/p-distrib.csv) [classes](https://x.tools.dbpedia.org/archivo/hdt-java/hdt-jena/c-distrib.tsv)
- [term analysis script](https://github.dev/dbpedia/archivo/blob/3bce0f9034dd06a99baae3522e1e41538b4608cf/eswc2021/analyze.sh)
- final filtered list of terms [classes](https://x.tools.dbpedia.org/archivo/hdt-java/hdt-jena/c-distrib-min10.tsv) [properties](https://x.tools.dbpedia.org/archivo/hdt-java/hdt-jena/p-distrib-min10.csv)

- Archivo LOD Ontology Coverage Analysis File Collection 
https://databus.dbpedia.org/ontologies/collections/archivo-reproducibility-analysis/ 
- [list of covered classes archivo](https://docs.google.com/spreadsheets/d/1tv_RZZwhgEc6vv1WPbAowyf6BMxxKbN-QtVYrsQ1Oc4/edit#gid=1761364766)
- [list of covered properties archivo](https://docs.google.com/spreadsheets/d/1tv_RZZwhgEc6vv1WPbAowyf6BMxxKbN-QtVYrsQ1Oc4/edit#gid=1761364766)
- [list of covered classes LOV](https://docs.google.com/spreadsheets/d/1tv_RZZwhgEc6vv1WPbAowyf6BMxxKbN-QtVYrsQ1Oc4/edit#gid=1418696249)
- [list of covered properties LOV](https://docs.google.com/spreadsheets/d/1tv_RZZwhgEc6vv1WPbAowyf6BMxxKbN-QtVYrsQ1Oc4/edit#gid=33490866)
- The queries used to retrieve the classes/properties can be found [here](queries)

## Unknown Terms of Archivo 

The data can be found [here](unknown_terms_crawl/term_count_reason_mapping.csv) and contains the following
* A table with mappings from terms to occurrence count in LOD cloud to the reason for not being able to be added to Archivo
* A json file with mappings from term to reason for not being added
* the script used to generate the stats
