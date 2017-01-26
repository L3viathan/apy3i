import json
import requests
import logging
from time import time
import datetime
from os.path import isfile
from urllib.parse import parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(filename="/var/log/api.log", level=logging.INFO, format='%(asctime)s\t%(message)s')

with open(".slack-token") as f:
    TOKEN = f.read().strip()


def timestamp():
    return int(time())

data_dir = "data"

def elo(r_x, r_y, who):
    k = 16
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


class API(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/json")
        self.end_headers()

    def do_GET(self):
        self.make_get_parameters()
        if self.path in (
                        '/status.json',
                        '/mood.json',
                        '/battery.json',
                        '/calendar.json',
                        '/location.json',
                        ):
            self.send_response(200)
            self.send_header("Content-Type", "text/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with open(data_dir + self.path, 'rb') as f:
                self.wfile.write(f.read())
        elif self.path.startswith('/elo.json'):
            r_x = int(self.url_params[b'x'])
            r_y = int(self.url_params[b'y'])
            who = int(self.url_params[b'who'])
            res = elo(r_x, r_y, who)
            if res is None:
                self.send_response(403)
                self.end_headers()
                return
            r_x_, r_y_ = res
            d = {'x': r_x_, 'y': r_y_}
            self.send_response(200)
            self.send_header("Content-Type", "text/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(d).encode())

        else:
            self.send_response(400)  # Bad Request
            self.end_headers()

    def do_POST(self):
        self.make_post_parameters()

        if self.path == '/mood':
            mood = self.post_data.get(b'mood', b'').decode("utf-8", "ignore")
            if mood:
                d = {"timestamp": timestamp(), "mood": mood}
                with open(data_dir + '/mood.json', 'w') as f:
                    json.dump(d, f)
            self.send_response(204)  # No content
            self.end_headers()

        elif self.path in ('/sleep_start', '/sleep_stop'):
            d = {"timestamp": timestamp(), "status": ('asleep' if self.path == '/sleep_start' else 'awake')}
            with open(data_dir + '/status.json', 'w') as f:
                json.dump(d, f)
            self.send_response(204)  # No content
            self.end_headers()

        elif self.path == '/slack':
            print(TOKEN, self.post_data)
            if self.post_data.get('token', None) != TOKEN:
                self.send_response(403)  # Forbidden
                self.end_headers()
                return
            text = (self.post_data.get('text', '').lower()
                    .replace(' ich', ' @' + self.post_data['user_name']).split(' '))
            if text[0] == 'schika':
                ones = ['gewinnt', 'besiegt', 'wins', 'defeats', 'gewonnen', 'gewinne', 'gewinnen']
                twos = ['verliert', 'unterliegt', 'loses', 'lost', 'verloren', 'verliere']
                zeroes = ['Remis', 'Unentschieden', 'ties', 'tie']
                simus = ['test', 'wenn', 'hätte', 'gewönne', 'verlöre']
                with open(data_dir + "/schika.json") as f:
                    ranks = json.load(f)
                players = [word for word in text if word in ranks]
                response = ''
                zwnj = '‌'
                if len(players) == 2:
                    x = ranks[players[0]]
                    y = ranks[players[1]]
                    if any(w in text for w in ones):
                        x, y = elo(x, y, 1)
                    elif any(w in text for w in twos):
                        x, y = elo(x, y, 2)
                    elif any(w in text for w in zeroes):
                        x, y = elo(x, y, 0)
                    else:
                        response = None
                    if response is None:
                        response = {'response_type': 'ephemeral', 'text': 'Ich habe dich nicht verstanden. Drücke dich klarer aus.'}
                    else:
                        ranks[players[0]] = x
                        ranks[players[1]] = y
                        if all(w not in text for w in simus):
                            with open(data_dir + "/schika.json", 'w') as f:
                                json.dump(ranks, f)
                    foo = "\n".join("{}: {}".format(k[:2] + zwnj + k[2:], ranks[k]) for k in sorted(ranks, key=lambda x: ranks[x], reverse=True))
                    response = {'response_type': 'in_channel', 'text': "Neue Tabelle:", 'attachments': [{'text': foo}]}
                elif 'list' in text:
                    foo = "\n".join("{}: {}".format(k[:2] + zwnj + k[2:], ranks[k]) for k in sorted(ranks, key=lambda x: ranks[x], reverse=True))
                    response = {'response_type': 'in_channel', 'text': "Tabelle:", 'attachments': [{'text': foo}]}
                elif text[1] == 'set':
                    ranks[text[2]] = int(text[3])
                    with open(data_dir + "/schika.json", 'w') as f:
                        json.dump(ranks, f)
                    response = {'response_type': 'ephemeral', 'text': 'Punkte von {} auf {} gesetzt'.format(text[2], text[3])}

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())

        elif self.path == '/mensa.json':
            self.send_response(200)
            self.send_header("Content-Type", "text/json")
            self.end_headers()
            meal_name = self.post_data.get(b'meal', b'fakju').decode()
            meal = ''.join(filter(str.islower, meal_name))
            rating = int(self.post_data.get(b'rating', b'-1'))
            if not (0 <= rating <= 5) or meal == 'fakju':
                self.send_response(400)  # Bad Request
                self.end_headers()
                return
            if 'asta' in meal and 'ffet' in meal:
                meal = 'astaffet'  # Pastabuffet
            mealfile = "mensa/" + meal + ".json"

            if isfile(mealfile):
                with open(mealfile, encoding="latin-1") as f:
                    ratings = json.load(f)
            else:
                ratings = {'stars':0, 'number':0, 'name': meal_name}

            if meal in ("uspargrndenentflltdasssensamstags","hristiimmelfahrteschlossen"):
                ratings['meta'] = True
            if rating==0:
                ratings['name'] = meal_name

            ratings['number'] += 1
            ratings['stars'] += rating

            with open(mealfile, 'w', encoding="latin-1") as f:
                json.dump(ratings, f)

            self.wfile.write(json.dumps(ratings).encode())

        elif self.path == '/phone':
            print(self.post_data)
            battery = self.post_data.get(b'battery', b'?').decode("utf-8", "ignore")
            calendar = self.post_data.get(b'event', b'').decode("utf-8", "ignore")
            lat = float(self.post_data.get(b'lat', 0))
            lon = float(self.post_data.get(b'lon', 0))
            logging.info('battery\t{}'.format(battery))
            logging.info('calendar\t{}'.format(calendar))
            logging.info('latlon\t{},{}'.format(lat,lon))
            t = timestamp()

            d = {"timestamp": t, "battery": battery}
            with open(data_dir + "/battery.json", "w") as f:
                json.dump(d, f)

            if calendar:
                if False and calendar.startswith("."):
                    d = {"timestamp": t, "calendar": calendar[1:]}
                else:
                    d = {"timestamp": t, "calendar": "undisclosed"}
            else:
                d = {"timestamp": t, "calendar": ""}

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


            self.send_response(204)  # No content
            self.end_headers()

    def make_post_parameters(self):
        length = int(self.headers.get('Content-Length'))
        data = self.rfile.read(length)
        d = parse_qs(data.decode('utf-8'))#.encode('ascii'))
        #d = parse_qs(data.decode('utf-8').encode('ascii'))
        self.post_data = {key: (value[0] if value else None) for key, value in d.items()}

    def make_get_parameters(self):
        if "?" not in self.path:
            self.url_params = {}
            return
        #d = parse_qs(self.path.split("?", 1)[1].decode('utf-8').encode('ascii'))
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
