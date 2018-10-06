import cherrypy
import json
import tenjin
import requests
import os
from tenjin.helpers import *
from tenjin.html import *
# todo should be decoupled
from tracker_service import explode_times
from tracker_service import format_time


# todo: should probably just rewrite this in something else
class Root(object):
    engine = tenjin.Engine()

    navbar = {'title': 'Minibus Tracker',
              'links': [{'template': 'index',
                         'text': 'Home',
                         'href': '',
                         'active': ''}]}

    @staticmethod
    def init_metadata():
        default_metadata = {'favicon': '<link rel="shortcut icon" href="/favicon.ico" type="image/x-icon">',
                            'content_type': '<meta http-equiv="Content-Type" content="text/html;charset=utf-8">',
                            'encoding': '<meta http-equiv="encoding" content="utf-8">',
                            'viewport': '<meta name="viewport" content="width=device-width,'
                                        ' initial-scale=1, shrink-to-fit=no">',
                            'boot_css': '<link href="/css/bootstrap.min.css" '
                                        'media="all" rel="stylesheet" type="text/css">',
                            'css': '<link href="/css/site.css" media="all" rel="stylesheet" type="text/css">'}
        return {'index': {**default_metadata,
                          **{'title': '<title>Minibus Tracker</title>',
                             'icons': '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax'
                                      '/libs/font-awesome/4.7.0/css/font-awesome.min.css">'}}}

    def generate_page_html(self, template, main_context, metadata=None):
        if metadata is None:
            metadata = self.metadata[template]

        template_path = 'templates/' + template + '.tmp'
        html_body = self.engine.render(template_path, main_context)

        for link in self.navbar['links']:
            if link['template'] in template:
                link['active'] = ' active'
            else:
                link['active'] = ''

        page_context = {'html_body': html_body,
                        'html_metadata': metadata,
                        'navbar': self.navbar}

        return self.engine.render('templates/page_tenjin.tmp', page_context)

    def __init__(self):
        self.metadata = self.init_metadata()
        self.routes = json.loads(requests.get('http://127.0.0.1:9003').content.decode('utf-8'))

        # todo: duplicate from tracker
        for route in self.routes:
            route['time_table'] = explode_times(route['departure_times'])

    @cherrypy.expose
    def index(self, route_number=None, route_type=None, destination=None):
        # for testing http://127.0.0.1:8080/?route_number=246&route_type=a1-b&destination=30

        minibus_data = json.loads(requests.get('http://127.0.0.1:9005').content.decode('utf-8'))

        if route_number is not None and route_type is not None:
            minibus_data = [minibus for minibus in minibus_data if
                            minibus['route_number'] == route_number and
                            minibus['route_type'] == route_type and
                            minibus['tracking']['direction'] == 'from_start']

        if destination is not None:
            destination = int(destination) - 1

            route = [route for route in self.routes if
                     route['route_number'] == route_number and
                     route['route_type'] == route_type][0]

            time_table = route['time_table']
            route_stops = route['route_stops']

            max_departures = len(time_table['weekdays'])
            end_stop = len(route_stops) - 1

            if end_stop < destination:
                destination = end_stop

            minibus_data = [minibus for minibus in minibus_data if minibus['tracking']['stop_id'] <= destination]

            for minibus in minibus_data:
                # todo: mimics code in tracker service
                time_table_index = minibus['tracking']['departure_id'] - 1 +\
                                   minibus['tracking']['stop_id'] * max_departures
                target_time_table_index = minibus['tracking']['departure_id'] - 1 + destination * max_departures

                raw_time = time_table['timetable'][time_table_index]
                route_end_raw_time = time_table['timetable'][target_time_table_index]

                raw_time_to_arrive = route_end_raw_time - raw_time

                formatted_time_to_arrive = format_time(abs(raw_time_to_arrive))

                if raw_time_to_arrive < 0:
                    formatted_time_to_arrive = '({})'.format(formatted_time_to_arrive)

                minibus['time_to_arrive'] = formatted_time_to_arrive

                minibus['destination_stop'] = route_stops[destination]['name']
                minibus['current_stop'] = route_stops[minibus['tracking']['stop_id']]['name']

        for minibus in minibus_data:
            del minibus['tracking']['closer']
            del minibus['tracking']['disqualified']
            del minibus['tracking']['safe_to_include']

        main_context = {'minibus_data': minibus_data}

        return self.generate_page_html('index', main_context)


if __name__ == '__main__':
    os.environ['NO_PROXY'] = '127.0.0.1'
    # conf.json essentially just points to the several static files necessary for bootstrap
    if 'conf.json' in os.listdir('.'):
        with open("conf.json", "r") as config_file:
            conf = json.loads(config_file.read())
    else:
        conf = {"/": {"tools.gzip.on": True,
                      "tools.gzip.mime_types": ["text/html", "text/plain", "text/javascript",
                                                "text/css", "application/javascript"]},
                "global": {"server.socket_host": "127.0.0.1",
                           "server.socket_port": 8080,
                           "server.thread_pool": 8}}

    # uncomment if running non-debug mode
    # conf['global']['environment'] = 'production'

    cherrypy.quickstart(Root(), '/', conf)
