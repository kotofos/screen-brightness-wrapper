import socket
import argparse
import logging
import os
import ipaddress
import platform
import subprocess
import time
import re
from collections import OrderedDict

import yaml


PORT=48653

MAX_BRIGHTNESS = 100
MIN_BRIGHTNESS = 0
DEFAULT_BRIGHTNESS_VALUE = 50


def clamp_brightness(val):
    if MIN_BRIGHTNESS <= val <= MAX_BRIGHTNESS:
        return val
    elif val > MAX_BRIGHTNESS:
        logging.info('max brightness')
        return MAX_BRIGHTNESS
    elif val < MIN_BRIGHTNESS:
        logging.info('min brightness')
        return MIN_BRIGHTNESS


class Config():
    def __init__(self, is_master,monitor_id=None, ip_addr=None):
        self.is_master = is_master
        self.monitor_id = monitor_id
        if ip_addr is None:
            self.ip = '127.0.0.1'
        else:
            self.ip = ip_addr

        self.config_file = os.path.expanduser('~/.monitor_controller/config.yaml')

        try:
            self.load_config()
        except FileNotFoundError:
            self._config = {}
            logging.warning('no config found, using defaults')
            self.init_config_file()
            self._config['debug'] = True
        self.check_config()

    def check_config(self):
        assert isinstance(self._config, dict)

        if self._config.get('debug', None) is None:
            self._config['debug'] = True
        try:
            self._config[self.ip][self.monitor_id]['brightness']
        except (AttributeError, KeyError):
            self._config[self.ip][self.monitor_id] = {'brightness': DEFAULT_BRIGHTNESS_VALUE}

        if self.monitor_id is None:
            try:
                self.monitor_id = self._config['default_monitor_id']
                logging.debug('No monitor id requested, using default from config {}'.format(self.monitor_id))
            except KeyError:
                logging.debug("No monitor id, using default")
                pass

    def load_config(self):
        with open(self.config_file, 'r') as ymfile:
            self._config = yaml.load(ymfile)
            logging.debug('config loaded {}'.format(self.config_file))

    def save_config(self):
        with open(self.config_file, 'w') as ymfile:
            yaml.dump(self._config, ymfile)
            logging.debug('config saved')
        if self.is_master and False: #todo stat
            value_logger = LogSettings(self._config)
            value_logger.log()

    def init_config_file(self):
        os.makedirs(os.path.split(self.config_file)[0], exist_ok=True)

    @property
    def brightness(self):
        return self._config[self.ip][self.monitor_id]['brightness']

    @brightness.setter
    def brightness(self, val):
        self._config[self.ip][self.monitor_id]['brightness'] = val

    @property
    def debug(self):
        return self._config['debug']

    @debug.setter
    def debug(self, val):
        self._config['debug'] = val


class MonitorController:
    def __init__(self, is_master, monitor_id):

        self.config = Config(is_master, monitor_id)

        if self.config.debug:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.CRITICAL)

        logging.debug('working dir: {}'.format(os.path.abspath(os.path.curdir)))

    def set_brightness(self, brightness):
        old_brightness = self.config.brightness
        logging.debug('old brightness for monitor {} is {}'.format(self.config.monitor_id, old_brightness))

        logging.debug('new brihtness {}'.format(brightness))
        brightness = clamp_brightness(brightness)

        self.send_command(brightness)

        self.config.brightness = brightness
        self.config.save_config()

    def change_brightness(self, brightness_change):
        old_brightness = self.config.brightness

        logging.debug('brightness change {}'.format(brightness_change))
        brightness = brightness_change + old_brightness
        self.set_brightness(brightness)

    def send_command(self, data):
        data = str(data)
        if platform.system() == 'Windows':
            if self.config.monitor_id is None:
                subprocess.run(('ScreenBright.exe', '-set', 'brightness', data))
            else:
                subprocess.run(('ScreenBright.exe', '-set', 'screen', str(self.config.monitor_id) ,'brightness', data))

        elif platform.system() == 'Darwin':
            subprocess.run(('ddcctl', '-d', '1', '-b', data))
        elif platform.system() == 'Linux':
            if self.config.monitor_id is None:
                subprocess.run(('ddctool', 'setvcp', '10', data, '--bus', '0'))
            else:
                subprocess.run(('ddctool', 'setvcp', '10', data, '--bus', str(self.config.monitor_id)))



class RemoteMonitorController(MonitorController):
    def __init__(self, addr):
        self.addr = addr
        self.config = Config(True, self.addr)

    def send_command(self, data):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((self.addr, PORT))
            sock.sendall(str(data).encode())
        finally:
            sock.close()


class LogSettings:
    def __init__(self, config):
        self.config = config
        self.log_file = 'brightness.log'

    def log(self):
        output = str(time.time())
        sorted_dict = OrderedDict(sorted(self.config.items()))
        for key in sorted_dict:
            if key == 'debug':
                continue
            output += ' ' + key
            output += ' ' + str(self.config[key]['brightness'])
        p = subprocess.run(('display-brightness'), stdout=subprocess.PIPE)
        val = int(p.stdout.decode())
        p = subprocess.run(('brightness', '-l'), stdout=subprocess.PIPE)
        res = re.search(('display 1: brightness ([01]\.[0-9]+)'), p.stdout.decode()).group(1)

        output += ' ' + str(val)
        output += ' ' + res
        output += '\n'
        with open(self.log_file, 'a') as f:
            f.write(output)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    script_dir = os.path.dirname(os.path.realpath(__file__))

    arg_parser = argparse.ArgumentParser(description='change monitor settings')
    arg_parser.add_argument('-b', '--brightness', dest='brightness_change', help='change brightness by value',
                            type=int, choices=range(-100, 101), default=0)

    arg_parser.add_argument('-a', '--address', dest='addr', help='remote address')
    arg_parser.add_argument('-m', '--monitor', dest='monitor_id', help='monitor id', type=int)
    args = arg_parser.parse_args()

    if args.addr is not None:
        ip = str(ipaddress.ip_address(args.addr))
        mn = RemoteMonitorController(ip)
    else:
        mn = MonitorController(True, args.monitor_id)
    mn.change_brightness(args.brightness_change)
