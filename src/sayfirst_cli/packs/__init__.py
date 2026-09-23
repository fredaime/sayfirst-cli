# SPDX-License-Identifier: Apache-2.0
"""Where the convenience packs this distribution ships live (article 9).

A directory of pack directories and nothing else. `--pack NAME` designates one
of them by its name, looked up here and nowhere else, and `--pack DIR` any pack
by its path (`instrument/designation.py` is the whole of that rule);
`sayfirst packs list` reads this directory to print each name and path. This
file exists so `importlib.resources` resolves the directory as an ordinary
subpackage instead of a namespace package assembled from wherever it is found
on the path, which is one fewer thing a reader has to reason about.
"""
