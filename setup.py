from setuptools import setup, find_packages
from distutils.util import convert_path
import os, sys

if sys.version_info[:2] < (2, 6):
    raise RuntimeError("Python version 2.6, 2.7 or >= 3.2 required.")

CLASSIFIERS = """\
Development Status :: 4 - Beta
Intended Audience :: Science/Research
Intended Audience :: Developers
License :: OSI Approved :: GNU Affero General Public License v3
Programming Language :: Python
Programming Language :: Python :: 2
Programming Language :: Python :: 2.6
Programming Language :: Python :: 2.7
Topic :: Software Development
Topic :: Software Development :: Build Tools
Topic :: Scientific/Engineering
Operating System :: Microsoft :: Windows
Operating System :: POSIX
Operating System :: Unix
Operating System :: MacOS
"""
                    
LONG_DESCRIPTION = ["This is a pythonic simple yet complete system logger.",
                    "It allows logging simultaneously to two streams, the first one is the system standard output by default and the second one is designated to be set to a file.",
                    "In addition, pysimplelog allows text colouring and attributes when the stream allows it.",]
DESCRIPTION      = [ LONG_DESCRIPTION[0] ]

# get version
main_ns = {}
ver_path = convert_path('__init__.py')
with open(ver_path) as ver_file:
    exec(ver_file.read(), main_ns)
#main_ns['__version__'] = '0.1.0'  


metadata = dict(name = 'pysimplelog',
                packages=["pysimplelog"],
                package_dir={'pysimplelog': '.'},
                version= main_ns['__version__'] ,
                author="Bachir AOUN",
                author_email="bachir.aoun@e-aoun.com",
                description = "\n".join(DESCRIPTION),
                long_description = "\n".join(LONG_DESCRIPTION),
                url = "http://bachiraoun.github.io/pysimplelog/",
                download_url = "https://github.com/bachiraoun/simplelog",
                license = 'GNU',
                classifiers=[_f for _f in CLASSIFIERS.split('\n') if _f],
                platforms = ["Windows", "Linux", "Mac OS-X", "Unix"], )

# setup              
setup(**metadata)

