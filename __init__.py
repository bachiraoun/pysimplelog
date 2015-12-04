try:
    from .__pkginfo__ import __version__, __author__
    from .SimpleLog import Logger 
except:
    from __pkginfo__ import __version__, __author__
    from SimpleLog import Logger 

    
