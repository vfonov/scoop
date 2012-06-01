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
from .types import Future, FutureId, FutureQueue
import scoop

# Set module-scope variables about this controller
worker = (scoop.WORKER_NAME, scoop.BROKER_NAME) # worker task id
rank = 0                                        # rank id for next task
is_origin = scoop.IS_ORIGIN                     # is the worker the origin?
current = None                                  # task currently running in greenlet
task_dict = {}                                  # dictionary of existing tasks
execQueue = None                                # queue of tasks pending execution
if scoop.DEBUG:
    import time
    stats = {}

# This is the callable greenlet for running tasks.
def runFuture(task):
    if scoop.DEBUG:
        stats.setdefault(task.id, {}).setdefault('start_time', []).append(time.time())
    task.waitTime = task.stopWatch.get()
    task.stopWatch.reset()
    try:
        task.resultValue = task.callable(*task.args, **task.kargs)    
    except Exception as err:
        task.exceptionValue = err
    task.executionTime = task.stopWatch.get()
    assert task.done(), "callable must return a value!"
    
    # Set debugging informations if needed
    if scoop.DEBUG:
        stats[task.id].setdefault('end_time', []).append(time.time())
        stats[task.id].update({'executionTime': task.executionTime,
                               'worker': worker,
                               'creationTime': task.creationTime,
                               'callable': str(task.callable.__name__),
                               'parent': task.parentId})
    # Run callback (see http://www.python.org/dev/peps/pep-3148/#future-objects)
    for callback in task.callback:
        try: callback(task)
        except: pass # Ignored callback exception as stated in PEP 3148
    return task

# This is the callable greenlet that implements the controller logic.
def runController(callable, *args, **kargs):
    global execQueue
    # initialize and run root task
    rootId = FutureId(-1,0)
    
    # initialise queue
    if execQueue == None:
        execQueue = deque() if len(scoop.BROKER_ADDRESS) == 0  else FutureQueue()
    
    # launch task if origin or try to pickup a task if slave worker
    if is_origin == True:
        task = Future(rootId, callable, *args, **kargs)
    else:
        task = execQueue.pop()
        
    task.greenlet = greenlet.greenlet(runFuture)
    task = task._switch(task)
    
    while task.parentId != rootId or not task.done() or is_origin == False:
        # process task
        if task.done():
            # task is finished
            if task.id.worker != worker:
                # task is not local
                execQueue.sendResult(task)
                task = execQueue.pop()
            else:
                # task is local, parent is waiting
                if task.index != None:
                    parent = task_dict[task.parentId]
                    if parent.exceptionValue == None:
                        task = parent._switch(task)
                    else:
                        task = execQueue.pop()
                else:
                    execQueue.append(task)
                    task = execQueue.pop()
        else:
            # task is in progress; run next task from pending execution queue.
            task = execQueue.pop()

        if task.resultValue == None and task.greenlet == None:
            # initialize if the task hasn't started
            task.greenlet = greenlet.greenlet(runFuture)
            task = task._switch(task)

    execQueue.socket.shutdown()
    if task.exceptionValue:
        raise task.exceptionValue
    return task.resultValue
