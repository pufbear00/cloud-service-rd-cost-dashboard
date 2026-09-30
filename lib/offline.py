"""Local-only copy. There is deliberately no environment flag to enable services."""
import socket


class OfflineModeError(RuntimeError):
    pass


def require_online(*args, **kwargs):
    raise OfflineModeError('空数据副本禁止联网采集、读取系统凭据和写入线上系统。')


def install_network_guard():
    socket.socket.connect = require_online
    socket.socket.connect_ex = require_online
    socket.socket.sendto = require_online
    socket.create_connection = require_online
    socket.getaddrinfo = require_online
