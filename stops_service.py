import requests
import os
import cherrypy
import json


class Root(object):

    stops_url = 'https://marsruti.lv/rigasmikroautobusi/bbus/stops.txt'

    @staticmethod
    def get_gtfs(file_name):
        with open('gtfs/{}.txt'.format(file_name), mode='r', encoding='utf-8') as file:
            return file.read()

    def get_stops(self):
        if 'stops.json' in os.listdir('static') and not self.debug:
            # if parsed file exists in system, just use that one
            with open('static/stops.json', mode='r', encoding='utf-8') as file:
                return file.read()
        else:
            # otherwise need to re-parse the data
            stop_data = self.convert_stops()
            with open('static/stops.json', mode='w+', encoding='utf-8') as file:
                file.write(stop_data)
                return stop_data

    def convert_stops(self):
        gtfs_raw_data = self.get_gtfs('stops')

        if 'stops.txt' not in os.listdir('static'):
            # if stop data is not present locally, GET it from online
            response = requests.get(self.stops_url)
            with open('static/stops.txt', mode='w+', encoding='utf-8-sig') as file:
                file.write(response.content.decode('utf-8-sig'))

        with open('static/stops.txt', mode='r', encoding='utf-8-sig') as file:
            raw_data = file.read()

        gtfs_lines = gtfs_raw_data.split('\n')
        gtfs_data = gtfs_lines[1:]
        gtfs_dict = {}

        for stop in gtfs_data:
            stop = stop.split(',')
            gtfs_dict[stop[0]] = stop[2].replace('"', '')

        split_data = raw_data.split('\n')
        header_row = split_data[0].lower().split(';')

        stops = {}

        for row in split_data[1:]:

            columns = row.split(';')
            stop = {}
            for column in range(0, len(columns)):

                # if header_row[column] == 'stops':
                #     stop[header_row[column]] = columns[column].split(',')
                # el
                if header_row[column] in ('lat', 'lng'):
                    stop[header_row[column]] = int(columns[column]) / 100000
                elif header_row[column] in ['id', 'name']:
                    stop[header_row[column]] = columns[column]

            if 'name' not in stop:
                if stop['id'] in gtfs_dict:
                    stop['name'] = gtfs_dict[stop['id']]

            if len(stop['id']) > 0:
                stop_id = stop['id']
                del stop['id']
                stops[stop_id] = stop

        return json.dumps(stops, sort_keys=True, indent=4)

    def __init__(self):
        self.debug = False
        pass

    @cherrypy.expose
    def index(self):
        stops = self.get_stops()

        if 'stops.json' not in os.listdir('debug'):
            with open('debug/stops.json', mode='w+', encoding='utf-8') as file:
                file.write(stops)

        return stops


if __name__ == '__main__':
    config = {"/": {"tools.gzip.on": True,
                    "tools.gzip.mime_types": ["text/html", "text/plain", "text/javascript",
                                              "text/css", "application/javascript"]},
              "global": {"server.socket_host": "127.0.0.1",
                         "server.socket_port": 9002,
                         "server.thread_pool": 8}}

    # uncomment if running non-debug mode
    # config['global']['environment'] = 'production'

    cherrypy.quickstart(Root(), '/', config)
