try:
    from .__pkginfo__ import __version__, __author__, __email__, __onlinedoc__, __repository__, __pypi__
    from .SimpleLog import Logger 
except:
    from __pkginfo__ import __version__, __author__, __email__, __onlinedoc__, __repository__, __pypi__
    from SimpleLog import Logger 

    
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
