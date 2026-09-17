# SPDX-License-Identifier: Apache-2.0
"""Where the convenience packs this distribution ships live (article 9).

A directory of pack directories and nothing else: no loader here reads any of
them by name. `sayfirst instrument run --pack DIR` designates one by its path,
and `sayfirst packs list` reads this directory only to print that path back —
this file exists so `importlib.resources` resolves the directory as an
ordinary subpackage instead of a namespace package assembled from wherever it
is found on the path, which is one fewer thing a reader has to reason about.
"""
