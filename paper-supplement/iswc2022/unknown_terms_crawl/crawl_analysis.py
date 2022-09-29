import re
import json
import csv
from urllib.parse import urldefrag
from typing import List, Set, Dict

new_validation_regex = re.compile(r"^\[.*\]:\[.*\]:Trying to validate (.*)$")

line_filter = re.compile(r"^\[.*\]:\[.*\]:(.*)$")

error_reasons = [
    "This Ontology is already in the Archivo index",
    "Archivo-Agent dbpedia-archivo-robot is not allowed",
    "Deployed the Ontology to the DBpedia Databus",
    "RDFlib couldn't parse the file",
    "Problem during validating",
    "ERROR: Malformed URI",
]

def load_term_count_mapping(filepath: str):
    
    result = {}
    with open(filepath) as f:
        reader = csv.reader(f)
    
        for row in reader:
            if row[0] in result: print(f"Multiple entries for {row[0]}")
            result[row[0]] = row[1]
    return result


def load_first_column_csv(filepath: str):
    result = []
    with open(filepath) as f:
        reader = csv.reader(f)
    
        for row in reader:
            result.append(row[0])
    return result



def read_logfile():

    data_mapping = {}

    current_uri = None

    current_data: List = []

    with open("./new_complete_crawl.log") as logfile:

        for line in logfile:
            if new_validation_regex.match(line) and len(current_data) == 0:
                match = new_validation_regex.match(line)
                assert match is not None
                current_uri = match.group(1)
                current_data = []
            elif (
                new_validation_regex.match(line)
                and len(current_data) > 0
                and "Robot allowed: True" not in current_data[-1]
            ):
                data_mapping[current_uri] = current_data

                current_data = []
                match = new_validation_regex.match(line)
                assert match is not None
                current_uri = match.group(1)

            elif current_uri is not None and line_filter.match(line):
                match = line_filter.match(line)
                assert match is not None
                current_data.append(match.group(1))
            else:

                try:
                    m = line_filter.match(line)
                    assert m is not None
                    current_data.append(m.group(1))
                except AssertionError:
                    pass


                pass

    return data_mapping


def parse_logfile(stopset: Set[str] = None):

    data_mapping = read_logfile()

    print(f"Finished grouping log: {len(data_mapping)} different URIs crawled...")

    count_by_reason: Dict = {}

    for _, loglist in data_mapping.items():

        reason = loglist[-1]

        for short_error in error_reasons:

            if short_error in reason:
                reason = short_error
                break

        count_by_reason[reason] = count_by_reason.get(reason, 0) + 1

    with open("result_data.json", "w+") as jsonfile:

        json.dump(data_mapping, jsonfile, indent=2)


    unified_term_reason_mapping = {}

    for term, reason_list in data_mapping.items():

        reason = reason_list[-1]

        for short_error in error_reasons:

            if short_error in reason:
                reason = short_error
                break
        
        unified_term_reason_mapping[term] = reason
    
    with open("unified_term_reasoning_mapping.json", "w+") as unified_file:

        json.dump(unified_term_reason_mapping, unified_file, indent=2)


    with open("reason_count.json", "w+") as jsonfile:

        json.dump(count_by_reason, jsonfile, indent=2)


def generate_term_count_reasoning_mapping(output_filepath: str, write_files: bool = False, stopset: Set[str] = None):

    if stopset is None: stopset = set()

    URIs_skipped: int = 0

    with open("unified_term_reasoning_mapping.json") as jsonfile:

        term_reason_mapping: Dict = json.load(jsonfile)

    LOD_class_terms = load_term_count_mapping("../scripts/c-distrib-min10.csv")
    # LOD_prop_terms = load_term_count_mapping("../scripts/p-distrib-min10.csv")

    # intersection_c_p = set(LOD_class_terms.keys()).intersection(set(LOD_prop_terms.keys()))
    # print(f"Intersection between classes and props: {len(intersection_c_p)}")

    # LOD_all_terms = {**LOD_class_terms, **LOD_prop_terms}
    LOD_all_terms = LOD_class_terms

    all_lod_terms_set = set(LOD_all_terms.keys())
    print(f"All LOD terms (deduplicated: {len(LOD_all_terms)})")

    not_in_archvio = all_lod_terms_set - stopset
    print(f"All URIs not in Archivo: {len(not_in_archvio)}")
    
    result_list: List = []

    for term in not_in_archvio:

        count = LOD_all_terms[term]
        # Skip terms in stoplist
        if term in stopset: 
            URIs_skipped += 1
            continue
        
        defrag_iri = urldefrag(term)[0]

        try:
            reason = term_reason_mapping[defrag_iri]
        except KeyError:
            print(f"No value for {defrag_iri}")
            reason = "No value found"
        

        result_list.append((term, count, reason))

    if write_files:

        with open(output_filepath, "w+") as resultfile:

            writer = csv.writer(resultfile)

            writer.writerows(result_list)
    
    print(f"URIs skipped: {URIs_skipped}")
    return result_list


def main():
    print("Loading data...")
    covered_by_archivo = load_first_column_csv("all_archivo_classes.csv")

    covered_by_archivo = set(covered_by_archivo)

    print("Reading the file and filter it...")

    term_count_reason_list = generate_term_count_reasoning_mapping("term_count_reason_mapping.csv", stopset=covered_by_archivo, write_files=True) 

    num_terms_not_in_archivo = len(term_count_reason_list)

    num_all_triples_not_in_archvio = sum([int(count) for _, count, _ in term_count_reason_list])

    all_reasons = set([x for _, _, x in term_count_reason_list])

    print("General Stats:")
    print(f"Terms not Covered by Archivo: {num_terms_not_in_archivo}")
    print(f"Triples not Covered by Archivo: {num_all_triples_not_in_archvio}\n\n")

    for reason in all_reasons:

        filtered_list = list(filter(lambda x: x[2] == reason, term_count_reason_list))

        num_terms_covered = len(filtered_list)

        num_triples_covered = sum([int(count) for _, count, _ in filtered_list])

        print(f"Stats for reason {reason}:")
        print(f"\tTerms: {num_terms_covered}")
        print(f"\tTerms %: {num_terms_covered / num_terms_not_in_archivo}")
        print(f"\tTriples: {num_triples_covered}")
        print(f"\tTriples / %: {num_triples_covered / num_all_triples_not_in_archvio}\n\n")

if __name__ == "__main__":
    parse_logfile()
    main()
