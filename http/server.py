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
from time import strftime
from datetime import timedelta

# Import from itools
from app import Application
from context import HTTPContext
from exceptions import HTTPError
from soup import SoupServer
from itools.log import Logger, register_logger, log_info



class HTTPServer(SoupServer):

    # The default application says "hello"
    app = Application()
    context_class = HTTPContext


    def __init__(self, access_log=None):
        SoupServer.__init__(self)

        # The logger
        logger = AccessLogger(log_file=access_log)
        logger.launch_rotate(timedelta(weeks=3))
        register_logger(logger, 'itools.web_access')


    def log_access(self, host, request_line, status_code, body_length):
        now = strftime('%d/%b/%Y:%H:%M:%S')
        message = '%s - - [%s] "%s" %d %d\n' % (host, now, request_line,
                                                status_code, body_length)
        log_info(message, domain='itools.web_access')


    def listen(self, address, port):
        SoupServer.listen(self, address, port)
        address = address if address is not None else '*'
        print 'Listen %s:%d' % (address, port)


    def stop(self):
        SoupServer.stop(self)
        if self.access_log:
            self.access_log_file.close()


    #######################################################################
    # Callbacks
    #######################################################################
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

        methods = self.app.known_methods
        soup_message.set_status(200)
        soup_message.set_header('Allow', ','.join(methods))


    def path_callback(self, soup_message, path):
        try:
            self._path_callback(soup_message, path)
        except Exception:
            self.log_error()
            soup_message.set_status(500)
            soup_message.set_body('text/plain', '500 Internal Server Error')


    def _path_callback(self, soup_message, path):
        context = self.context_class(soup_message, path)

        # 501 Not Implemented
        app = self.app
        method_name = context.get_method()
        if method_name not in app.known_methods:
            return context.set_response(501)

        # Step 1: Host
        app.get_host(context)

        # Step 2: Resource
        resource = app.get_resource(context)
        if resource is None:
            # 404 Not Found
            return context.set_response(404)
        if type(resource) is str:
            # 307 Temporary redirect
            context.set_status(307)
            context.set_header('Location', resource)
            return
        context.resource = resource

        # 405 Method Not Allowed
        allowed_methods = app.get_allowed_methods(resource)
        if method_name not in allowed_methods:
            context.set_response(405)
            context.set_header('allow', ','.join(allowed_methods))
            return

        # Step 3: User
        context.user = app.get_user(context)

        # Continue
        method_name = app.known_methods[method_name]
        method = getattr(app, method_name)
        try:
            method(context)
        except HTTPError, exception:
            self.log_error()
            status = exception.code
            context.set_response(status)




class AccessLogger(Logger):
    def format(self, domain, level, message):
        return message


###########################################################################
# For testing purposes
###########################################################################
if __name__ == '__main__':
    server = HTTPServer()
    print 'Start server..'
    server.start()
