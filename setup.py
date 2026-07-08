"""
This script will work from within the main package directory.

python setup.py sdist bdist_wheel
twine upload dist/pysimplelog-...



"""
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup
try:
    from distutils.util import convert_path
except ImportError:
    # distutils removed in Python 3.12+; for single-component paths
    # (no directory separators) the conversion is a no-op on all platforms
    def convert_path(pathname):
        return pathname
import os, sys

# set package path and name
PACKAGE_PATH = '.'
PACKAGE_NAME = 'pysimplelog'

# check python version
if sys.version_info[:2] < (3, 6):
    raise RuntimeError("Python version 3.6 and above is required.")

# automatically create MANIFEST.in
commands = [# include MANIFEST.in
            '# include this file, to ensure we can recreate source distributions',
            'include MANIFEST.in'
            # exclude all .log files
            '\n# exclude all logs',
            'global-exclude *.log',
            # exclude all other non necessary files
            '\n# exclude all other non necessary files ',
            'global-exclude .project',
            'global-exclude .pydevproject',
            # exclude all of the subversion metadata
            '\n# exclude all of the subversion metadata',
            'global-exclude *.svn*',
            'global-exclude .svn/*',
            'global-exclude *.git*',
            'global-exclude .git/*',
            # include all LICENCE files
            '\n# include all license files found',
            'global-include ./*LICENSE.*',
            # include all README files
            '\n# include all readme files found',
            'global-include ./*README.*',
            'global-include ./*readme.*']
with open('MANIFEST.in','w') as fd:
    for l in commands:
        fd.write(l)
        fd.write('\n')

# declare classifiers
CLASSIFIERS = """\
Development Status :: 5 - Production/Stable
Intended Audience :: Science/Research
Intended Audience :: Developers
License :: OSI Approved :: GNU Affero General Public License v3
Programming Language :: Python
Programming Language :: Python :: 3
Programming Language :: Python :: 3.6
Programming Language :: Python :: 3.7
Programming Language :: Python :: 3.8
Programming Language :: Python :: 3.9
Programming Language :: Python :: 3.10
Programming Language :: Python :: 3.11
Programming Language :: Python :: 3.12
Topic :: Software Development
Topic :: Software Development :: Build Tools
Topic :: Scientific/Engineering
Operating System :: Microsoft :: Windows
Operating System :: POSIX
Operating System :: Unix
Operating System :: MacOS
"""

# create descriptions
LONG_DESCRIPTION = ["This is a pythonic simple yet complete system logger.",
                    "It allows logging simultaneously to stdout, a rotating log file, and any number of user-supplied sinks.",
                    "In addition, pysimplelog is text colouring and attributes enabled when the stream allows it.",]
DESCRIPTION      = [ LONG_DESCRIPTION[0] ]

## get package info
import re as _re
PACKAGE_INFO = {}
infoPath = convert_path('__pkginfo__.py')
with open(infoPath) as fd:
    _src = fd.read()
for _m in _re.finditer(r"^(__\w+__)\s*=\s*['\""]([^'\""]*)['\"""]" , _src, _re.MULTILINE):
    PACKAGE_INFO[_m.group(1)] = _m.group(2)


# create meta data
metadata = dict(name = PACKAGE_NAME,
                packages=[PACKAGE_NAME],
                package_dir={PACKAGE_NAME: '.'},
                version= PACKAGE_INFO['__version__'] ,
                author="Bachir AOUN",
                author_email="bachir.aoun@e-aoun.com",
                description = "\n".join(DESCRIPTION),
                long_description = "\n".join(LONG_DESCRIPTION),
                url = "https://bachiraoun.github.io/pysimplelog/",
                download_url = "https://github.com/bachiraoun/pysimplelog",
                license = 'GNU Affero General Public License v3',
                classifiers=[_f for _f in CLASSIFIERS.split('\n') if _f],
                platforms = ["Windows", "Linux", "Mac OS-X", "Unix"], )

# setup
setup(**metadata)
