import argparse
import logging
import os
import subprocess
import platform

import yaml

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


class MonitorController:
    def __init__(self):

        self.config_file = os.path.expanduser('~/.monitor_controller/config.yaml')

        try:
            self.load_config()
        except FileNotFoundError:
            self.config = {}
            logging.warning('no config found, using defaults')
            self.init_config_file()
        self.check_config()

        if self.config['debug']:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.CRITICAL)

        logging.debug('working dir: {}'.format(os.path.abspath(os.path.curdir)))

    def set_brightness(self, brightness):
        old_brightness = self.config['brightness']
        logging.debug('old brightness {}'.format(old_brightness))

        logging.debug('new brihtness {}'.format(brightness))
        brightness = clamp_brightness(brightness)

        if platform.system() == 'Windows':
            subprocess.run(('ScreenBright.exe', '-set', 'brightness', str(brightness)))
        elif platform.system() == 'Darwin':
            subprocess.run(('ddcctl', '-d', '1', '-b', str(brightness)))

        self.config['brightness'] = brightness
        self.save_config()

    def change_brightness(self, brightness_change):
        old_brightness = self.config['brightness']

        logging.debug('brightness change {}'.format(brightness_change))
        brightness = brightness_change + old_brightness
        self.set_brightness(brightness)

    def check_config(self):
        keys = (('brightness', DEFAULT_BRIGHTNESS_VALUE),
                ('debug', False))
        for key, def_value in keys:
            if self.config.get(key, None) is None:
                self.config[key] = def_value

    def load_config(self):
        with open(self.config_file, 'r') as ymfile:
            self.config = yaml.load(ymfile)
            logging.debug('config loaded {}'.format(self.config_file))

    def save_config(self):
        with open(self.config_file, 'w') as ymfile:
            yaml.dump(self.config, ymfile)
            logging.debug('config saved')

    def init_config_file(self):
        os.makedirs(os.path.split(self.config_file)[0], exist_ok=True)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    script_dir = os.path.dirname(os.path.realpath(__file__))

    arg_parser = argparse.ArgumentParser(description='change monitor settings')
    arg_parser.add_argument('-b', '--brightness', dest='brightness_change', help='change brightness by value',
                            type=int, choices=range(-100, 101), default=0)
    args = arg_parser.parse_args()

    mn = MonitorController()
    mn.change_brightness(args.brightness_change)
