"""Sphinx configuration for the GradCafe Analytics project."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / 'src'
MODULE2_PATH = PROJECT_ROOT.parent / 'module_2'

sys.path.insert(0, str(SRC_PATH))
sys.path.insert(0, str(MODULE2_PATH))

# pylint: disable=invalid-name,redefined-builtin

project = 'GradCafe Analytics'
copyright = '2025, Joe Hawes'
author = 'Joe Hawes'
release = '1.0'

extensions = ['sphinx.ext.autodoc', 'sphinx.ext.napoleon', 'sphinx_rtd_theme']

templates_path = ['_templates']
exclude_patterns: list[str] = []

# -- Options for HTML output -------------------------------------------------

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'show-inheritance': True,
}

autodoc_typehints = 'description'
