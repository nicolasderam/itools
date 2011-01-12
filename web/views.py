# -*- coding: UTF-8 -*-
# Copyright (C) 2008 Henry Obein <henry@itaapy.com>
# Copyright (C) 2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
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
from itools.core import freeze, thingy_type, thingy, thingy_property
from itools.core import thingy_lazy_property
from itools.stl import stl
from itools.uri import decode_query, get_reference
from exceptions import FormError
from fields import hidden_field


class view_type(thingy_type):

    def __new__(mcs, class_name, bases, dict):
        # Add the 'field_names' attribute, if not explicitly defined
        if 'field_names' not in dict:
            field_names = []

            # Inherit from the base classes
            for base in bases:
                for name in getattr(base, 'field_names', []):
                    if name in dict and dict[name] is None:
                        continue
                    if name not in field_names:
                        field_names.append(name)

            # Add this class fields
            for name, value in dict.iteritems():
                if (type(value) is thingy_type
                    and issubclass(value, hidden_field)
                    and name not in field_names):
                    field_names.append(name)

            # Ok
            dict['field_names'] = field_names

        # Add the name to fields that miss them
        for name in dict['field_names']:
            field = dict.get(name)
            if type(field) is thingy_type and field.name is None:
                field.name = name

        # Subviews
        if 'subviews' not in dict:
            subviews = []
            for base in bases:
                for name in getattr(base, 'subviews', []):
                    if name in dict and dict[name] is None:
                        continue
                    if name not in subviews:
                        subviews.append(name)
            for name, value in dict.iteritems():
                if name == 'view':
                    continue
                if type(value) is view_type and name not in subviews:
                    subviews.append(name)
            dict['subviews'] = subviews

        # Make and return the class
        return thingy_type.__new__(mcs, class_name, bases, dict)



class view(thingy):

    __metaclass__ = view_type


    # Access Control
    access = False

    # Bindings
    resource = None
    view = None

    def __init__(self, **kw):
        for key in kw:
            setattr(self, key, kw[key])


    @thingy_lazy_property
    def context(self):
        return self.resource.context


    @thingy_lazy_property
    def root_view(self):
        if self.view is None:
            return self
        return self.view.root_view


    #######################################################################
    # Schema
    #######################################################################
    def get_field_names(self):
        # Check for specific fields
        action = self.action_name
        if action:
            fields = getattr(self, '%s_fields' % action, None)
            if fields is not None:
                return fields

        # Default
        return self.field_names


    def get_field(self, name):
        return getattr(self, name)


    def get_fields(self):
        for name in self.get_field_names():
            field = getattr(self, name, None)
            if field is None:
                field = self.get_field(name)
            yield field


    def cook(self, method):
        context = self.context
        get_from_query = context.query.get
        get_from_form = context.form.get

        # Cook fields
        error = False
        for field in self.get_fields():
            # Cook the field
            if field.source == 'query':
                field = field(view=self, getter=get_from_query)
                field.cook()
            elif method == 'post':
                field = field(view=self, getter=get_from_form)
                field.cook()
                if field.error:
                    error = True
            else:
                field = field(view=self, getter=get_from_query)
                field.cook(required=False)
            # Assign the bound & cooked field to the view
            setattr(self, field.name, field)

        # Cook subviews
        for name in self.subviews:
            view = getattr(self, name)
            if view is not None:
                view = view(resource=self.resource, view=self)
                view.cook(method)
                setattr(self, name, view)

        if error:
            raise FormError


    #######################################################################
    # Caching
    def get_mtime(self, resource):
        return None


    #######################################################################
    # Request methods
    def http_get(self):
        raise NotImplementedError


    def http_post(self):
        raise NotImplementedError


    #######################################################################
    # View's metadata
    view_title = None


    #######################################################################
    # Canonical URI for search engines
    # "language" is by default because too widespreaded
    canonical_query_parameters = freeze(['language'])


    def get_canonical_uri(self, context):
        """Return the same URI stripped from redundant view name, if already
        the default, and query parameters not affecting the resource
        representation.
        Search engines will keep this sole URI when crawling different
        combinations of this view.
        """
        uri = get_reference(context.uri)
        query = uri.query
        # Remove the view name if default
        view_name = context.view_name
        if view_name:
            resource = context.resource
            if view_name == resource.default_view_name:
                uri = uri.resolve2('..')
        # Remove noise from query parameters
        canonical_query_parameters = self.canonical_query_parameters
        for parameter in query.keys():
            if parameter not in canonical_query_parameters:
                del query[parameter]
        uri.query = query
        return uri


    #######################################################################
    # Posts
    #######################################################################
    @thingy_lazy_property
    def action_name(self):
        """Default function to retrieve the name of the action from a form
        """
        context = self.context
        action = context.form.get('action')
        if action is None:
            return None

        action = 'action_%s' % action
        # Save the query of the action into context.form_query
        if '?' in action:
            action, query = action.split('?')
            # Deserialize query using action specific schema
            schema = getattr(self, '%s_query_schema' % action, None)
            context.form_query = decode_query(query, schema)

        return action


    @thingy_property
    def action_method(self):
        name = self.action_name or 'action'
        return getattr(self, name, None)


    def http_post(self):
        method = self.action_method
        if method is None:
            msg = "the '%s' method is not defined"
            raise NotImplementedError, msg % self.action_name
        return method()



class stl_view(view):

    show = True
    template = None


    def get_template(self):
        template = self.template

        # Case 1: None
        if template is None:
            msg = "%s is missing the 'template' variable"
            raise NotImplementedError, msg % repr(self.__class__)

        # Case 2: events
        if type(template) is list:
            return template

        # Case 3: str
        if type(template) is str:
            return self.context.get_template(template).events

        # Case 4: type error
        msg = 'unexpected "%s" type for the template attribute'
        raise TypeError, msg % type(template)


    def render(self):
        if not self.show:
            return None

        events = self.get_template()
        return stl(events=events, namespace=self)


    def http_get(self):
        context = self.context
        # Get the namespace
        body = self.render()
        context.ok_wrap('text/html', body)

