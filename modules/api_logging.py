from peewee import *
from playhouse.sqlite_ext import JSONField
from scapy.packet import Raw, bind_layers
from scapy.layers.l2 import Ether
from scapy.layers.inet import IP, TCP, Packet
from scapy.layers.inet6 import IPv6
from scapy_http.http import *
from threading import Thread, Timer, Event
import time
from modules.definitions import MonitoringModule, DictTools


class ApiLogging(MonitoringModule):
    MAP = {
        'nova': {8774},
        'keystone': {5000, 35357},
        'swift': {8080},
        'glance': {9292},
        'cinder': {8776},
        'neutron': {9696},
        'ceph': {6789}
    }

    def __init__(self, db_path, iface='lo', **kwargs):
        self.port_mapping = DictTools.invert(ApiLogging.MAP)
        sniff_filter = self.create_filter(self.port_mapping)
        super().__init__(interface=iface, sniff_filter=sniff_filter, **kwargs)
        self.services = list(ApiLogging.MAP.keys())
        self._bind_ports_http()
        self.init_db(db_path)

    @staticmethod
    def create_filter(ports):
        sniff_filter = 'tcp and inbound and ('
        for i, p in enumerate(ports):
            if i > 0:
                sniff_filter += ' or'
            sniff_filter += ' port '+str(p)
        sniff_filter += ')'
        return sniff_filter

    @staticmethod
    def init_db(path, create_tables=True):
        ApiLogging.DATABASE.init(path)
        ApiLogging.DATABASE.connect()
        if create_tables:
            ApiLogging.DATABASE.create_tables([ApiData])

    def _bind_ports_http(self):
        for port in self.port_mapping:
            bind_layers(TCP, HTTP, sport=port)
            bind_layers(TCP, HTTP, dport=port)

    def measure_packet(self, packet_bytes):
        packet = Ether(packet_bytes)
        port = self.classify_packet(packet, self.port_mapping)

        print('Packet service: ', self.port_mapping[port])
        packet.show()
        print('')

    def run(self):
        while not self.stopped.is_set():
            packet = self.pipe.recv()
            self.measure_packet(packet)
        print("Consumer Thread Stopped!")

    def start_monitoring(self):
        print("Logging API Access")
        self.start_sniffing()
        self.start()

class ApiData(Model):
    interface = CharField()
    type = CharField()
    time = TimeField(formats='%H:%M:%S')
    content = JSONField(default={})
    service = CharField()

    class Meta:
        database = ApiLogging.DATABASE

    def __init__(self, services=None, service_port_map=DictTools.invert(ApiLogging.MAP), **kwargs):
        super(ApiData, self).__init__(**kwargs)
        self.map = service_port_map
        self.services = services

    def classify_port(self, port):
        if port in self.map:
            return self.map[port]
        return 'etc'

    def content(self):
        attrs = {'interface': self.interface, 'type': self.type, 'time': self.time, 'content': self.content, 'service': self.service}
        return attrs

    def __str__(self):
        return str(self.content())

    def save(self, force_insert=False, only=None):
        super(ApiData, self).save(force_insert, only)
