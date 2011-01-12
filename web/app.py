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

# Import from the Standard Library
from base64 import decodestring
from binascii import Error as BinasciiError
from urllib import unquote

# Import from itools
from itools.handlers import BaseDatabase


# These are the values that 'WebApplication.find_resource' may return
MOVED = 301
REDIRECT = 307 # 302 in HTTP 1.0
UNAUTHORIZED = 401
FORBIDDEN = 403
NOT_FOUND = 404
GONE = 410 # Not available in HTTP 1.0


class WebApplication(object):

    database = BaseDatabase()


    def handle_request(self, context):
        # Step 1: Host
        self.find_host(context)

        # Step 2: Resource
        action = self.find_resource(context)
        if action == NOT_FOUND:
            return context.set_response(404) # 404 Not Found
        elif action == GONE:
            return context.set_response(410) # 410 Gone
        elif action == REDIRECT:
            context.set_status(307) # 307 Temporary redirect
            return context.set_header('Location', context.resource)
        elif action == MOVED:
            context.set_status(301) # 301 Moved Permanently
            return context.set_header('Location', context.resource)

        # 405 Method Not Allowed
        allowed_methods = self.get_allowed_methods(context)
        if context.method not in allowed_methods:
            context.set_response(405)
            return context.set_header('allow', ','.join(allowed_methods))

        # Step 3: User (authentication)
        self.find_user(context)

        # Step 4: Access Control
        action = self.check_access(context)
        if action == UNAUTHORIZED:
            return context.set_response(401) # 401 Unauthorized
        elif action == FORBIDDEN:
            return context.set_response(403) # 403 Forbidden

        # Continue
        method = self.known_methods[context.method]
        method = getattr(self, method)
        try:
            method(context)
        except HTTPError, exception:
            self.log_error()
            status = exception.code
            context.set_response(status)


    #######################################################################
    # Resource
    #######################################################################
    def find_host(self, context):
        pass


    def find_resource(self, context):
        """Sets 'context.resource' to the requested resource if it exists.

        Otherwise sets 'context.status' to 404 (not found error) and
        'context.resource' to the latest resource in the path that does exist.
        """
        # Split the path so '/a/b/c/;view' becomes ('/a/b/c', 'view')
        name = context.path.get_name()
        if name and name[0] == ';':
            path = context.path[:-1]
            view = name[1:]
        else:
            path = context.path
            view = None

        # Get the resource
        resource = self.get_resource(path, soft=True)
        if resource is None:
            return NOT_FOUND
        context.resource = resource

        # Get the view
        context.view = resource.get_view(view, context.query)
        if context.view is None:
            return NOT_FOUND


    #######################################################################
    # Authorization
    #######################################################################
    def get_credentials(self, context):
        # Credentials
        cookie = context.get_cookie('__ac')
        if cookie is None:
            return None

        cookie = unquote(cookie)
        # When we send:
        # Set-Cookie: __ac="deleted"; expires=Wed, 31-Dec-97 23:59:59 GMT;
        #             path=/; max-age="0"
        # to FF4, it don't delete the cookie, but continue to send
        # __ac="deleted" (not base64 encoded)
        try:
            cookie = decodestring(cookie)
        except BinasciiError:
            return
        username, password = cookie.split(':', 1)
        if username is None or password is None:
            return None

        return username, password


    def get_user(self, credentials):
        return None


    def find_user(self, context):
        credentials = self.get_credentials(context)
        if credentials is None:
            self.user = None
        else:
            self.user = self.get_user(credentials)


    def check_access(self, context):
        # Access Control
        resource = context.resource
        ac = resource.get_access_control()
        if not ac.is_access_allowed(context, resource, context.view):
            return FORBIDDEN if context.user else UNAUTHORIZED


    #######################################################################
    # Request handlers
    #######################################################################
    known_methods = {
        'OPTIONS': 'http_options',
        'GET': 'http_get',
        'HEAD': 'http_get',
        'POST': 'http_post'}


    def get_allowed_methods(self, context):
        obj = context.view or context.resource

        methods = [
            x for x in self.known_methods
            if getattr(obj, self.known_methods[x], None) ]
        methods = set(methods)
        methods.add('OPTIONS')
        # DELETE is unsupported at the root
        if obj.path == '/':
            methods.discard('DELETE')
        return methods


    def http_options(self, context):
        methods = self.get_allowed_methods(context.resource)
        context.set_status(200)
        context.set_header('Allow', ','.join(methods))


    def http_get(self, context):
        resource = context.resource
        resource.http_get(context)


    def http_post(self, context):
        resource = context.resource
        resource.http_post(context)

