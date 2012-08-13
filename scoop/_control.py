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
from __future__ import print_function
from collections import deque
import greenlet
import os
from ._types import Future, FutureId, FutureQueue
import scoop

# Set module-scope variables about this controller
# future currently running in greenlet
current = None
# dictionary of existing futures
futureDict = {}
# queue of futures pending execution
execQueue = None

if scoop.DEBUG:
    import time
    stats = {}
    QueueLength = []


def runFuture(future):
    """This is the callable greenlet for running futures."""
    if scoop.DEBUG:
        stats.setdefault(future.id,
                         {}).setdefault('start_time',
                                        []).append(time.time())
    future.waitTime = future.stopWatch.get()
    future.stopWatch.reset()
    try:
        future.resultValue = future.callable(*future.args, **future.kargs)
    except Exception as err:
        future.exceptionValue = err
    future.executionTime = future.stopWatch.get()
    assert future.done(), "callable must return a value!"

    # Set debugging informations if needed
    if scoop.DEBUG:
        t = time.time()
        stats[future.id].setdefault('end_time', []).append(t)
        stats[future.id].update({'executionTime': future.executionTime,
                                 'worker': scoop.worker,
                                 'creationTime': future.creationTime,
                                 'callable': str(future.callable.__name__)
                                 if hasattr(future.callable, '__name__')
                                 else 'No name',
                                 'parent': future.parentId})
        QueueLength.append((t, len(execQueue)))

    # Run callback, see http://www.python.org/dev/peps/pep-3148/#future-objects
    if future.parentId.worker == scoop.worker:
        for callback in future.callback:
            try:
                callback(future)
            except:
                # Ignored callback exception as stated in PEP 3148
                pass
    return future


def runController(callable, *args, **kargs):
    """This is the callable greenlet that implements the controller logic."""
    global execQueue
    # initialize and run root future
    rootId = FutureId(-1, 0)

    # initialise queue
    if execQueue is None:
        execQueue = FutureQueue()

    # launch future if origin or try to pickup a future if slave worker
    if scoop.IS_ORIGIN is True:
        future = Future(rootId, callable, *args, **kargs)
    else:
        future = execQueue.pop()

    future.greenlet = greenlet.greenlet(runFuture)
    future = future._switch(future)

    while future.parentId != rootId or \
            not future.done() or \
            scoop.IS_ORIGIN is False:
        # process future
        if future.done():
            # future is finished
            if future.id.worker != scoop.worker:
                # future is not local
                execQueue.sendResult(future)
                future = execQueue.pop()
            else:
                # future is local, parent is waiting
                if future.index is not None:
                    parent = futureDict[future.parentId]
                    if parent.exceptionValue is None:
                        future = parent._switch(future)
                    else:
                        future = execQueue.pop()
                else:
                    future = execQueue.pop()
        else:
            # future is in progress; run next future from pending execution
            # queue.
            future = execQueue.pop()

        if future.resultValue is None and future.greenlet is None:
            # initialize if the future hasn't started
            future.greenlet = greenlet.greenlet(runFuture)
            future = future._switch(future)

    execQueue.shutdown()
    if future.exceptionValue:
        raise future.exceptionValue
    # We delete the initial future from the futureDict
    if future.id in futureDict:
        del futureDict[future.id]
    return future.resultValue
