#!/usr/bin/env python
#
#    This file is part of Scalable COncurrent Operations in Python (SCOOP).
#
#    SCOOP is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of
#    the License, or (at your option) any later version.
#
#    SCOOP is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with SCOOP. If not, see <http://www.gnu.org/licenses/>.
#
from collections import deque, defaultdict, namedtuple
import time
import zmq
import sys
import threading
import scoop
try:
    import cPickle as pickle
except ImportError:
    import pickle

from .. import discovery

# Worker requests
INIT = b"INIT"
REQUEST = b"REQUEST"
TASK = b"TASK"
REPLY = b"REPLY"
SHUTDOWN = b"SHUTDOWN"
VARIABLE = b"VARIABLE"
TASKEND = b"TASKEND"
BROKER_INFO = b"BROKER_INFO"
# Broker interconnection
CONNECT = b"CONNECT"

BrokerInfo = namedtuple('BrokerInfo', ['hostname',
                                       'task_port',
                                       'info_port',
                                       'externalHostname'])

class LaunchingError(Exception): pass

class Broker(object):
    def __init__(self, tSock="tcp://*:*", mSock="tcp://*:*", debug=False,
                 headless=False, hostname="127.0.0.1"):
        """This function initializes a broker.

        :param tSock: Task Socket Address.
        Must contain protocol, address  and port information.
        :param mSock: Meta Socket Address.
        Must contain protocol, address and port information.
        """
        # Initialize zmq
        self.context = zmq.Context(1)

        self.debug = debug
        self.hostname = hostname

        # Create identifier for this broker
        import uuid
        self.name = str(uuid.uuid4())
        scoop.logger.info("Using name {workerName}.".format(
            workerName=self.getName(),
        ))

        # zmq Socket for the tasks, replies and request.
        self.taskSocket = self.context.socket(zmq.ROUTER)
        self.taskSocket.setsockopt(zmq.LINGER, 1000)
        self.tSockPort = 0
        if tSock[-2:] == ":*":
            self.tSockPort = self.taskSocket.bind_to_random_port(tSock[:-2])
        else:
            self.taskSocket.bind(tSock)
            self.tSockPort = tSock.split(":")[-1]

        # zmq Socket for the pool informations
        self.infoSocket = self.context.socket(zmq.PUB)
        self.infoSocket.setsockopt(zmq.LINGER, 1000)
        self.infoSockPort = 0
        if mSock[-2:] == ":*":
            self.infoSockPort = self.infoSocket.bind_to_random_port(mSock[:-2])
        else:
            self.infoSocket.bind(mSock)
            self.infoSockPort = mSock.split(":")[-1]

        if zmq.zmq_version_info() >= (3, 0, 0):
            self.taskSocket.setsockopt(zmq.SNDHWM, 0)
            self.taskSocket.setsockopt(zmq.RCVHWM, 0)
            self.infoSocket.setsockopt(zmq.SNDHWM, 0)
            self.infoSocket.setsockopt(zmq.RCVHWM, 0)

        # Init connection to fellow brokers
        self.clusterSocket = self.context.socket(zmq.DEALER)
        self.clusterSocket.setsockopt_string(zmq.IDENTITY, self.getName())
        if zmq.zmq_version_info() >= (3, 0, 0):
            self.clusterSocket.setsockopt(zmq.RCVHWM, 0)
            self.clusterSocket.setsockopt(zmq.SNDHWM, 0)
        self.cluster = []
        self.clusterAvailable = set()

        # Init statistics
        if self.debug:
            self.stats = []

        # Two cases are important and must be optimised:
        # - The search of unassigned task
        # - The search of available workers
        # These represent when the broker must deal the communications the
        # fastest. Other cases, the broker isn't flooded with urgent messages.

        # Initializing the queue of workers and tasks
        # The busy workers variable will contain a dict (map) of workers: task
        self.availableWorkers = deque()
        self.unassignedTasks = deque()
        self.groupTasks = {}
        # Shared variables containing {workerID:{varName:varVal},}
        self.sharedVariables = defaultdict(dict)

        # Start a worker-like communication if needed
        self.execQueue = None

        # Handle cloud-like behavior
        self.discoveryThread = None
        self.config = defaultdict(bool)
        self.processConfig({'headless': headless})

    def addBrokerList(self, aBrokerInfoList):
        """Add a broker to the broker cluster available list.
        Connects to the added broker if needed."""
        self.clusterAvailable.update(set(aBrokerInfoList))

        # If we need another connection to a fellow broker
        # TODO: only connect to a given number
        for aBrokerInfo in aBrokerInfoList:
            self.clusterSocket.connect(
                "tcp://{hostname}:{port}".format(
                    hostname=aBrokerInfo.hostname,
                    port=aBrokerInfo.task_port,
                )
            )
            self.cluster.append(aBrokerInfo)

    def processConfig(self, worker_config):
        """Update the pool configuration with a worker configuration.
        """
        self.config['headless'] |= worker_config.get("headless", False)
        if self.config['headless']:
            # Launch discovery process
            if not self.discoveryThread:
                self.discoveryThread = discovery.Advertise(
                    port=",".join(str(a) for a in self.getPorts()),
                )

    def run(self):
        """Redirects messages until a shutdown message is received.
        """
        while True:
            if not self.taskSocket.poll(-1):
                continue

            msg = self.taskSocket.recv_multipart()
            msg_type = msg[1]

            if self.debug:
                self.stats.append((time.time(),
                                   msg_type,
                                   len(self.unassignedTasks),
                                   len(self.availableWorkers)))

            # New task inbound
            if msg_type in TASK:
                task = msg[2]
                try:
                    address = self.availableWorkers.popleft()
                except IndexError:
                    self.unassignedTasks.append(task)
                else:
                    self.taskSocket.send_multipart([address, TASK, task])

            # Request for task
            elif msg_type == REQUEST:
                address = msg[0]
                try:
                    task = self.unassignedTasks.pop()
                except IndexError:
                    self.availableWorkers.append(address)
                else:
                    self.taskSocket.send_multipart([address, TASK, task])

            # Answer needing delivery
            elif msg_type == REPLY:
                address = msg[3]
                task = msg[2]
                self.taskSocket.send_multipart([address, REPLY, task])

            # Shared variable to distribute
            elif msg_type == VARIABLE:
                address = msg[4]
                value = msg[3]
                key = msg[2]
                self.sharedVariables[address].update(
                    {key: value},
                )
                self.infoSocket.send_multipart([VARIABLE,
                                                key,
                                                value,
                                                address])

            # Initialize the variables of a new worker
            elif msg_type == INIT:
                address = msg[0]
                try:
                    self.processConfig(pickle.loads(msg[2]))
                except pickle.PickleError:
                    continue
                self.taskSocket.send_multipart([
                    address,
                    pickle.dumps(self.config,
                                 pickle.HIGHEST_PROTOCOL),
                    pickle.dumps(self.sharedVariables,
                                 pickle.HIGHEST_PROTOCOL),
                ])

                self.taskSocket.send_multipart([
                    address,
                    pickle.dumps(self.clusterAvailable,
                                 pickle.HIGHEST_PROTOCOL),
                ])

            # Clean the buffers when a coherent (mapReduce/mapScan)
            # operation terminates
            elif msg_type == TASKEND:
                askResult = msg[2]
                groupID = msg[3]
                self.infoSocket.send_multipart([
                    TASKEND,
                    askResult,
                    groupID,
                ])

            # Add a given broker to its fellow list
            elif msg_type == CONNECT:
                try:
                    connect_brokers = pickle.loads(msg[2])
                except pickle.PickleError:
                    scoop.logger.error("Could not understand CONNECT message.")
                    continue
                self.addBrokerList(connect_brokers)

            # Shutdown of this broker was requested
            elif msg_type == SHUTDOWN:
                self.shutdown()
                break

    def getPorts(self):
        return (self.tSockPort, self.infoSockPort)

    def getName(self):
        import sys
        if sys.version < '3':
            return unicode(self.name)
        return self.name

    def shutdown(self):
        # This send may raise an ZMQError
        # Looping over it until it gets through
        for i in range(100):
            try:
                self.infoSocket.send(SHUTDOWN)
            except zmq.ZMQError:
                time.sleep(0.01)
            else:
                break
        time.sleep(0.1)

        self.taskSocket.close()
        self.infoSocket.close()
        self.context.term()

        # Write down statistics about this run if asked
        if self.debug:
            import os
            import pickle
            try:
                os.mkdir('debug')
            except:
                pass
            with open("debug/broker-broker", 'wb') as f:
                pickle.dump(self.stats, f)
