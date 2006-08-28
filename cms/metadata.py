# -*- coding: ISO-8859-1 -*-
# Copyright (C) 2003-2005 Juan David Ib��ez Palomar <jdavid@itaapy.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

# Import from the Standard Library
import base64
import urllib

# Import from itools
from itools.datatypes import (DataType, String, Boolean, Email,
                              Tokens, QName, XML)
from itools import schemas



class Password(DataType):

    @staticmethod
    def decode(data):
        data = urllib.unquote(data)
        return base64.decodestring(data)


    @staticmethod
    def encode(value):
        value = base64.encodestring(value)
        return urllib.quote(value)



class Record(object):

    default = []

    @classmethod
    def encode(cls, value):
        lines = []
        for key, value in value.items():
            prefix, local_name = key
            datatype = schemas.get_datatype(key)
            value = datatype.encode(value)
            value = XML.encode(value)
            qname = QName.encode(key)
            lines.append('\n    <%s>%s</%s>' % (qname, value, qname))
        return ''.join(lines) + '\n'



class Enumerate(String):

    options = []

    @classmethod
    def get_options(cls):
        """Returns a copy of options list of dictionaries."""
        return [dict(option) for option in cls.options]


    @classmethod
    def get_namespace(cls, name):
        options = cls.get_options()
        for option in options:
            option['selected'] = option['name'] == name
        return options


    @classmethod
    def get_value(cls, name, default=None):
        for option in cls.options:
            if option['name'] == name:
                return option['value']

        return default



class Schema(schemas.base.Schema):

    class_uri = 'http://xml.ikaaro.org/namespaces/metadata'
    class_prefix = 'ikaaro'


    datatypes = {
##        'format': String,
##        'version': String,
##        'owner': String,
        # Workflow
        'wf_transition': Record,
##        'name': String,
##        'user': String,
##        'comments': Unicode,
        # History
        'history': Record,
        # Users
        'email': Email,
        'password': Password,
        'user_theme': String(default='aruni'), # XXX unused
        'user_language': String(default='en'),
        'website_is_open': Boolean(default=False),
        'website_languages': Tokens(default=('en',)),
        # Future
        'order': Tokens(default=()),
        }


schemas.register_schema(Schema)

