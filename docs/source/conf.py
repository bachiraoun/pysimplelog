# -*- coding: utf-8 -*-
#
# pysimplelog documentation build configuration file, created by
# sphinx-quickstart on Mon Sep 12 22:54:29 2016.
#
# This file is execfile()d with the current directory set to its
# containing dir.

import os
import sys
import datetime

# -- Path setup ---------------------------------------------------------------
# Make the pysimplelog package importable from docs/source by inserting the
# repo root (two levels up from this file) onto sys.path.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# -- General configuration ------------------------------------------------

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.githubpages',
]

templates_path = ['_templates']
source_suffix = '.rst'
master_doc = 'index'

# General information about the project.
project = u'pysimplelog'
copyright = u'2016\u2013%d, Bachir Aoun' % datetime.date.today().year
author = u'Bachir Aoun'

# Version
try:
    from pysimplelog import __version__ as VER
    from pysimplelog import SimpleLog
    if SimpleLog.__doc__:
        SimpleLog.__doc__ = SimpleLog.__doc__.replace("%AUTO_VERSION", VER)
except Exception as _e:
    print(
        "pysimplelog import failed during doc build: %s" % _e,
        file=sys.stderr,
    )
    VER = "unknown"

version = VER
release = VER

rst_epilog = """
.. |VERSION| replace:: %s
""" % (VER,)

language = 'en'
exclude_patterns = []
pygments_style = 'sphinx'
todo_include_todos = False
autodoc_member_order = 'bysource'

# -- Options for HTML output ----------------------------------------------

html_theme = 'alabaster'
html_theme_options = {
    'github_user': "bachiraoun",
    'github_repo': "pysimplelog",
    'github_banner': True,
    'show_powered_by': False,
}

html_title = u'pysimplelog v%s' % VER
html_short_title = html_title
project_name = html_title

html_static_path = ['_static']

html_sidebars = {
    '**': ['about.html', 'navigation.html', 'searchbox.html'],
}

html_show_sourcelink = False
html_show_sphinx = False
html_show_copyright = True

htmlhelp_basename = 'pysimplelogdoc'

# -- Options for LaTeX output ---------------------------------------------

latex_elements = {}
latex_documents = [
    (master_doc, 'pysimplelog.tex', u'pysimplelog Documentation',
     u'Bachir Aoun', 'manual'),
]

# -- Options for manual page output ---------------------------------------

man_pages = [
    (master_doc, 'pysimplelog', u'pysimplelog Documentation',
     [author], 1)
]

# -- Options for Texinfo output -------------------------------------------

texinfo_documents = [
    (master_doc, 'pysimplelog', u'pysimplelog Documentation',
     author, 'pysimplelog',
     'A complete logging system with enqueue, bind(), catch(), and multi-sink routing.',
     'Miscellaneous'),
]
