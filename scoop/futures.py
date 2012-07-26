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
import os
from collections import namedtuple
import scoop
from scoop._types import Future, NotStartedProperly
from scoop import _control as control

# Constants stated by PEP 3148 (http://www.python.org/dev/peps/pep-3148/#module-functions)
FIRST_COMPLETED = 'FIRST_COMPLETED'
FIRST_EXCEPTION = 'FIRST_EXCEPTION'
ALL_COMPLETED = 'ALL_COMPLETED'
_AS_COMPLETED = '_AS_COMPLETED'

# This is the greenlet for running the controller logic.
_controller = None

def _startup(rootFuture, *args, **kargs):
    """Initializes the SCOOP environment.
    
    :param rootFuture: Any callable object (function or class object with *__call__*
        method); this object will be called once and allows the use of parallel
        calls inside this object.
    :param args: A tuple of positional arguments that will be passed to the
        callable object. 
    :param kargs: A dictionary of additional keyword arguments that will be
        passed to the callable object. 
        
    :returns: The result of the root Future.
    
    Be sure to launch your root Future using this method."""
    import greenlet
    global _controller
    _controller = greenlet.greenlet(control.runController)
    try:
        result = _controller.switch(rootFuture, *args, **kargs)
    except scoop._comm.Shutdown:
        result = None
    if scoop.DEBUG:
        import pickle
        try:
            os.makedirs("debug")
        except:
            pass
        with open("debug/" + scoop.WORKER_NAME.decode() + "-" +
                scoop.BROKER_NAME.decode(), 'wb') as f:
            pickle.dump(control.debug_stats, f)
        with open("debug/" + scoop.WORKER_NAME.decode() + "-QUEUE", 'wb') as f:
            pickle.dump(control.QueueLength, f)
    return result

def _mapFuture(callable, *iterables, **kargs):
    """Similar to the built-in map function, but each of its 
    iteration will spawn a separate independent parallel Future that will run 
    either locally or remotely as `callable(*args, **kargs)`.
    
    :param callable: Any callable object (function or class object with *__call__*
        method); this object will be called to execute each Future. 
    :param iterables: A tuple of iterable objects; each will be zipped
        to form an iterable of arguments tuples that will be passed to the
        callable object as a separate Future. 
    :param kargs: A dictionary of additional keyword arguments that will be 
        passed to the callable object. 
        
    :returns: A list of Future objects, each corresponding to an iteration of
        map.
    
    On return, the Futures are pending execution locally, but may also be
    transfered remotely depending on global load. Execution may be carried on
    with any further computations. To retrieve the map results, you need to
    either wait for or join with the spawned Futures. See functions waitAny,
    waitAll, or joinAll. Alternatively, You may also use functions mapWait or
    mapJoin that will wait or join before returning."""
    childrenList = []
    for args in zip(*iterables):
        childrenList.append(submit(callable, *args, **kargs))
    return childrenList

def map(func, *iterables, **kargs):
    """Equivalent to 
    `map(func, \*iterables, ...) <http://docs.python.org/library/functions.html#map>`_ 
    but *func* is executed asynchronously
    and several calls to func may be made concurrently. The returned iterator
    raises a TimeoutError if *__next__()* is called and the result isn't available
    after timeout seconds from the original call to *map()* [To be done in future
    version of SCOOP]. If timeout is not
    specified or None then there is no limit to the wait time. If a call raises
    an exception then that exception will be raised when its value is retrieved
    from the iterator.
    
    :param func: Any callable object (function or class object with *__call__*
        method); this object will be called to execute the Futures. 
    :param iterables: Iterable objects; each will be zipped to form an iterable
        of arguments tuples that will be passed to the callable object as a
        separate Future.
    :param timeout: The maximum number of seconds to wait [To be done in future 
        version of SCOOP]. If None, then there is no limit on the wait time.
    :param kargs: A dictionary of additional keyword arguments that will be 
        passed to the callable object. 
        
    :returns: A generator of map results, each corresponding to one map 
        iteration."""
    # Remove 'timeout' from kargs to be compliant with the futures API
    kargs.pop('timeout', None)
    for future in _waitAll(*_mapFuture(func, *iterables, **kargs)):
        del control.futureDict[future.id]
        yield future.resultValue

def submit(func, *args, **kargs):
    """Submit an independent parallel :class:`scoop._types.Future` that will 
    either run locally or remotely as `func(*args, **kargs)`.
    
    :param func: Any callable object (function or class object with *__call__*
        method); this object will be called to execute the Future.
    :param args: A tuple of positional arguments that will be passed to the
        callable object.
    :param kargs: A dictionary of additional keyword arguments that will be
        passed to the callable object.
        
    :returns: A future object for retrieving the Future result.
    
    On return, the Future is pending execution locally, but may also be
    transfered remotely depending on load or on remote distributed workers. You
    may carry on with any further computations while the Future completes. Result
    retrieval is made via the ``result()`` function on the Future."""
    try:
        child = Future(control.current.id, func, *args, **kargs)
    except AttributeError:
        raise NotStartedProperly("SCOOP was not started properly.\n"
                                 "Be sure to start your program with the "
                                 "'-m scoop' parameter. You can find further "
                                 "information in the documentation.")
    control.execQueue.append(child)
    return child

def _waitAny(*children):
    """Waits on any child Future created by the calling Future.
    
    :param children: A tuple of children Future objects spawned by the calling 
        Future.
        
    :return: A generator function that iterates on futures that are done.
    
    The generator produces results of the children in a non deterministic order
    that depends on the particular parallel execution of the Futures. The
    generator returns a tuple as soon as one becomes available."""
    n = len(children)
    # check for available results and index those unavailable
    for index, future in enumerate(children):
        if future.exceptionValue != None:
            raise future.exceptionValue
        if future.resultValue != None:
            yield future
            n -= 1
        else:
            future.index = index
    future = control.current
    while n > 0:
        # wait for remaining results; switch to controller
        future.stopWatch.halt()
        childFuture = _controller.switch(future)
        future.stopWatch.resume()
        if childFuture.exceptionValue:
            raise childFuture.exceptionValue
        yield childFuture
        n -= 1

def _waitAll(*children):
    """Wait on all child futures specified by a tuple of previously created 
       Future.
    
    :param children: A tuple of children Future objects spawned by the calling 
        Future.
        
    :return: A generator function that iterates on Future results.
    
    The generator produces results in the order that they are specified by
    the children argument. Because Futures are executed in a non deterministic
    order, the generator may have to wait for the last result to become
    available before it can produce an output. See waitAny for an alternative
    option."""
    for index, future in enumerate(children):
        for f in _waitAny(future):
            yield f

def wait(fs, timeout=None, return_when=ALL_COMPLETED):
    """Wait for the futures in the given sequence to complete.
    
    :param fs: The sequence of Futures (possibly created by another instance) to
        wait upon.
    :param timeout: The maximum number of seconds to wait [To be done in future
        version of SCOOP]. If None, then there
        is no limit on the wait time.
    :param return_when: Indicates when this function should return. The options
        are:

        ===============   ================================================
        FIRST_COMPLETED   Return when any future finishes or is cancelled.
        FIRST_EXCEPTION   Return when any future finishes by raising an
                          exception. If no future raises an exception then
                          it is equivalent to ALL_COMPLETED.
        ALL_COMPLETED     Return when all futures finish or are cancelled.
        ===============   ================================================
        
    :return: A named 2-tuple of sets. The first set, named 'done', contains the
        futures that completed (is finished or cancelled) before the wait
        completed. The second set, named 'not_done', contains uncompleted
        futures."""
    DoneAndNotDoneFutures = namedtuple('DoneAndNotDoneFutures', 'done not_done')
    if return_when == FIRST_COMPLETED:
        for future in _waitAny(*fs):
            break
    elif return_when == ALL_COMPLETED:
        for future in _waitAll(*fs):
            pass
    elif return_when == FIRST_EXCEPTION:
        for future in _waitAny(*fs):
            if future.exceptionValue != None:
                break
    done = set(f for f in fs if f.done())
    not_done = set(fs) - done
    return DoneAndNotDoneFutures(done, not_done)

def as_completed(fs, timeout=None):
    """An iterator over the given futures that yields each as it completes.

    :param fs: The sequence of Futures (possibly created by another instance) to
        wait upon.
    :param timeout: The maximum number of seconds to wait [To be done in future
        version of SCOOP]. If None, then there
        is no limit on the wait time.

    :return: An iterator that yields the given Futures as they complete
        (finished or cancelled).
    """
    return _waitAny(*fs)

def _join(child):
    """This private function is for joining the current Future with one of its
    child Future.
    
    :param child: A child Future object spawned by the calling Future.
    
    :return: The result of the child Future.
    
    Only one Future can be specified. The function returns a single
    corresponding result as soon as it becomes available."""
    for future in _waitAny(child):
        del control.futureDict[future.id]
        return future.resultValue

def _joinAll(*children):
    """This private function is for joining the current Future with all of the
    children Futures specified in a tuple.
    
    :param children: A tuple of children Future objects spawned by the calling
        Future.
        
    :return: A list of corresponding results for the children Futures.
    
    This function will wait for the completion of all specified child Futures
    before returning to the caller."""
    return [_join(future) for future in _waitAll(*children)]

def shutdown(wait=True):
    """This function is here for compatibility with `futures` (PEP 3148).
    
    :param wait: Unapplied parameter."""
    pass

def _scan(func, args):
    if len(args) == 2:
        return _join(submit(func, args[0], args[1]))
    elif len(args) == 3:
        return _join(submit(func, args[2], _join(submit(func, args[0],
                                                args[1]))))
    else:
        return _join(submit(func, _scan(func, args[0:len(args)//2]),
            _scan(func, args[len(args)//2:len(args) + 1])))
