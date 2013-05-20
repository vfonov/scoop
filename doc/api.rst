API Reference
=============

.. note:

    Please note that the current version of SCOOP doesn't support timeout. Its
    support has been scheduled in a future version.

Futures module
--------------

The following methods are part of the futures module. They can be accessed like
so::
    
    from scoop import futures
    
    results = futures.map(func, data)
    futureObject = futures.submit(func, arg)
    ...
    
More informations are available in the :doc:`usage` document.

.. automodule:: scoop.futures
   :members:
   
Future class
------------

The :meth:`~scoop.futures.submit` function returns a
:class:`~scoop._types.Future` object.
This instance possess the following methods.
   
.. autoclass:: scoop._types.Future
   :members:

Shared module
-------------

This module provides the :meth:`~scoop.shared.setConst` and 
:meth:`~scoop.shared.getConst` functions allowing arbitrary object sharing
between futures.

.. automodule:: scoop.shared
   :members:


SCOOP Constants and objects
---------------------------

The following objects are available to a program that was launched using SCOOP.

.. note::
    Please note that using these is considered as advanced usage. You should not rely on these for other purposes than debugging.

====================    ====================================================================
Constants               Description
====================    ====================================================================
scoop.IS_ORIGIN         Boolean value. True if current instance is the root worker.
scoop.WORKER_NAME       String value. Name of the current instance (deprecated).
scoop.BROKER_NAME       String value. Name of the broker to which this instance is attached (deprecated).
scoop.BROKER_ADDRESS    String value. Address of the socket communicating work information.
scoop.META_ADDRESS      String value. Address of the socket communicating meta information.
scoop.SIZE              Integer value. Size of the current worker pool.
scoop.DEBUG             Boolean value. True if debug mode is enabled, false otherwise.
scoop.IS_RUNNING        Boolean value. True if scoop is currently running, false otherwise.
scoop.worker            2-tuple. Unique identifier of the current instance in the pool.
scoop.logger            Logger object. Provides log formatting and redirection facilities. See the `official documentation <http://docs.python.org/2/library/logging.html#logging.Logger>`_ for more informations on its usage.
====================    ====================================================================
