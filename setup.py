#!/usr/bin/env python

from setuptools import setup

import scoop
import sys

# Backports installation
extraPackages = []
if sys.version_info[0] == 2 and sys.version_info[1] < 7:
    extraPackages = ['scoop.backports']


setup(name='scoop',
      version=scoop.__revision__,
      description='Scalable COncurrent Operations in Python',
      long_description=open('README.txt').read(),
      author='SCOOP Development Team',
      author_email='scoop-users@googlegroups.com',
      url='http://scoop.googlecode.com',
      download_url='http://code.google.com/p/scoop/downloads/list',
      install_requires=['greenlet>=0.3.4',
                        'pyzmq>=2.2.0',
                        'argparse>=1.1'],
      packages=['scoop',
                'scoop.bootstrap',
                'scoop.launch',
                'scoop.broker'] + extraPackages,
      platforms=['any'],
      keywords=['distributed algorithms',
                'parallel programming',
                'Concurrency',
                'Cluster programming',
                'greenlet',
                'zmq',],
      license='LGPL',
      classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: Education',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)',
        'Programming Language :: Python',
        'Topic :: Scientific/Engineering',
        'Topic :: Software Development',
        ],
     )
