import requests
import cherrypy
import json
import os
import time


class Root(object):

    session = requests.session()
    gps_url = 'http://marsruti.lv/rigasmikroautobusi/gps.txt?{}'

    @staticmethod
    def parse_bus(bus):
        bus_data = bus.split(',')
        bus_geo_location = (int(bus_data[2]), int(bus_data[3]))
        bus_geo_location = (bus_geo_location[0] / 1000000, bus_geo_location[1] / 1000000)

        return {'route_number': bus_data[1],
                'lng': bus_geo_location[0],
                'lat': bus_geo_location[1],
                'speed': bus_data[4],
                'heading': bus_data[5],
                'car_id': bus_data[6]}

    def get_gps(self):
        response = self.session.get(self.gps_url.format(str(round(time.time(), 3)).replace('.', '')))

        raw_content = response.content
        buses = raw_content.decode('utf-8').split('\n')

        return json.dumps([self.parse_bus(d) for d in buses if len(d) > 0], sort_keys=True, indent=4)

    @staticmethod
    def get_archived_gps_files():
        return sorted([(os.path.getmtime('gps/{}'.format(d)), d) for d in os.listdir('gps')], key=lambda d: d[0])

    def __init__(self):
        self.debug = True
        self.old_gps = self.get_archived_gps_files()

    def replay_gps(self):
        try:
            file = self.old_gps[0][1]
        except IndexError:
            self.old_gps = self.get_archived_gps_files()
            file = self.old_gps[0][1]

        del self.old_gps[0]
        with open('gps/{}'.format(file), mode='r', encoding='utf-8') as gps_file:
            gps_data = gps_file.read()
            if len(gps_data) == 0:
                if len(self.old_gps) != 0:
                    return self.replay_gps()
                else:
                    return []
            buses = gps_data.split('\n')
            return json.dumps([self.parse_bus(d) for d in buses if len(d) > 0], sort_keys=True, indent=4)

    @cherrypy.expose
    def index(self):
        if self.debug:
            return self.replay_gps()
        else:
            return self.get_gps()


if __name__ == '__main__':
    config = {"/": {"tools.gzip.on": True,
                    "tools.gzip.mime_types": ["text/html", "text/plain", "text/javascript",
                                              "text/css", "application/javascript"]},
              "global": {"server.socket_host": "127.0.0.1",
                         "server.socket_port": 9004,
                         "server.thread_pool": 8}}

    # uncomment if running non-debug mode
    # config['global']['environment'] = 'production'

    cherrypy.quickstart(Root(), '/', config)
