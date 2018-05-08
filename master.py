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
from enum import Enum
from threading import Thread

import yaml
from filelock import FileLock

PORT = 48653
config_path = '~/.config/monitor_controller/config.yaml'

MAX_BRIGHTNESS = 100
MIN_BRIGHTNESS = 0
DEFAULT_BRIGHTNESS_VALUE = 50
LOCAL_IP = ['127.0.0.1', 'localhost']

flock_log = logging.getLogger('filelock')
flock_log.setLevel('WARNING')


# todo config docs
# todo supported backends

class Config:
    """Class for accessing config file"""

    def __init__(self, ):
        self.config_file = os.path.expanduser(config_path)
        self.lock = FileLock(self.config_file + '.lock', timeout=10)
        self.lock.acquire()

        try:
            self.load_config()
        except FileNotFoundError:
            self._config_data = {}
            logging.warning('No config found, using defaults')
            self.init_config_filepath()
        self.check_config()

    def check_config(self):
        assert isinstance(self._config_data, dict)

    def load_config(self):
        with open(self.config_file, 'r') as ymfile:
            self._config_data = yaml.load(ymfile)
            logging.debug('Config loaded {}'.format(self.config_file))

    def save_config(self):
        with open(self.config_file, 'w') as ymfile:
            yaml.dump(self._config_data, ymfile)
            logging.debug('Config saved')
        self.lock.release()

    def init_config_filepath(self):
        os.makedirs(os.path.split(self.config_file)[0], exist_ok=True)

    @property
    def debug(self):
        return self._config_data['debug']

    @debug.setter
    def debug(self, val):
        self._config_data['debug'] = val

    @property
    def brightness(self):
        return self._config_data['global_brightness']

    @brightness.setter
    def brightness(self, val):
        self._config_data['global_brightness'] = val

    # to allow direct access to config dict
    def __getitem__(self, item):
        return self._config_data[item]

    def get(self, item, default):
        return self._config_data.get(item, default)


class MontiorsController:

    def __init__(self, monitors=()):
        self.config = Config()
        self.monitors = monitors

        if self.config.debug:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.CRITICAL)

        logging.debug(
            'working dir: {}'.format(os.path.abspath(os.path.curdir)))

    def change_all_brightness(self, brightness_delta_steps):
        delta = brightness_delta_steps * self.config['step']
        old_global = self.config.brightness

        self.get_offset_limits()
        # negative brightness are allowed, for monitors with positive offset
        new_global = self.clamp_global_brightness(old_global + delta)

        logging.debug(
            'delta {} old {} new {}'.format(delta, old_global, new_global))

        any_changed = False

        for ip, host_dict in self.config['hosts'].items():
            threads = []
            for monitor in host_dict['monitors']:
                retval = []
                t = Thread(target=self.process_monitor,
                           args=(host_dict, ip, monitor,
                                 new_global, old_global, retval))
                t.start()
                threads.append((t, retval))

            for t, retval in threads:
                t.join()
                changed = retval[0]
                any_changed |= changed

        if any_changed:
            self.config.brightness = new_global
            self.config.save_config()
        else:
            # All montors at their limit. No changes
            logging.debug('No changes')

    def get_offset_limits(self):
        self.min_offset = 1000
        self.max_offset = -1000
        for ip, host_data in self.config['hosts'].items():
            for monitor in host_data['monitors']:
                self.min_offset = min(self.min_offset,
                                      monitor['brightness_offset'])
                self.max_offset = max(self.max_offset,
                                      monitor['brightness_offset'])

    def clamp_global_brightness(self, val):
        """Apply limits"""
        min_val = self.max_offset + MIN_BRIGHTNESS - 1
        max_val = -self.min_offset + MAX_BRIGHTNESS + 1

        if min_val <= val <= max_val:
            return val
        elif val > max_val:
            logging.info('max global brightness')
            return max_val
        elif val < min_val:
            logging.info('min global brightness')
            return min_val

    def process_monitor(self, host_data, ip, monitor, new_global, old_global,
                        retval):
        cmd = self.get_cmd(host_data, monitor)
        old = old_global * monitor['brightness_mult'] + monitor[
            'brightness_offset']
        old, old_clamped = self.clamp_brightness(old)
        # new*mult + offset
        new = new_global * monitor['brightness_mult'] + monitor[
            'brightness_offset']
        new, clamped = self.clamp_brightness(new)
        changed = new != old
        if changed:
            logging.debug('host {} old {} new {}'.format(ip, old, new))
            self.set_brightness(cmd, ip, new, monitor)

        # restore contrast
        if self.BrightnessClampEnum.NO_CLAMP == clamped:
            self.set_contrast(cmd, ip, monitor['contrast_norm'],
                              monitor)
        else:
            changed = clamped != old_clamped
            if clamped == self.BrightnessClampEnum.MIN:
                self.set_contrast(
                    cmd, ip, monitor['contrast_min'], monitor)
            elif clamped == self.BrightnessClampEnum.MAX:
                self.set_contrast(
                    cmd, ip, monitor['contrast_max'], monitor)

        # aka return from thread
        retval.append(changed)

    def get_cmd(self, host_data, monitor):
        global_cmd = self.config.get('global_cmd', None)
        host_cmd = host_data.get('cmd', global_cmd)
        cmd = monitor.get('cmd', host_cmd)
        assert cmd, "No cmd to execute"

        return cmd

    def set_brightness(self, cmd, ip, val, monitor):
        cmd = cmd.format(
            brightness=val,
            mon_id=monitor['id'],
            prop=monitor['brightness_prop_id'])
        self.set_prop(cmd, ip)

    def set_contrast(self, cmd, ip, val, monitor):
        cmd = cmd.format(
            brightness=val,
            mon_id=monitor['id'],
            prop=monitor['contrast_prop_id'])
        self.set_prop(cmd, ip)

    def set_prop(self, cmd, ip):
        """change brightness for local or remote monitor"""
        if ip in LOCAL_IP:
            subprocess.run(cmd, shell=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, check=True)
        else:
            self.send_remote_command(ip, cmd)

    def send_remote_command(self, ip, data):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((ip, PORT))
            sock.sendall(str(data).encode())
        finally:
            sock.close()

    class BrightnessClampEnum(Enum):
        MIN = 0
        MAX = 1
        NO_CLAMP = 2

    def clamp_brightness(self, val):
        """Apply limits"""
        if MIN_BRIGHTNESS <= val <= MAX_BRIGHTNESS:
            return val, self.BrightnessClampEnum.NO_CLAMP
        elif val > MAX_BRIGHTNESS:
            logging.info('max brightness')
            return MAX_BRIGHTNESS, self.BrightnessClampEnum.MAX
        elif val < MIN_BRIGHTNESS:
            logging.info('min brightness')
            return MIN_BRIGHTNESS, self.BrightnessClampEnum.MIN


class LocalMonitorController:
    def __init__(self, is_master):

        self.config = Config(is_master)

    def change_brightness(self, brightness_change):
        old_brightness = self.config.brightness

        logging.debug('brightness change {}'.format(brightness_change))
        brightness = brightness_change + old_brightness
        self.set_brightness(brightness)

    def set_brightness(self, brightness):
        old_brightness = self.config.brightness
        logging.debug('old brightness {}'.format(old_brightness))

        logging.debug('new brihtness {}'.format(brightness))
        brightness = self.clamp_brightness(brightness)

        self.send_command(brightness)

        self.config.brightness = brightness
        self.config.save_config()

    def send_command(self, data):
        data = str(data)
        if platform.system() == 'Windows':
            subprocess.run(('ScreenBright.exe', '-set', 'brightness', data))
        elif platform.system() == 'Darwin':
            subprocess.run(('ddcctl', '-d', '1', '-b', data))
        elif platform.system() == 'Linux':
            subprocess.run(('ddctool', 'setvcp', '10', data, '--bus', '0'))


class RemoteMonitorController(LocalMonitorController):
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
        res = re.search(('display 1: brightness ([01]\.[0-9]+)'),
                        p.stdout.decode()).group(1)

        output += ' ' + str(val)
        output += ' ' + res
        output += '\n'
        with open(self.log_file, 'a') as f:
            f.write(output)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    arg_parser = argparse.ArgumentParser(description='Change monitor settings')
    arg_parser.add_argument(
        '-b', '--brightness', dest='brightness_delta_steps',
        help='increase or decrease brightness by step count +- value',
        type=int, choices=range(-100, 101), default=0)

    # arg_parser.add_argument(
    #   '-a', '--address', dest='addr',
    #  help='remote address')

    # todo
    # arg_parser.add_argument('-m', '--monitor', dest='monitor_id',
    # help='select monitor')
    args = arg_parser.parse_args()

    mn = MontiorsController()
    mn.change_all_brightness(args.brightness_delta_steps)
    exit()

    if args.addr is not None:
        ip = str(ipaddress.ip_address(args.addr))
        mn = RemoteMonitorController(ip)
    else:
        mn = LocalMonitorController()
    mn.change_brightness(args.brightness_change)
