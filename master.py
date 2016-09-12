import socket
import argparse

arg_parser = argparse.ArgumentParser(description='change monitor settings')
arg_parser.add_argument('-b', '--brightness', dest='brightness_change', help='change brightness by value',
                        type=int, choices=range(-100, 101), default=0)
args = arg_parser.parse_args()

PORT=48653
HOST='10.144.10.181'
data = str(args.brightness_change)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    # Connect to server and send data
    sock.connect((HOST, PORT))
    sock.sendall(data.encode())

finally:
    sock.close()
