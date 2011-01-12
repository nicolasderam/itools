# -*- coding: UTF-8 -*-
# Copyright (C) 2005-2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2007 Sylvain Taverne <sylvain@itaapy.com>
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
from access import AccessControl
from app import WebApplication
from context import WebContext, WebLogger
from exceptions import FormError
from fields import boolean_field, choice_field, email_field, file_field
from fields import hidden_field, input_field, integer_field
from fields import multiple_choice_field, password_field, readonly_field
from fields import text_field, textarea_field
from fields import make_stl_template
from messages import INFO, ERROR, MSG_MISSING_OR_INVALID
from resources import Resource, Root, VirtualRoot
from ui import UI
from views import view_type, view, stl_view


__all__ = [
    'WebApplication',
    'AccessControl',
    'WebContext',
    'WebLogger',
    'UI',
    # Model
    'Resource',
    'VirtualRoot',
    'Root',
    # View-Controller
    'view_type',
    'view',
    'stl_view',
    # Fields
    'boolean_field',
    'choice_field',
    'email_field',
    'file_field',
    'hidden_field',
    'input_field',
    'integer_field',
    'multiple_choice_field',
    'password_field',
    'readonly_field',
    'text_field',
    'textarea_field',
    # Exceptions
    'FormError',
    # Messages
    'INFO',
    'ERROR',
    'MSG_MISSING_OR_INVALID',
    # Utilities
    'make_stl_template',
    ]
