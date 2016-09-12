import socketserver
from screen_bright_wrapper import MonitorController
import logging

logging.basicConfig(level=logging.DEBUG)

PORT = 48653


class MyTCPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.data = self.request.recv(1024).decode()
        try:
            self.data = int(self.data)
        except ValueError:
            pass
        else:
            mc = MonitorController()
            mc.change_brightness(self.data)


server = socketserver.TCPServer(("", PORT), MyTCPHandler)
server.serve_forever()
