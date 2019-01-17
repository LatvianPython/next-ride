import cherrypy
import json
import time
import math
import requests
import os
from cherrypy.process.plugins import BackgroundTask


def running_sum(a):
    total = 0
    for item in a:
        total += int(item)
        yield total


def parse_days(encoded_data, days):
    chunks = [encoded_data[x:x + 2] for x in range(0, len(encoded_data), 2)]

    valid_from = []
    for day in chunks:
        try:
            valid_from += [day[0]] * int(day[1])
        except IndexError:
            valid_from += [day[0]] * (days - len(valid_from))
    return valid_from


def split_data(data):
    remaining_data = data.copy()
    result = []
    for i in range(0, 4):
        index = remaining_data.index('')
        result.append(remaining_data[:index])
        remaining_data = remaining_data[index + 1:]
    result.append(remaining_data)

    return result


# todo: multiple places in codebase uses this function, need to refactor process
def explode_times(encoded_data):
    # decoding times
    data = encoded_data.split(',')

    data = split_data(data)

    number_of_departures = len(data[0])

    timetable = list(running_sum(data[0]))
    valid_from = parse_days(data[1], number_of_departures)
    valid_to = parse_days(data[2], number_of_departures)
    weekdays = parse_days(data[3], number_of_departures)

    time_between_stops = data[4]

    delta_time = 5
    left_to_parse = number_of_departures
    for i in range(0, len(time_between_stops) - 2, 2):
        times = (time_between_stops[i], time_between_stops[i + 1])
        delta_time = delta_time + int(time_between_stops[i]) - 5
        stop_with_current_delta = int(times[1].zfill(1))

        if stop_with_current_delta > 0:
            left_to_parse = left_to_parse - stop_with_current_delta
        else:
            stop_with_current_delta = left_to_parse
            left_to_parse = 0

        index_to = -(number_of_departures - stop_with_current_delta)
        if index_to == 0:
            index_to = None

        timetable += [departure_time + delta_time for departure_time in timetable[-number_of_departures:index_to]]

        if left_to_parse <= 0:
            left_to_parse = number_of_departures
            delta_time = 5

    return {'weekdays': weekdays,
            'timetable': timetable,
            'valid_from': valid_from,
            'valid_to': valid_to}


def format_time(minutes):
    return '{}:{}'.format(str(int(minutes / 60) % 24).rjust(2), str(minutes % 60).zfill(2))


def measure(lat1, lon1, lat2, lon2):
    r = 6378.137
    d_lat = lat2 * math.pi / 180 - lat1 * math.pi / 180
    d_lon = lon2 * math.pi / 180 - lon1 * math.pi / 180
    a = math.sin(d_lat / 2) * math.sin(d_lat / 2) + \
        math.cos(lat1 * math.pi / 180) * math.cos(lat2 * math.pi / 180) * math.sin(d_lon / 2) * math.sin(d_lon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    d = r * c
    return d * 1000


def distance_between_points(p1, p2):
    return measure(p1[0], p1[1], p2[0], p2[1])


def get_routes():
    os.environ['NO_PROXY'] = '127.0.0.1'
    return json.loads(requests.get('http://127.0.0.1:9003').content.decode('utf-8'))


class Root(object):
    tracked_buses = []

    @staticmethod
    def get_minibus_locations():
        os.environ['NO_PROXY'] = '127.0.0.1'
        return json.loads(requests.get('http://127.0.0.1:9004').content.decode('utf-8'))

    def track_minibuses(self):
        current_time = time.localtime().tm_hour * 60 + time.localtime().tm_min

        minibuses = self.get_minibus_locations()

        valid_buses = [minibus
                       for minibus in minibuses
                       if minibus['route_number'] in [route['route_number']
                                                      for route in self.routes]]

        temp_tracking = []
        for route in self.routes:
            minibuses_in_route = [minibus for minibus in valid_buses if
                                  minibus['route_number'] == route['route_number']]

            time_table = route['time_table']
            route_stops = route['route_stops']

            max_departures = len(time_table['weekdays'])
            target_stop = len(route_stops) - 1

            for minibus in minibuses_in_route:
                minibus['route_type'] = route['route_type']

                bus_geo_location = (minibus['lng'], minibus['lat'])

                closest_stop = (99999, None, 0)
                for route_stop in range(0, len(route_stops)):
                    stop_geo_location = (route_stops[route_stop]['lng'], route_stops[route_stop]['lat'])
                    distance = distance_between_points(bus_geo_location, stop_geo_location)
                    if closest_stop[0] > distance:
                        closest_stop = (distance, route_stops[route_stop], route_stop)

                times_table = time_table['timetable']

                best_fit = (99999, 0)
                for i in range(1, max_departures + 1):
                    test_index = i - 1 + closest_stop[2] * max_departures
                    if abs(times_table[test_index] - current_time) < best_fit[0]:
                        best_fit = (abs(times_table[test_index] - current_time), i)

                clicked_departure = best_fit[1]

                # todo same code already in html_service
                time_table_index = clicked_departure - 1 + closest_stop[2] * max_departures
                target_time_table_index = clicked_departure - 1 + target_stop * max_departures

                raw_time = time_table['timetable'][time_table_index]
                route_end_raw_time = time_table['timetable'][target_time_table_index]

                raw_time_to_arrive = route_end_raw_time - raw_time

                previous_tracking = None

                for i in range(0, len(self.tracked_buses)):
                    if self.tracked_buses[i]['car_id'] == minibus['car_id'] and \
                            self.tracked_buses[i]['route_number'] == minibus['route_number'] and \
                            self.tracked_buses[i]['route_type'] == minibus['route_type']:
                        previous_tracking = self.tracked_buses[i]['tracking']

                if previous_tracking is None:
                    tracking = {'closer': 0,
                                'further': 0,
                                'disqualified': 0,
                                'safe_to_include': 0,
                                'readings': 0,
                                'direction': 'undefined',
                                'distance_to_stop': closest_stop[0],
                                'stop_id': closest_stop[2]}
                else:
                    tracking = previous_tracking

                tracking['departure_id'] = clicked_departure

                if raw_time_to_arrive == 0:
                    tracking['direction'] = 'to_start'
                    tracking['disqualified'] = 1
                    tracking['safe_to_include'] = 0
                    tracking['further'] = 0
                    tracking['closer'] = 0
                    tracking['readings'] = 0

                if closest_stop[2] == 0:
                    tracking['direction'] = 'from_start'
                    tracking['disqualified'] = 0
                    tracking['safe_to_include'] = 1
                    tracking['further'] = 0
                    tracking['closer'] = 0
                    tracking['readings'] = 0

                if tracking['stop_id'] < closest_stop[2]:
                    tracking['further'] += 1
                elif tracking['stop_id'] > closest_stop[2]:
                    tracking['closer'] += 1

                if tracking['disqualified'] + tracking['safe_to_include'] == 0 and \
                        tracking['readings'] > 10 and tracking['closer'] + tracking['further'] > 2:
                    if tracking['closer'] < tracking['further']:
                        tracking['direction'] = 'from_start'
                    else:
                        tracking['direction'] = 'to_start'

                tracking['distance_to_stop'] = closest_stop[0]
                tracking['stop_id'] = closest_stop[2]

                tracking['readings'] += 1

                tracked_bus = minibus.copy()

                tracked_bus['tracking'] = tracking

                temp_tracking.append(tracked_bus)

        self.tracked_buses = temp_tracking
        pass

    def __init__(self):
        self.routes = get_routes()

        for route in self.routes:
            route['time_table'] = explode_times(route['departure_times'])

        task = BackgroundTask(interval=1, function=self.track_minibuses, bus=cherrypy.engine)
        task.start()
        pass

    @cherrypy.expose
    def index(self, route_number=None, route_type=None):

        tracked_buses = self.tracked_buses

        if route_number is not None and route_type is not None:
            tracked_buses = [minibus for minibus in tracked_buses if
                             minibus['route_number'] == route_number and
                             minibus['route_type'] == route_type]

        tracked_buses = json.dumps(tracked_buses, sort_keys=True, indent=4)

        if 'tracked_buses.json' not in os.listdir('debug'):
            with open('debug/tracked_buses.json', mode='w+', encoding='utf-8') as file:
                file.write(tracked_buses)

        return tracked_buses


if __name__ == '__main__':
    config = {"/": {"tools.gzip.on": True,
                    "tools.gzip.mime_types": ["text/html", "text/plain", "text/javascript",
                                              "text/css", "application/javascript"]},
              "global": {"server.socket_host": "127.0.0.1",
                         "server.socket_port": 9005,
                         "server.thread_pool": 8}}

    # uncomment if running non-debug mode
    # config['global']['environment'] = 'production'

    cherrypy.quickstart(Root(), '/', config)
