# -*- coding: ISO-8859-1 -*-
# Copyright (C) 2005 Nicolas OYEZ <noyez@itaapy.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307  USA


class LanguageTag(object):


    def decode(cls, value):
        res = value.split('-', 1)
        if len(res) < 2:
            return (res[0].lower(), None)
        else:
            return (res[0].lower(), res[1].upper())
            
    decode = classmethod(decode)


    def encode(cls, value):
        language, locality = value
        if locality is None:
            return language.lower()
        return '%s-%s' % (language.lower(), locality.upper())

    encode = classmethod(encode)


    def to_unicode(cls, value):
        return unicode('-'.join([i for i in value if i != None]))

    to_unicode = classmethod(to_unicode)
    
