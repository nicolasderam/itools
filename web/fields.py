# -*- coding: UTF-8 -*-
# Copyright (C) 2009 Juan David Ibáñez Palomar <jdavid@itaapy.com>
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
from itools.core import freeze, guess_type
from itools.core import thingy, thingy_property, thingy_lazy_property
from itools.core import OrderedDict
from itools.datatypes import Boolean, Email, Integer, String, Unicode
from itools.gettext import MSG
from itools.stl import stl
from itools.xml import XMLParser


###########################################################################
# Utilities
###########################################################################

stl_namespaces = {
    None: 'http://www.w3.org/1999/xhtml',
    'stl': 'http://www.hforge.org/xml-namespaces/stl'}

def make_stl_template(data):
    return list(XMLParser(data, stl_namespaces))



###########################################################################
# The 'hidden_field' class is the base class for all view fields (because
# the most simple)
###########################################################################

class hidden_field(thingy):

    name = None

    datatype = String
    readonly = True
    required = False
    source = 'form' # Possible values: query & form

    # The 'getter' function is passed by the view, it is used to get the raw
    # value (from the query or from the post, it depends...)
    getter = None

    # Output values for the 'cook' method
    error = None

    # Error messages
    error_required = MSG(u'This field is required.')
    error_invalid = MSG(u'Invalid value.')


    def __init__(self, name=None, **kw):
        if name and not self.name:
            self.name = name


    #######################################################################
    # To be overriden by subclasses when a datatype is not enough
    #######################################################################
    @thingy_lazy_property
    def value(self):
        return self.datatype.get_default()


    def decode(self, raw_value):
        self.value = self.datatype.decode(raw_value)


    def is_empty(self):
        return self.datatype.is_empty(self.value)


    def is_valid(self):
        return self.datatype.is_valid(self.value)


    #######################################################################
    # The recipe
    #######################################################################
    @thingy_lazy_property
    def raw_value(self):
        value = self.getter(self.name)
        if value is None:
            return None

        return value[0] if type(value) is list else value


    def cook(self, required=None):
        if required is None:
            required = self.required

        # (1) Check raw value
        raw_value = self.raw_value
        if raw_value is None:
            if required:
                self.error = self.error_required
                return
            return

        # (2) Get the cooked value
        try:
            self.decode(raw_value)
        except Exception:
            self.error = self.error_invalid
            return

        # (3) Check it is not empty
        if self.is_empty():
            if required:
                self.error = self.error_required
                return
            return

        # (4) Validate
        if not self.is_valid():
            self.error = self.error_invalid


    #######################################################################
    # The user interface
    #######################################################################
    template = make_stl_template("""
    <input type="hidden" id="${name}" name="${name}" value="${encoded_value}"
    />""")


    def encoded_value(self):
        if self.raw_value is None:
            return self.datatype.encode(self.value)
        return self.raw_value


    def render(self):
        return stl(events=self.template, namespace=self)


###########################################################################
# Read Only field
###########################################################################

class readonly_field(hidden_field):

    template = make_stl_template("""
    <input type="hidden" id="${name}" name="${name}" value="${encoded_value}"
    /> ${title}: ${displayed}""")

    title = None
    displayed = None



###########################################################################
# Input fields
###########################################################################

class input_field(readonly_field):
    """This is the base class for all visible fields, by default a simple
    input element is used.
    """

    # First block: the field header
    template = make_stl_template("""
    <stl:block stl:if="title">
      <label for="${name}">${title}</label>
      <span stl:if="required" class="field-is-required"
        title="This field is required">*</span>
      <span stl:if="description" title="${description}">(?)</span>
      <br/>
    </stl:block>
    <span stl:if="error" class="field-error">${error}<br/></span>
    ${input}
    """)

    # Second block: the input widget (by default an input element)
    input_template = make_stl_template("""
    <input type="${type}" name="${name}" id="${name}" value="${encoded_value}"
      size="${size}" />""")

    readonly = False
    description = None
    size = None
    type = None

    def input(self):
        template = self.input_template
        if template is None:
            return None

        if type(template) is list:
            return stl(events=template, namespace=self)

        if type(template) is str:
            template = self.view.context.get_template(template)
            return stl(template, self)

        raise TypeError, 'unexepected value of type "%s"' % type(template)



class email_field(input_field):
    datatype = Email
    size = 40


class file_field(input_field):
    input_template = make_stl_template("""
    <input type="file" name="${name}" id="${name}" size="${size}" />
    <stl:block stl:if="preview"><br/><img src="${preview}" /></stl:block>
    """)

    preview = None


    def decode(self, raw_value):
        """Find out the resource class (the mimetype sent by the browser can be
        minimalistic).
        """
        filename, mimetype, body = raw_value
        # Find out the mimetype
        guessed, encoding = guess_type(filename)
        if encoding is not None:
            encoding_map = {'gzip': 'application/x-gzip',
                            'bzip2': 'application/x-bzip2'}
            if encoding in encoding_map:
                mimetype = encoding_map[encoding]
        elif guessed is not None:
            mimetype = guessed

        self.filename = filename
        self.mimetype = mimetype
        self.body = body


    def is_empty(self):
        return False



class integer_field(input_field):
    datatype = Integer



class password_field(input_field):
    type = 'password'

    def encoded_value(self):
        return self.view.resource.context.query.get(self.name)



class text_field(input_field):
    datatype = Unicode
    size = 40



class textarea_field(input_field):
    datatype = Unicode

    input_template = make_stl_template("""
    <textarea name="${name}" id="${name}" rows="${rows}" cols="${cols}"
    >${value}</textarea>
    """)

    rows = 5
    cols = 60



class boolean_field(input_field):

    datatype = Boolean

    input_template = make_stl_template("""
    <input type="radio" name="${name}" id="${name}" value="1" checked="${yes}"
      /> ${yes_label}
    <input type="radio" name="${name}" value="0" checked="${no}"/> ${no_label}
    """)

    yes_label = MSG(u'Yes')
    no_label = MSG(u'No')


    def yes(self):
        return self.value is True


    def no(self):
        return self.value is False



class choice_field(input_field):

    select_template = make_stl_template("""
    <select name="${name}" id="${name}" size="${size}" class="${css}">
      <option stl:repeat="option options" value="${option/value}"
        selected="${option/selected}">${option/title}</option>
    </select>""")

    radio_template = make_stl_template("""
    <stl:block stl:repeat="option options">
      <input type="radio" id="${name}-${option/value}" name="${name}"
        value="${option/value}" checked="${option/selected}" />
      <label for="${name}-${option/value}">${option/title}</label>
      <br stl:if="not oneline" />
    </stl:block>""")


    mode = 'select'
    css = None
    oneline = False


    @thingy_property
    def input_template(self):
        try:
            return getattr(self, '%s_template' % self.mode)
        except AttributeError:
            raise ValueError, "unkown '%s' mode" % self.mode


    values = OrderedDict()


    def is_valid(self):
        return self.value in self.values


    def options(self):
        value = self.value
        return [
            {'value': k, 'title': v.get('title', v), 'selected': k == value }
            for k, v in self.values.iteritems() ]



class multiple_choice_field(choice_field):

    select_template = make_stl_template("""
    <select name="${name}" id="${name}" multiple="multiple" size="${size}"
      class="${css}">
      <option stl:repeat="option options" value="${option/value}"
        selected="${option/selected}">${option/title}</option>
    </select>""")


    checkbox_template = make_stl_template("""
    <stl:block stl:repeat="option options">
      <input type="checkbox" id="${name}-${option/value}" name="${name}"
        value="${option/value}" checked="${option/selected}" />
      <label for="${name}-${option/value}">${option/title}</label>
      <br stl:if="not oneline" />
    </stl:block>""")


    default = freeze([])


    @thingy_lazy_property
    def raw_value(self):
        value = self.getter(self.name)
        if value is None:
            return []

        return value if type(value) is list else [value]


    def decode(self, raw_value):
        self.value = [ self.datatype.decode(x) for x in raw_value ]


    def is_valid(self):
        for value in self.value:
            if value not in self.values:
                return False
        return True


    def is_empty(self):
        return len(self.value) == 0


    def options(self):
        value = self.value
        return [
            {'value': k, 'title': v.get('title', v), 'selected': k in value }
            for k, v in self.values.iteritems() ]

