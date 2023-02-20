import requests


# url to get all vocabs and their resource
lovOntologiesURL = "https://lov.linkeddata.es/dataset/lov/api/v2/vocabulary/list"

# prefix.cc complete urls
prefixccURLs = "http://prefix.cc/context"


def getLovUrls():
    req = requests.get(lovOntologiesURL)
    json_data = req.json()
    return [dataObj["uri"] for dataObj in json_data]


def getPrefixURLs():
    req = requests.get(prefixccURLs)
    json_data = req.json()
    prefixOntoDict = json_data["@context"]
    return [prefixOntoDict[prefix] for prefix in prefixOntoDict]
