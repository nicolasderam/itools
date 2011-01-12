# -*- coding: UTF-8 -*-
# Copyright (C) 2005-2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2007 Hervé Cauwelier <herve@itaapy.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Import from itools
from catalog import Catalog, make_catalog, CatalogAware
from catalog import SearchResults
from queries import AllQuery, NotQuery, StartQuery, TextQuery
from queries import RangeQuery, PhraseQuery, AndQuery, OrQuery
from registry import get_register_fields, register_field
from ro import ROGitDatabase
from rw import GitDatabase, make_git_database, check_database


__all__ = [
    # Database
    'ROGitDatabase',
    'GitDatabase',
    'make_git_database',
    'check_database',
    'get_register_fields',
    'register_field',
    # Xapian
    'make_catalog',
    'Catalog',
    'CatalogAware',
    'SearchResults',
    # Queries
    'RangeQuery',
    'PhraseQuery',
    'AndQuery',
    'OrQuery',
    'AllQuery',
    'NotQuery',
    'StartQuery',
    'TextQuery']
