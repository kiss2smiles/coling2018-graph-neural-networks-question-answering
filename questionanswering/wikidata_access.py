import nltk
from SPARQLWrapper import SPARQLWrapper, JSON
import logging


logging.basicConfig(level=logging.DEBUG)
sparql = SPARQLWrapper("http://knowledgebase:8890/sparql")
sparql.setReturnFormat(JSON)
sparql.setMethod("GET")
sparql.setTimeout(40)

sparql_prefix = """
        PREFIX e:<http://www.wikidata.org/entity/>
        PREFIX rdfs:<http://www.w3.org/2000/01/rdf-schema#>
        PREFIX skos:<http://www.w3.org/2004/02/skos/core#>
        """
sparql_select = """
        SELECT DISTINCT %queryvariables% WHERE
        """
sparql_relation = {
    "direct":"{GRAPH <http://wikidata.org/statements> { ?e1 ?p [ ?rd ?e2 ] }}",

    "reverse":"{GRAPH <http://wikidata.org/statements> { ?e2 ?p [ ?rr ?e1 ] }}",

    "v-structure":"{GRAPH <http://wikidata.org/statements> { _:m ?p ?e2. _:m ?rv ?e1. }}",
}
sparql_relation_complex = """
        {
        {GRAPH <http://wikidata.org/statements> { ?e1 ?p [ ?rd ?e2 ] }}
        UNION
        {GRAPH <http://wikidata.org/statements> { ?e2 ?p [ ?rr ?e1 ] }}
        UNION
        {GRAPH <http://wikidata.org/statements> { _:m ?p ?e2. _:m ?rv ?e1. }}}
        """

sparql_entity_label = """
        {{GRAPH <http://wikidata.org/terms> { ?e2 rdfs:label "%labelright%"@en  }}
        UNION
        {GRAPH <http://wikidata.org/terms> { ?e2 skos:altLabel "%labelright%"@en  }}
        }
        """

sparql_entity_abstract = "[ _:s [ e:P131v ?e2]]"


def graph_to_query(g, return_var_values = False):
    query = sparql_prefix
    variables = []
    query += sparql_select
    query += "{"
    for i, edge in enumerate(g.get('edgeSet', [])):
        if 'type' in edge:
            sparql_relation_inst = sparql_relation[edge['type']]
        else:
            sparql_relation_inst = sparql_relation_complex

        if 'kbID' in edge:
            sparql_relation_inst = re.sub(r"\?r[drv]", "e:" + edge['kbID'], sparql_relation_inst)
        else:
            sparql_relation_inst = sparql_relation_inst.replace("?r", "?r" + str(i))
            #             variables.extend(["?r{}".format(i), "?r{}r".format(i), "?r{}v".format(i) ])
            variables.extend(["?r{}{}".format(i, t[0]) for t in sparql_relation] if 'type' not in edge else ["?r{}{}".format(i, edge['type'][0])])

        sparql_relation_inst = sparql_relation_inst.replace("?p", "?p" + str(i))

        if 'hopUp' in edge:
            sparql_relation_inst = sparql_relation_inst.replace("?e2", sparql_entity_abstract)

        if 'rightkbID' in edge:
            sparql_relation_inst = sparql_relation_inst.replace("?e2", "e:" + edge['rightkbID'])
        else:
            sparql_relation_inst = sparql_relation_inst.replace("?e2", "?e2" + str(i))
            right_label =  " ".join([g['tokens'][i] for i in edge['right']]).title()
            sparql_entity_label_inst = sparql_entity_label.replace("?e2", "?e2" + str(i))
            sparql_entity_label_inst = sparql_entity_label_inst.replace("%labelright%", right_label)
            variables.append("?e2" + str(i))
            query += sparql_entity_label_inst
        sparql_relation_inst = sparql_relation_inst.replace("_:m", "_:m" + str(i))
        sparql_relation_inst = sparql_relation_inst.replace("_:s", "_:s" + str(i))

        query += sparql_relation_inst

    if return_var_values:
        variables.append("?e1")
    query += "}"
    query = query.replace("%queryvariables%", " ".join(variables))
    return query


def query_wikidata(query):
    sparql.setQuery(query)
    try:
        results = sparql.query().convert()
    except Exception as inst:
        logging.debug(inst)
        return []
    if len(results["results"]["bindings"]) > 0:
        results = results["results"]["bindings"]
        results = [r for r in results if all(r[b]['value'].startswith("http://www.wikidata.org/entity/") for b in r)]
        results = [{b:r[b]['value'].replace("http://www.wikidata.org/entity/","") for b in r} for r in results  ]
        return results
    else:
        logging.debug(results)
        return []


def load_entity_map(path_to_map):
    with open(path_to_map) as f:
        return_map = [l.strip().split("\t") for l in f.readlines()]
    return_map = nltk.Index({(t[1], t[0]) for t in return_map})
    return return_map

entity_map = load_entity_map("../data/" + "entity_map.tsv")


def map_query_results(query_results):
    answers = [r['e1'] for r in query_results]
    answers = [e.lower() for a in answers for e in entity_map.get(a, [a])]
