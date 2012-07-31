Install
=======

Requirements
------------

The software requirements for SCOOP are as follows:

* `Python <http://www.python.org/>`_ >= 2.6 or >= 3.2
* `Greenlet <http://pypi.python.org/pypi/greenlet>`_ >= 0.3.4
* `PyZMQ <http://www.zeromq.org/bindings:python>`_ and 
  `libzmq <http://www.zeromq.org/>`_ >= 2.2.0
* :program:`ssh` for remote execution

Installation
------------
    
To install SCOOP and its other dependencies, use 
`pip <http://www.pip-installer.org/en/latest/index.html>`_ as such::

    pip install scoop

.. note::

	If you don't already have `libzmq <http://www.zeromq.org/>`_ installed in a
	default library location, please visit the 
	`PyZMQ installation page <http://www.zeromq.org/bindings:python/>`_ for 
	further assistance.

Remote usage
~~~~~~~~~~~~
    
Because remote host connection needs to be done without a prompt, you must use 
ssh keys to allow passwordless authentication.
You should make sure that your public ssh key is contained in the ``~/.ssh/authorized_keys2`` 
file on the remote systems (Refer to the `ssh manual <http://www.openbsd.org/cgi-bin/man.cgi?query=ssh>`_). If you have a shared :file:`/home/` over your systems, 
you can do as such::
    
    [~]$ mkdir ~/.ssh; cd ~/.ssh
    [.ssh]$ ssh-keygen -t dsa
    [.ssh]$ cat id_dsa.pub >> authorized_keys2
    
.. note::

    If your remote hosts needs special configuration (non-default port, some 
    specified username, etc.), you should do it in your ssh client 
    configuration file (by default ``~/.ssh/config``). Please  as to how 
    to configure and personalize your hosts connections.
