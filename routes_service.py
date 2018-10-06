import requests
import os
import cherrypy
import json


class Root(object):

    routes_url = 'https://marsruti.lv/rigasmikroautobusi/bbus/routes.txt'

    @staticmethod
    def get_stops():
        os.environ['NO_PROXY'] = '127.0.0.1'
        return json.loads(requests.get('http://127.0.0.1:9002').content.decode('utf-8'))

    def get_routes(self):
        if 'routes.json' in os.listdir('static') and not self.debug:
            # if parsed file exists in system, just use that one
            with open('static/routes.json', mode='r', encoding='utf-8') as file:
                return json.loads(file.read())
        else:
            # otherwise need to re-parse the data
            routes = self.convert_routes()
            with open('static/routes.json', mode='w+', encoding='utf-8') as file:
                file.write(json.dumps(routes, sort_keys=True, indent=4))
            return routes

    key_translation = {'routenum': 'route_number',
                       'routename': 'route_name',
                       'routestops': 'route_stops',
                       'routetype': 'route_type'}

    def convert_routes(self):
        if 'routes.txt' not in os.listdir('static'):
            # if stop data is not present locally, GET it from online
            response = requests.get(self.routes_url)
            with open('static/routes.txt', mode='w+', encoding='utf-8-sig') as file:
                file.write(response.content.decode('utf-8-sig'))

        with open('static/routes.txt', mode='r', encoding='utf-8-sig') as file:
            raw_data = file.read()

        split_data = raw_data.split('\n')
        header_row = split_data[0].lower().split(';')

        routes = []

        split_data = split_data[2:]

        stops = self.get_stops()

        for row in range(0, len(split_data)):
            columns = split_data[row].split(';')
            route = {}
            for column in range(0, len(columns)):

                if header_row[column] not in list(self.key_translation.keys()):
                    continue

                key = self.key_translation[header_row[column]]

                if key in ['route_stops']:
                    value = [i for i in columns[column].split(',') if len(i) > 0]
                else:
                    value = columns[column]

                route[key] = value

            if len(route) > 1 and len(route['route_type']) > 0:
                route['departure_times'] = split_data[row + 1]

                if len(route['route_number']) == 0:
                    route['route_number'] = routes[-1]['route_number']

                route['route_stops'] = [stops[route_stop] for route_stop in route['route_stops']]

                routes.append(route)

        return routes

    def __init__(self):
        self.debug = False
        pass

    @cherrypy.expose
    def index(self, route_number=None, route_type=None):
        routes = self.get_routes()

        if route_number is not None and route_type is not None:
            routes = [route for route in routes if (route['route_number'] == str(route_number) and
                                                    route['route_type'] == route_type)][0]

        routes = json.dumps(routes, sort_keys=True, indent=4)

        if 'routes.json' not in os.listdir('debug'):
            with open('debug/routes.json', mode='w+', encoding='utf-8') as file:
                file.write(routes)

        return routes


if __name__ == '__main__':
    config = {"/": {"tools.gzip.on": True,
                    "tools.gzip.mime_types": ["text/html", "text/plain", "text/javascript",
                                              "text/css", "application/javascript"]},
              "global": {"server.socket_host": "127.0.0.1",
                         "server.socket_port": 9003,
                         "server.thread_pool": 8}}

    # uncomment if running non-debug mode
    # config['global']['environment'] = 'production'

    cherrypy.quickstart(Root(), '/', config)
