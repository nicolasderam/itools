# -*- coding: UTF-8 -*-
# Copyright (C) 2005-2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2006-2007 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2007-2008 Henry Obein <henry@itaapy.com>
# Copyright (C) 2008 David Versmisse <david.versmisse@itaapy.com>
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
from copy import copy
from types import FunctionType, MethodType
from urllib import unquote
from warnings import warn

# Import from itools
from itools.http import HTTPServer
from itools.http import ClientError, NotModified, Forbidden, NotFound, Conflict
from itools.http import NotImplemented, MethodNotAllowed, Unauthorized
from itools.http import set_response
from itools.i18n import init_language_selector
from itools.log import log_error, log_warning, register_logger
from itools.uri import Reference
from context import Context, set_context, del_context, select_language
from context import WebLogger
from exceptions import FormError
from views import BaseView


class WebServer(HTTPServer):

    access_log = None
    event_log = None

    database = None


    def __init__(self, root, access_log=None, event_log=None):
        super(WebServer, self).__init__(access_log)
        # The application's root
        self.root = root
        # Logging
        register_logger(WebLogger(log_file=event_log), 'itools.web')


    #######################################################################
    # Stage 0: Initialize the context
    #######################################################################
    def init_context(self, context):
        # (1) Initialize the response status to None, it will be changed
        # through the request handling process.
        context.status = None

        # (2) The server, the data root and the authenticated user
        context.server = self
        context.root = self.root

        # (3) The authenticated user
        self.find_user(context)

        # (4) The Site Root
        self.find_site_root(context)

        # (5) Keep the context
        set_context(context)


    def find_user(self, context):
        context.user = None

        # (1) Read the id/auth cookie
        cookie = context.get_cookie('__ac')
        if cookie is None:
            return

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
            return

        # (2) Get the user resource and authenticate
        user = context.root.get_user(username)
        if user is not None and user.authenticate(password):
            context.user = user


    def find_site_root(self, context):
        """This method may be overriden to support virtual hosting.
        """
        context.site_root = self.root


    ########################################################################
    # Request handling: main functions
    ########################################################################
    def listen(self, address, port):
        # Language negotiation
        init_language_selector(select_language)

        # Add handlers
        HTTPServer.listen(self, address, port)
        self.add_handler('/', self.path_callback)
        self.add_handler('*', self.star_callback)


    def path_callback(self, soup_message, path):
        # (1) Get the class that will handle the request
        method_name = soup_message.get_method()
        method = methods.get(method_name)
        # 501 Not Implemented
        if method is None:
            log_warning('Unexpected "%s" HTTP method' % method_name,
                        domain='itools.web')
            return set_response(soup_message, 501)

        # If path is null => 400 Bad Request
        if path is None:
            log_warning('Unexpected HTTP path (null)', domain='itools.web')
            return set_response(soup_message, 400)

        # (2) Initialize the context
        # XXX This try/except can be removed if its body contains no bug
        # anymore
        try:
            context = Context(soup_message, path)
            self.init_context(context)
        except Exception:
            log_error('Internal error', domain='itools.web')
            return set_response(soup_message, 500)

        # (3) Pass control to the Get method class
        try:
            method.handle_request(self, context)
        except Exception:
            log_error('Failed to handle request', domain='itools.web')
            set_response(soup_message, 500)
        finally:
            del_context()


    def star_callback(self, soup_message, path):
        """This method is called for the special "*" request URI, which means
        the request concerns the server itself, and not any particular
        resource.

        Currently this feature is only supported for the OPTIONS request
        method:

          OPTIONS * HTTP/1.1
        """
        method = soup_message.get_method()
        if method != 'OPTIONS':
            soup_message.set_status(405)
            soup_message.set_header('Allow', 'OPTIONS')
            return

        known_methods = methods.keys()
        soup_message.set_status(200)
        soup_message.set_header('Allow', ','.join(known_methods))



###########################################################################
# The Request Methods
###########################################################################

status2name = {
    401: 'http_unauthorized',
    403: 'http_forbidden',
    404: 'http_not_found',
    405: 'http_method_not_allowed',
    409: 'http_conflict'}


def find_view_by_method(server, context):
    """Associating an uncommon HTTP or WebDAV method to a special view.
    method "PUT" -> view "http_put" <instance of BaseView>
    """
    method_name = context.method
    view_name = "http_%s" % method_name.lower()
    context.view = context.resource.get_view(view_name)
    if context.view is None:
        raise NotImplemented, 'method "%s" is not implemented' % method_name


class RequestMethod(object):

    @classmethod
    def find_resource(cls, server, context):
        """Sets 'context.resource' to the requested resource if it exists.

        Otherwise sets 'context.status' to 404 (not found error) and
        'context.resource' to the latest resource in the path that does exist.
        """
        # We start at the sire-root
        root = context.site_root
        path = copy(context.path)
        path.startswith_slash = False

        # Found
        resource = root.get_resource(path, soft=True)
        if resource is not None:
            context.resource = resource
            return

        # Not Found
        while resource is None:
            path = path[:-1]
            resource = root.get_resource(path, soft=True)
        context.resource = resource
        raise NotFound


    @classmethod
    def find_view(cls, server, context):
        query = context.uri.query
        context.view = context.resource.get_view(context.view_name, query)
        if context.view is None:
            raise NotFound


    @classmethod
    def check_access(cls, server, context):
        """Tell whether the user is allowed to access the view on the
        resource.
        """
        user = context.user
        resource = context.resource
        view = context.view

        # Get the check-point
        ac = resource.get_access_control()
        if ac.is_access_allowed(user, resource, view):
            return

        # Unauthorized (401)
        if user is None:
            raise Unauthorized

        # Forbidden (403)
        raise Forbidden


    @classmethod
    def check_method(cls, server, context, method_name=None):
        if method_name is None:
            method_name = context.method
        # Get the method
        view = context.view
        method = getattr(view, method_name, None)
        if method is None:
            message = '%s has no "%s" method' % (view, method_name)
            raise NotImplemented, message
        context.view_method = method


    @classmethod
    def check_cache(cls, server, context):
        """Implement cache if your method supports it.
        Most methods don't, hence the default implementation.
        """
        pass


    @classmethod
    def check_conditions(cls, server, context):
        """Check conditions to match before the response can be processed:
        resource, state, request headers...
        """
        pass


    @classmethod
    def check_transaction(cls, server, context):
        """Return True if your method is supposed to change the state.
        """
        raise NotImplementedError


    @classmethod
    def commit_transaction(cls, server, context):
        database = server.database
        # Check conditions are met
        if cls.check_transaction(server, context) is False:
            database.abort_changes()
            return

        # Save changes
        try:
            database.save_changes()
        except Exception:
            cls.internal_server_error(server, context)


    @classmethod
    def set_body(cls, context):
        context.soup_message.set_status(context.status)

        body = context.entity
        if body is None:
            pass
        elif isinstance(body, Reference):
            location = context.uri.resolve(body)
            location = str(location)
            context.soup_message.set_header('Location', location)
        else:
            context.soup_message.set_response(context.content_type, body)


    @classmethod
    def internal_server_error(cls, server, context):
        log_error('Internal Server Error', domain='itools.web')
        context.status = 500
        root = context.site_root
        context.entity = root.http_internal_server_error.GET(root, context)


    @classmethod
    def handle_request(cls, server, context):
        root = context.site_root

        # (1) Find out the requested resource and view
        try:
            # The requested resource and view
            cls.find_resource(server, context)
            cls.find_view(server, context)
            # Access Control
            cls.check_access(server, context)
            # Check the request method is supported
            cls.check_method(server, context)
            # Check the client's cache
            cls.check_cache(server, context)
            # Check pre-conditions
            cls.check_conditions(server, context)
        except Unauthorized, error:
            status = error.code
            context.status = status
            context.view_name = status2name[status]
            context.view = root.get_view(context.view_name)
        except ClientError, error:
            status = error.code
            context.status = status
            context.view_name = status2name[status]
            context.view = root.get_view(context.view_name)
        except NotModified:
            context.http_not_modified()
            return

        # (2) Always deserialize the query
        resource = context.resource
        view = context.view
        try:
            context.query = view.get_query(context)
        except FormError, error:
            context.method = view.on_query_error
            context.query_error = error
        except Exception:
            cls.internal_server_error(server, context)
            context.method = None
        else:
            # GET, POST...
            context.method = getattr(view, cls.method_name)

        # (3) Render
        try:
            m = getattr(root.http_main, cls.method_name)
            context.entity = m(root, context)
        except Exception:
            cls.internal_server_error(server, context)
        else:
            # Ok: set status
            if context.status is not None:
                pass
            elif isinstance(context.entity, Reference):
                context.status = 302
            elif context.entity is None:
                context.status = 204
            else:
                context.status = 200

        # (4) Commit the transaction
        cls.commit_transaction(server, context)

        # (5) Build and return the response
        cls.set_body(context)



class GET(RequestMethod):

    method_name = 'GET'


    @classmethod
    def check_cache(cls, server, context):
        # Get the resource's modification time
        resource = context.resource
        mtime = context.view.get_mtime(resource)
        if mtime is None:
            return

        # Set the last-modified header
        mtime = mtime.replace(microsecond=0)
        context.set_header('last-modified', mtime)
        # Cache-Control: max-age=1
        # (because Apache does not cache pages with a query by default)
        context.set_header('cache-control', 'max-age=1')

        # Check for the request header If-Modified-Since
        if_modified_since = context.get_header('if-modified-since')
        if if_modified_since is None:
            return

        # Cache: check modification time
        if mtime <= if_modified_since:
            raise NotModified


    @classmethod
    def check_transaction(cls, server, context):
        # GET is not expected to change the state
        if getattr(context, 'commit', False) is True:
            # FIXME To be removed one day.
            warn("Use of 'context.commit' is strongly discouraged.")
            return True
        return False



class HEAD(GET):

    @classmethod
    def check_method(cls, server, context):
        GET.check_method(server, context, method_name='GET')



class POST(RequestMethod):

    method_name = 'POST'


    @classmethod
    def check_method(cls, server, context):
        # If there was an error, the method name always will be 'GET'
        if context.status is None:
            method_name = 'POST'
        else:
            method_name = 'GET'
        RequestMethod.check_method(server, context, method_name=method_name)


    @classmethod
    def check_transaction(cls, server, context):
        return getattr(context, 'commit', True) and context.status < 400



class OPTIONS(RequestMethod):

    @classmethod
    def handle_request(cls, server, context):
        root = context.site_root

        known_methods = methods.keys()
        allowed = []

        # (1) Find out the requested resource and view
        try:
            cls.find_resource(server, context)
            cls.find_view(server, context)
        except ClientError, error:
            status = error.code
            context.status = status
            context.view_name = status2name[status]
            context.view = root.get_view(context.view_name)
        else:
            # Check methods supported by the view
            resource = context.resource
            view = context.view
            for method_name in known_methods:
                # Search on the resource's view
                method = getattr(view, method_name, None)
                if method is not None:
                    allowed.append(method_name)
                    continue
                # Search on the resource itself
                # PUT -> "put" view instance
                view_name = "http_%s" % method_name.lower()
                http_view = getattr(resource, view_name, None)
                if isinstance(http_view, BaseView):
                    if getattr(http_view, method_name, None) is not None:
                        allowed.append(method_name)
            # OPTIONS is built-in
            allowed.append('OPTIONS')
            # DELETE is unsupported at the root
            if context.path == '/':
                allowed.remove('DELETE')

        # (2) Render
        context.set_header('allow', ','.join(allowed))
        context.entity = None
        context.status = 200

        # (3) Build and return the response
        context.soup_message.set_status(context.status)
        cls.set_body(context)



class PUT(RequestMethod):
    """The client must send a correct "If-Unmodified-Since" header to be
       authorized to PUT.
    """

    method_name = 'PUT'


    @classmethod
    def find_view(cls, server, context):
        find_view_by_method(server, context)


    @classmethod
    def check_conditions(cls, server, context):
        """The resource is not locked, the request must have a correct
           "If-Unmodified-Since" header.
        """
        if_unmodified_since = context.get_header('If-Unmodified-Since')
        if if_unmodified_since is None:
            raise Conflict
        mtime = context.resource.get_mtime().replace(microsecond=0)
        if mtime > if_unmodified_since:
            raise Conflict


    @classmethod
    def check_transaction(cls, server, context):
        return getattr(context, 'commit', True) and context.status < 400


    @classmethod
    def set_body(cls, context):
        super(PUT, cls).set_body(context)

        # Set the Last-Modified header (if possible)
        mtime = context.resource.get_mtime()
        if mtime is None:
            return
        mtime = mtime.replace(microsecond=0)
        context.set_header('Last-Modified', mtime)



class DELETE(RequestMethod):

    method_name = 'DELETE'


    @classmethod
    def find_view(cls, server, context):
        # Look for the "delete" view
        return find_view_by_method(server, context)


    @classmethod
    def check_conditions(cls, server, context):
        resource = context.resource
        parent = resource.parent
        # The root cannot delete itself
        if parent is None:
            raise MethodNotAllowed


    @classmethod
    def check_transaction(cls, server, context):
        return getattr(context, 'commit', True) and context.status < 400



###########################################################################
# Registry
###########################################################################

methods = {}


def register_method(method, method_handler):
    methods[method] = method_handler


register_method('GET', GET)
register_method('HEAD', HEAD)
register_method('POST', POST)
register_method('OPTIONS', OPTIONS)
register_method('PUT', PUT)
register_method('DELETE', DELETE)
