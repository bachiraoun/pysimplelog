"""
This is a pythonic simple yet complete system logger. It allows logging simultaneously 
to two streams, the first one is the system standard output by default and the second 
one is designated to be set to a file. In addition, pysimplelog is text colouring 
and attributes enabled when the stream allows it.
                    

Installation guide:
===================
pysimplelog is a pure python 2.7.x module that needs no particular installation. 
One can either fork pysimplelog's `github repository 
<https://github.com/bachiraoun/pysimplelog/>`_ and copy the 
package to python's site-packages or use pip as the following:


.. code-block:: console
    
    
        pip install pysimplelog
"""

try:
    from .__pkginfo__ import __version__, __author__, __email__, __onlinedoc__, __repository__, __pypi__
    from .SimpleLog import Logger, SingleLogger 
except:
    from __pkginfo__ import __version__, __author__, __email__, __onlinedoc__, __repository__, __pypi__
    from SimpleLog import Logger, SingleLogger 

    
def get_version():
    """Get pysimplelog's version number."""
    return __version__ 

def get_author():
    """Get pysimplelog's author's name."""
    return __author__     
 
def get_email():
    """Get pysimplelog's author's email."""
    return __email__   
    
def get_doc():
    """Get pysimplelog's official online documentation link."""
    return __onlinedoc__       
    
def get_repository():
    """Get pysimplelog's official online repository link."""
    return __repository__        
    
def get_pypi():
    """Get pysimplelog pypi's link."""
    return __pypi__   
