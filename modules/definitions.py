import socket
from threading import Thread, Event
from peewee import SqliteDatabase
from modules.sniffer import IPSniff
from scapy.all import TCP, IP, IPv6, Packet
from queue import Queue
import os
import time


class SniffThread(Thread):

    INSTANCE = None

    @staticmethod
    def instance(iface='lo'):
        if SniffThread.INSTANCE is None:
            SniffThread.INSTANCE = SniffThread(iface=iface)
        return SniffThread.INSTANCE

    def __init__(self, iface):
        super().__init__()
        self.queue = []
        self.stopped = None
        self.iface = iface
        self.sniffer = None
        self.INSTANCE = self

    def start_sniffing(self, shared_queue: Queue, stop_event: Event) -> bool:
        self.queue.append(shared_queue)
        if self.stopped is None:
            self.stopped = stop_event
            self.start()
            return True
        return False

    def store_packet(self, direction, packet):
        data = (direction, packet)
        for q in self.queue:
            if not q.full():
                q.put(data)

    def run(self):
        self.sniffer = IPSniff(self.iface, callback=self.store_packet)
        self.sniffer.recv()
        print("Sniffer thread Stopped!")


class MonitoringModule(Thread):
    MODE_IPV4 = 'inet'
    MODE_IPV6 = 'inet6'
    TRAFFIC_OUTBOUND = 'out'
    TRAFFIC_INBOUND = 'in'
    QUEUE_SIZE = 10000
    START_TIME = time.time()
    DATABASE = SqliteDatabase(None)

    @staticmethod
    def packet_type(traffic_type):
        if traffic_type == socket.PACKET_OUTGOING:
            return MonitoringModule.TRAFFIC_OUTBOUND
        return MonitoringModule.TRAFFIC_INBOUND

    def __init__(self, interface='lo', mode=MODE_IPV4):
        super().__init__()
        self.stopped = Event()
        self.sniff_iface = interface
        self.sniff_thread = None
        self.queue = Queue(MonitoringModule.QUEUE_SIZE)

        self.mode = mode
        if mode == MonitoringModule.MODE_IPV4:
            self.ip_layer = IP
        else:
            self.ip_layer = IPv6
        self.iface_ip = self.iface_ip(interface, mode)

    @staticmethod
    def execution_time() -> int:
        return round(time.time() - MonitoringModule.START_TIME)

    @staticmethod
    def iface_ip(iface: str, mode=MODE_IPV4) -> str:
        cmd = 'ip addr show '+iface
        split = mode + ' '
        return os.popen(cmd).read().split(split)[1].split("/")[0]
    
    def start_sniffing(self):
        self.sniff_thread = SniffThread.instance(iface=self.sniff_iface)
        self.sniff_thread.start_sniffing(self.queue, self.stopped)

    def stop_execution(self):
        self.stopped.set()

    @staticmethod
    def classify_packet(packet: Packet, port_map: dict) -> (str, str):
        port = None

        if TCP in packet:
            #packet port is the client dport or the server sport
            if packet.dport in port_map:
                port = packet.dport
            else:
                port = packet.sport

        return port


class DictTools:
    @staticmethod
    def add_multiple_key_single_value(keys: list=[], value=None, dictionary: dict={}):
        for key in keys:
            dictionary[key] = value

    @staticmethod
    def invert(dictionary: dict) -> dict:
        new_dict = {}
        for key in dictionary:
            for value in dictionary[key]:
                new_dict[value] = key
        return new_dict
