import re
import json
import requests
import logging
import datetime
import tokens as TOKENS
import external_apis
from time import time
from random import shuffle
from os.path import isfile
from urllib.parse import parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
from html import unescape

logging.basicConfig(
        filename="/var/log/api.log",
        level=logging.INFO,
        format='%(asctime)s\t%(message)s',
        )

def timestamp():
    return int(time())

data_dir = "data"

# with open(data_dir + "/presence.json") as f:
#     PRESENCE = json.load(f)


class API(BaseHTTPRequestHandler):
    ones = ['gewinnt', 'besiegt', 'wins', 'defeats', 'gewonnen', 'gewinne', 'gewinnen']
    twos = ['verliert', 'unterliegt', 'loses', 'lost', 'verloren', 'verliere']
    zeroes = ['remis', 'unentschieden', 'ties', 'tie']
    simus = ['test', 'wenn', 'hätte', 'gewönne', 'verlöre', 'würde']
    zwnj = '‌'
    table = {
            'author_link': 'https://github.com/L3viathan/schikanoeschen/blob/master/german.md',
            'author_name': 'Offizielle Turnierregeln',
            'author_icon': 'https://static.l3vi.de/book.png',
            'fallback': '<Ligatabelle>',
            'title': 'Tabelle',
            'thumb_url': 'https://static.l3vi.de/karten.png',
            }

    tokenizer = re.Scanner([
        (r'[a-z@/_-]+|[^\sa-z@/_-]+', lambda _, x: x),
        (r'\s+', None),
        ])
    state = {
            'zuhause': {}
            }

    def do_HEAD(self):
        self.send_headers(200)

    def do_GET(self):
        self.make_get_parameters()
        if self.path in (
                        '/status.json',
                        '/mood.json',
                        '/battery.json',
                        '/calendar.json',
                        '/schika.json',
                        '/location.json',
                        ):
            self.send_headers(200)
            with open(data_dir + self.path, 'rb') as f:
                self.wfile.write(f.read())
        elif self.path.startswith('/elo.json'):
            r_x = int(self.url_params[b'x'])
            r_y = int(self.url_params[b'y'])
            who = int(self.url_params[b'who'])
            k = int(self.url_params.get(b'k', 16))
            res = self.elo(r_x, r_y, who, k=k)
            if res is None:
                return self.send_headers(400)  # Bad Request
            r_x_, r_y_ = res
            d = {'x': r_x_, 'y': r_y_}
            self.respond_json(d)

        else:
            self.send_headers(400)  # Bad Request

    def send_headers(self, code):
        self.send_response(code)
        if code == 200:
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def respond_json(self, payload):
        self.send_headers(200)
        self.wfile.write(json.dumps(payload).encode())

    def ephemeral(self, message, **kwargs):
        self.respond_json(
                {
                    'response_type': 'ephemeral',
                    'text': message,
                    **kwargs
                    }
                )

    def attachment(self, hide_sender=False, fallback="<New message>", public=True, **kwargs):
        response_type = 'in_channel' if public else 'ephemeral'
        json_reply = {
                'response_type': response_type,
                'attachments': [{fallback: fallback, **kwargs}],
                }
        if hide_sender:
            self.send_headers(200)
            url = self.post_data['response_url']
            requests.post(url, json=json_reply)
        else:
            self.respond_json(json_reply)


    def in_channel(self, message, hide_sender=False, **kwargs):
        json_reply = {
                'response_type': 'in_channel',
                'text': message,
                **kwargs
                }
        if hide_sender:
            self.send_headers(200)
            url = self.post_data['response_url']
            requests.post(url, json=json_reply)
        else:
            self.respond_json(json_reply)

    @staticmethod
    def make_table(ranks):
        return "\n".join("{}: {}".format(k[:2] + API.zwnj + k[2:], ranks[k]['score'])
            for k in sorted(ranks, key=lambda x: ranks[x]['score'], reverse=True) if ranks[k].get('active') != False)

    @staticmethod
    def elo(r_x, r_y, who, k=16):
        if who == 2:
            S_x = 0
            S_y = 1
        elif who == 1:
            S_x = 1
            S_y = 0
        elif who == 0:
            S_x = 0.5
            S_y = 0.5
        else:
            return None

        R_x = 10**(r_x/400)
        R_y = 10**(r_y/400)

        E_x = R_x/(R_x+R_y)
        E_y = R_y/(R_x+R_y)

        r_x_ = round(r_x + k * (S_x-E_x))
        r_y_ = round(r_y + k * (S_y-E_y))
        return r_x_, r_y_

    def do_POST(self):
        self.make_post_parameters()

        if self.path == '/mood':
            mood = self.post_data.get(b'mood', b'').decode("utf-8", "ignore")
            if mood:
                d = {
                        "timestamp": timestamp(),
                        "mood": mood,
                        }
                with open(data_dir + '/mood.json', 'w') as f:
                    json.dump(d, f)
            return self.send_headers(204)  # No content

        elif self.path in ('/sleep_start', '/sleep_stop'):
            d = {
                    "timestamp": timestamp(),
                    "status": ('asleep' if self.path == '/sleep_start' else 'awake'),
                    }
            with open(data_dir + '/status.json', 'w') as f:
                json.dump(d, f)
            return self.send_headers(204)  # No content

        elif self.path == '/zuhause':
            API.state['zuhause'] = {}
            for person in self.post_data:
                API.state['zuhause'][person] = self.post_data[person].split(",")
            # for person in API.state['zuhause']:
            #     n = API.state['zuhause']
            #     if n == 1:
            #         del API.state['zuhause'][person]
            #     else:
            #         API.state['zuhause'][person] -= 1
            # for person in online.split(","):
            #     API.state['zuhause'][person] = 2  # we have patience
            return self.send_headers(204)  # No content

        elif self.path == '/slack':
            if self.post_data.get('token', None) != TOKENS.slack:
                return self.send_headers(403)  # Forbidden

            logging.info('Received slack command: ' + self.post_data.get('text', ''))
            user = '@' + self.post_data['user_name']

            text = (self.post_data.get('text', '').lower()
                    .replace(' ich', ' ' + user).replace(' mich', ' ' + user))
            tokens, _ = API.tokenizer.scan(text)

            if tokens[0] == 'schika':
                with open(data_dir + "/schika.json") as f:
                    ranks = json.load(f)
                players = [word for word in tokens if word in ranks]
                response = ''
                if len(players) == 2:
                    x = ranks[players[0]]['score']
                    y = ranks[players[1]]['score']
                    if any(w in tokens for w in API.ones):
                        x, y = self.elo(x, y, 1)
                    elif any(w in tokens for w in API.twos):
                        x, y = self.elo(x, y, 2)
                    elif any(w in tokens for w in API.zeroes):
                        x, y = self.elo(x, y, 0)
                    else:
                        return self.ephemeral('Ich habe dich nicht verstanden. Drücke dich klarer aus. (1)')

                    ranks[players[0]]['score'] = x
                    ranks[players[1]]['score'] = y

                    if all(w not in tokens for w in API.simus):
                        with open(data_dir + "/schika.json", 'w') as f:
                            json.dump(ranks, f)
                        return self.attachment(text=self.make_table(ranks), color='good', **API.table)

                    # simulation:
                    return self.attachment(text=self.make_table(ranks), color='warning', hide_sender=True, public=False, **API.table, footer='Simulation')

                elif tokens[1] == 'list':
                    return self.attachment(text=self.make_table(ranks), color='good', hide_sender=True, **API.table)

                elif tokens[1] == 'hide':
                    ranks[tokens[2]]['active'] = False
                    with open(data_dir + "/schika.json", 'w') as f:
                        json.dump(ranks, f)
                    return self.ephemeral('Ich habe {} aus der Tabelle entfernt'.format(tokens[2]))

                elif tokens[1] == 'unhide':
                    ranks[tokens[2]]['active'] = True
                    with open(data_dir + "/schika.json", 'w') as f:
                        json.dump(ranks, f)
                    return self.ephemeral('Ich habe {} in die Tabelle genommen'.format(tokens[2]))

                elif tokens[1] == 'set':
                    ranks[tokens[2]] = {'score': int(tokens[3]), 'active': True}
                    with open(data_dir + "/schika.json", 'w') as f:
                        json.dump(ranks, f)
                    return self.ephemeral('Punkte von {} auf {} gesetzt'.format(tokens[2], tokens[3]))

                elif tokens[1] == 'help':
                    return self.ephemeral('Befehle:\n/konga schika set <jemand> <punkte>\n'
                                        '/konga schika list\n'
                                        '/konga schika help\n')
                else:
                    return self.ephemeral('Ich habe dich nicht verstanden. Drücke dich klarer aus. (2)')
            elif tokens[0] == 'bell':
                return self.in_channel("Wuff!")
            # elif tokens[0] in ('da', 'weg'):
            #     for person in tokens[1:]:
            #         PRESENCE[person] = tokens[0] == 'da'
            #     with open(data_dir + "/presence.json", "w") as f:
            #         json.dump(PRESENCE, f)
            #     self.ephemeral("Noted.")
            elif tokens[0] in ('alle', 'ruf'):
                rest = text[4:]
                names = ", ".join(name for name in API.state['zuhause'] and name != user)
                self.in_channel('{}: Nachricht von {}: {}'.format(names, user, rest), hide_sender=True)
            elif tokens[0] == 'zuhause':
                # online = ', '.join(API.state['zuhause'])
                online = ', '.join('{} ({})'.format(
                    name,
                    ', '.join(host for host in API.state['zuhause'][name])
                    )
                    for name in API.state['zuhause']
                    )
                if online:
                    self.ephemeral(online)
                else:
                    self.ephemeral('Im Moment scheint niemand zuhause zu sein.')
            elif tokens[0] == 'say':
                rest = text[4:]
                self.in_channel(rest, hide_sender=True)
            elif tokens[0] == 'trivia':
                q = external_apis.trivia()
                answers = [*map(unescape, q["incorrect_answers"] + [q["correct_answer"]])]
                shuffle(answers)
                self.attachment(
                        title="Trivia, Kategorie {}".format(q["category"]),
                        text=unescape(q["question"]),
                        fields=[
                            {
                                "title": letter,
                                "value": answer,
                                "short": True,
                                }
                            for letter, answer
                            in zip("ABCD", answers)
                            ],
                        )
                API.state['answer'] = unescape(q["correct_answer"])
            elif tokens[0] == 'solve':
                self.in_channel("Die richtige Antwort war: {}".format(API.state["answer"]))

            elif tokens[0] == 'help':
                self.ephemeral('Verfügbare Befehle: schika, say, bell, da, weg, ruf, present, help')
            else:
                return self.ephemeral('Das Kommando {} wurde noch nicht implementiert. Frag @jonathan.'.format(tokens[0]))

        elif self.path == '/mensa.json':
            meal_name = self.post_data.get(b'meal', b'fakju').decode()
            meal = ''.join(filter(str.islower, meal_name))
            rating = int(self.post_data.get(b'rating', b'-1'))
            if not (0 <= rating <= 5) or meal == 'fakju':
                return self.send_headers(400)  # Bad Request
            if 'asta' in meal and 'ffet' in meal:
                meal = 'astaffet'  # Pastabuffet
            mealfile = "mensa/" + meal + ".json"

            if isfile(mealfile):
                with open(mealfile, encoding="latin-1") as f:
                    ratings = json.load(f)
            else:
                ratings = {
                        'stars':0,
                        'number':0,
                        'name': meal_name,
                        }

            if meal in ("uspargrndenentflltdasssensamstags","hristiimmelfahrteschlossen"):
                ratings['meta'] = True
            if rating==0:
                ratings['name'] = meal_name

            ratings['number'] += 1
            ratings['stars'] += rating

            with open(mealfile, 'w', encoding="latin-1") as f:
                json.dump(ratings, f)

            self.respond_json(ratings)

        elif self.path == '/phone':
            battery = self.post_data.get(b'battery', b'?').decode("utf-8", "ignore")
            calendar = self.post_data.get(b'event', b'').decode("utf-8", "ignore")
            lat = float(self.post_data.get(b'lat', 0))
            lon = float(self.post_data.get(b'lon', 0))
            logging.info('battery\t{}'.format(battery))
            logging.info('calendar\t{}'.format(calendar))
            logging.info('latlon\t{},{}'.format(lat,lon))
            t = timestamp()

            d = {
                    "timestamp": t,
                    "battery": battery,
                    }
            with open(data_dir + "/battery.json", "w") as f:
                json.dump(d, f)

            if calendar:
                if False and calendar.startswith("."):
                    d = {
                        "timestamp": t,
                        "calendar": calendar[1:],
                        }
                else:
                    d = {
                        "timestamp": t,
                        "calendar": "undisclosed",
                        }
            else:
                d = {
                    "timestamp": t,
                    "calendar": "",
                    }

            with open(data_dir + "/calendar.json", "w") as f:
                json.dump(d, f)

            if lat and lon:
                try:
                    r = requests.get("http://maps.googleapis.com/maps/api/geocode/json?latlng={},{}&sensor=true".format(lat, lon))
                    location = r.json()['results'][0]
                    d = {
                            'timestamp': t,
                            'address': location['formatted_address'],
                            'lat': lat,
                            'lon': lon,
                            'role': '',
                        }
                    with open(data_dir + "/location.json", "w") as f:
                        json.dump(d, f)
                except IndexError:
                    pass

            self.send_headers(204)  # No content

    def make_post_parameters(self):
        length = int(self.headers.get('Content-Length'))
        data = self.rfile.read(length)
        d = parse_qs(data.decode('utf-8'))
        self.post_data = {key: (value[0] if value else None) for key, value in d.items()}

    def make_get_parameters(self):
        if "?" not in self.path:
            self.url_params = {}
            return
        d = parse_qs(self.path.split("?", 1)[1].encode('ascii'))
        self.url_params = {key: (value[0] if value else None) for key, value in d.items()}

def run(server_class=HTTPServer, handler_class=BaseHTTPRequestHandler):
    server_address = ('', 5005)
    httpd = server_class(server_address, handler_class)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()

if __name__ == '__main__':
    run(HTTPServer, API)
