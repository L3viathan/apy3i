import requests

def get_articles(query, token):
    url = "https://content.guardianapis.com/search?api-key={key}&q={query}"
    r = requests.get(url.format(key=token, query=query.replace(" ", "+")))
    j = r.json()
    if j["response"]["status"] != "ok":
        return
    for article in j["response"]["results"]:
        yield article['webTitle'], article['webUrl']

def convert_currency(from_, to, amount):
    url = "http://api.fixer.io/latest?symbols={target}&base={source}"
    r = requests.get(url.format(source=from_, target=to))
    return r.json()["rates"][to] * amount

def trivia():
    url = "https://opentdb.com/api.php?amount=1&type=multiple"
    r = requests.get(url)
    return r.json()["results"][0]
