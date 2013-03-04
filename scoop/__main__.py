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
# Global imports
import argparse
import os
import sys
import socket
import subprocess
import time
import logging
import traceback
import signal

# Local imports
from scoop import utils
from scoop.launch import Host
from scoop.launch.brokerLaunch import localBroker, remoteBroker
import scoop

try:
    signal.signal(signal.SIGQUIT, utils.KeyboardInterruptHandler)
except AttributeError:
    # SIGQUIT doesn't exist on Windows
    signal.signal(signal.SIGTERM, utils.KeyboardInterruptHandler)


class ScoopApp(object):
    """SCOOP application. Coordinates the launches."""
    LAUNCH_HOST_CLASS = Host

    def __init__(self, hosts, n, verbose, python_executable, brokerHostname,
            executable, arguments, tunnel, log, path, debug, nice,
            env, profile, pythonPath):
        # Assure setup sanity
        assert type(hosts) == list and hosts, ("You should at least "
                                               "specify one host.")
        self.workersLeft = n
        self.createdSubprocesses = []

        # launch information
        self.python_executable = python_executable[0]
        self.pythonpath = pythonPath
        self.n = n
        self.tunnel = tunnel
        self.executable = executable
        self.args = arguments
        self.verbose = verbose
        self.path = path
        self.debug = debug
        self.nice = nice
        self.profile = profile
        self.errors = None

        # Logging configuration
        if self.verbose > 2:
            self.verbose = 2

        self.log = None
        self.init_logging(log)

        self.log.info("SCOOP {0} {1} on {2} using Python {3}, API: {4}".format(
                scoop.__version__,
                scoop.__revision__,
                sys.platform,
                sys.version.replace("\n", ""),
                sys.api_version,
            )
        )

        if env in ["PBS", "SGE"]:
            self.log.info("Detected {0} environment.".format(env))
        self.log.info("Deploying {0} worker(s) over {1} "
                     "host(s).".format(n,
                                       len(hosts)))

        # Handling Broker Hostname
        self.brokerHostname = '127.0.0.1' if self.tunnel else brokerHostname
        self.log.debug('Using hostname/ip: "{0}" as external broker '
                      'reference.'.format(self.brokerHostname))
        self.log.debug('The python executable to execute the program with is: '
                     '{0}.'.format(self.python_executable))

        self.divideHosts(hosts)

        self.showHostDivision(headless=not executable)

        self.hostsConn = []

    def init_logging(self, log):
        verbose_levels = {0: logging.WARNING,
                          1: logging.INFO,
                          2: logging.DEBUG,
                         }
        logging.basicConfig(filename=log,
                            level=verbose_levels[self.verbose],
                            format='[%(asctime)-15s] %(levelname)-7s '
                                   '%(message)s')
        self.log = logging.getLogger(self.__class__.__name__)

    def divideHosts(self, hosts):
        """Divide the workers accross hosts."""
        maximumWorkers = sum(host[1] for host in hosts)

        # If specified amount of workers is greater than sum of each specified.
        if self.n > maximumWorkers:
            self.log.debug("The -n flag is set at {0} workers, which is higher "
                         "than the maximum number of workers ({1}) specified "
                         "by the hostfile.\nThis behavior may degrade the "
                         "performances of scoop for cpu-bound operations."
                         "".format(self.n, maximumWorkers))
            index = 0
            while self.n > maximumWorkers:
                hosts[index] = (hosts[index][0], hosts[index][1] + 1)
                index = (index + 1) % len(hosts)
                maximumWorkers += 1

        # If specified amount of workers if lower than sum of each specified.
        elif self.n < maximumWorkers:
            self.log.debug("The -n flag is set at {0} workers, which is lower "
                         "than the maximum number of workers ({1}) specified "
                         "by the hostfile."
                         "".format(self.n, maximumWorkers))
            while self.n < maximumWorkers:
                maximumWorkers -= hosts[-1][1]
                if self.n > maximumWorkers:
                    hosts[-1] = (hosts[-1][0], self.n - maximumWorkers)
                    maximumWorkers += hosts[-1][1]
                else:
                    del hosts[-1]


        # Checking if the broker if externally routable
        if self.brokerHostname in utils.loopbackReferences and \
                len(hosts) > 1 and \
                not self.tunnel:
            raise Exception("\n"
                            "Could not find route from external worker to the "
                            "broker: Unresolvable hostname or IP address.\n "
                            "Please specify your externally routable hostname "
                            "or IP using the --broker-hostname parameter or "
                            " use the --tunnel flag.")

        hosts.reverse()
        self.hosts = hosts

    def showHostDivision(self, headless):
        # Show worker distribution
        self.log.info('Worker distribution: ')
        for worker, number in reversed(self.hosts):
            first_worker = (worker == self.hosts[-1][0])
            self.log.info('   {0}:\t{1} {2}'.format(
                worker,
                number - 1 if first_worker or not headless else str(number),
                "+ origin" if first_worker or not headless else "",
                )
            )

    def _addWorker_args(self, workerinfo):
        """Create the arguments to pass to the addWorker call.
            The returned args and kwargs must ordered/named according to the namedtuple
            in LAUNCH_HOST_CLASS.LAUNCHING_ARGUMENTS

            both args and kwargs are supported for full flexibilty,
            but usage of kwargs only is strongly advised

            workerinfo is a dict with information that can be used to start the worker
        """
        args = []
        kwargs = {
                  'pythonPath':self.pythonpath,
                  'path':self.path,
                  'nice':self.nice,
                  'pythonExecutable':self.python_executable,
                  'size':self.n,
                  'workerNum':self.workersLeft,
                  'brokerHostname':self.brokerHostname,
                  'brokerPorts':(self.broker.brokerPort, self.broker.infoPort),
                  'debug':self.debug,
                  'profiling':self.profile,
                  'executable':self.executable,
                  'args':self.args,
                  }
        return args, kwargs

    def addWorkerToHost(self, workerinfo):
        """add a worker to current host"""
        hostname = workerinfo['hostname']

        self.log.debug('Initialising {0}{1} worker {2} [{3}].'.format(
            "local" if hostname in utils.localHostnames else "remote",
            " origin" if self.workersLeft == 1 else "",
            self.workersLeft,
            hostname,
            )
        )

        add_args, add_kwargs = self._addWorker_args(workerinfo)
        self.hostsConn[-1].addWorker(*add_args, **add_kwargs)

    def run(self):
        """Launch the broker and every worker assigned on every hosts."""
        # Launching the local broker, repeat until it works
        if self.brokerHostname in utils.localHostnames:
            self.broker = localBroker(debug=self.debug,
                                      nice=self.nice,
                                      subbroker=not self.executable,
                                      )
        else:
            self.broker = remoteBroker(self.brokerHostname,
                                       self.python_executable,
                                       self.nice,
                                       subbroker=not self.executable,
                                       )

        # Launch the workers
        for hostname, nbworkers in self.hosts:
            self.hostsConn.append(self.LAUNCH_HOST_CLASS(hostname))
            total_workers_host = min(nbworkers, self.workersLeft)
            for worker_idx_host in range(total_workers_host):
                workerinfo = {'hostname':hostname,
                              'total_workers_host':total_workers_host,
                              'worker_idx_host':worker_idx_host
                              }
                self.addWorkerToHost(workerinfo)
                self.workersLeft -= 1

            # Launch every workers at the same time
            self.log.debug(
                "{0}: Launching '{1}'".format(
                    hostname,
                    self.hostsConn[-1].getCommand(),
                )
            )
            shells = self.hostsConn[-1].launch(
                (self.broker.brokerPort,
                 self.broker.infoPort)
                    if self.tunnel else None,
                stdPipe=not self.hostsConn[-1].isLocal(),
            )
            if self.workersLeft <= 0:
                # We've launched every worker we needed, so let's exit the loop
                rootProcess = shells[-1]
                break

        # Wait for the root program
        if self.hostsConn[-1].isLocal():
            self.errors = self.hostsConn[-1].subprocesses[-1].wait()
        else:
            # Process stdout first, then the whole stderr at the end
            for outStream, inStream in [(sys.stdout, rootProcess.stdout),
                                        (sys.stderr, rootProcess.stderr)]:
                data = inStream.read(1)
                while len(data) > 0:
                    # Should not rely on utf-8 codec
                    outStream.write(data.decode("utf-8"))
                    outStream.flush()
                    data = inStream.read(1)
            self.errors = rootProcess.wait()
        self.log.info('Root process is done.')

    def close(self):
        """Subprocess cleanup."""
        # Give time to flush data if debug was on
        if self.debug:
            time.sleep(5)

        # Terminate workers
        for host in self.hostsConn:
            host.close()

        # Terminate the broker
        try:
            self.broker.close()
        except AttributeError:
            # Broker was not started (probably mislaunched)
            pass

        self.log.info('Finished cleaning spawned subprocesses.')


def makeParser():
    """Create the SCOOP module arguments parser."""
    # TODO: Add environment variable (all + selection)
    parser = argparse.ArgumentParser(
        description="Starts a parallel program using SCOOP.",
        prog="{0} -m scoop".format(sys.executable),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--hosts', '--host',
                       help="The list of hosts. The first host will execute "
                            "the origin. (default is 127.0.0.1)",
                       metavar="Address",
                       nargs='*')
    group.add_argument('--hostfile',
                       help="The hostfile name",
                       metavar="FileName")
    parser.add_argument('--path', '-p',
                        help="The path to the executable on remote hosts "
                             "(default is local directory)",
                        default=os.getcwd())
    parser.add_argument('--nice',
                        type=int,
                        metavar="NiceLevel",
                        help="*nix niceness level (-20 to 19) to run the "
                             "executable")
    parser.add_argument('--verbose', '-v',
                        action='count',
                        help="Verbosity level of this launch script (-vv for "
                             "more)",
                        default=1)
    parser.add_argument('--quiet', '-q',
                        action='store_true')
    parser.add_argument('--log',
                        help="The file to log the output. (default is stdout)",
                        default=None,
                        metavar="FileName")
    parser.add_argument('-n',
                        help="Total number of workers to launch on the hosts. "
                             "Workers are spawned sequentially over the hosts. "
                             "(ie. -n 3 with 2 hosts will spawn 2 workers on "
                             "the first host and 1 on the second.) (default: "
                             "Number of CPUs on current machine)",
                        type=int,
                        metavar="NumberOfWorkers")
    parser.add_argument('--tunnel',
                        help="Activate ssh tunnels to route toward the broker "
                             "sockets over remote connections (may eliminate "
                             "routing problems and activate encryption but "
                             "slows down communications)",
                        action='store_true')
    parser.add_argument('--broker-hostname',
                        nargs=1,
                        help="The externally routable broker hostname / ip "
                             "(defaults to the local hostname)",
                        metavar="Address")
    parser.add_argument('--python-interpreter',
                        nargs=1,
                        help="The python interpreter executable with which to "
                             "execute the script",
                        default=[sys.executable],
                        metavar="Path")
    parser.add_argument('--pythonpath',
                        nargs=1,
                        help="The PYTHONPATH environment variable (default is "
                             "current PYTHONPATH)",
                        default=[os.environ.get('PYTHONPATH', '')])
    parser.add_argument('--debug',
                        help=argparse.SUPPRESS,
                        action='store_true')
    parser.add_argument('--profile',
                        help=("Turn on the profiling. SCOOP will call "
                        "cProfile.run on the executable for every worker and"
                        " will produce files in directory profile/ named "
                        "workerX where X is the number of the worker."),
                        action='store_true')
    parser.add_argument('executable',
                        nargs='?',
                        help='The executable to start with SCOOP')
    parser.add_argument('args',
                        nargs=argparse.REMAINDER,
                        help='The arguments to pass to the executable',
                        default=[],
                        metavar="args")
    return parser


def main():
    """Execution of the SCOOP module. Parses its command-line arguments and
    launch needed resources."""
    # Generate a argparse parser and parse the command-line arguments
    parser = makeParser()
    args = parser.parse_args()

    # Get a list of resources to launch worker(s) on
    hosts = utils.getHosts(args.hostfile, args.hosts)
    if args.n:
        n = args.n
    else:
        n = utils.getWorkerQte(hosts)
    assert n > 0, ("Scoop couldn't determine the number of worker to start.\n"
                   "Use the '-n' flag to set it manually.")
    if not args.broker_hostname:
        args.broker_hostname = [utils.brokerHostname(hosts)]

    # Launch SCOOP
    scoopApp = ScoopApp(hosts, n, args.verbose if not args.quiet else 0,
                        args.python_interpreter,
                        args.broker_hostname[0],
                        args.executable, args.args, args.tunnel,
                        args.log, args.path,
                        args.debug, args.nice,
                        utils.getEnv(), args.profile,
                        args.pythonpath[0])

    rootTaskExitCode = False
    try:
        rootTaskExitCode = scoopApp.run()
    except Exception as e:
        logging.error('Error while launching SCOOP subprocesses:')
        logging.error(traceback.format_exc())
    finally:
        scoopApp.close()

    # Exit with the proper exit code
    if rootTaskExitCode:
        sys.exit(rootTaskExitCode)


if __name__ == "__main__":
    main()
