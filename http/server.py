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
from itools.i18n import init_language_selector
from itools.log import Logger, register_logger
from itools.log import log_info, log_error, log_warning
from itools.uri import Path
from context import set_context, set_response, select_language
from soup import SoupServer



class HTTPServer(SoupServer):

    def __init__(self, access_log=None, event_log=None):
        SoupServer.__init__(self)

        # Mounts
        self.mounts = [None, {}]

        # Access log
        logger = AccessLogger(log_file=access_log)
        logger.launch_rotate(timedelta(weeks=3))
        register_logger(logger, 'itools.web_access')
        # Events log
        if event_log is not None:
            register_logger(Logger(log_file=event_log), 'itools.http')


    def log_access(self, host, request_line, status_code, body_length):
        now = strftime('%d/%b/%Y:%H:%M:%S')
        message = '%s - - [%s] "%s" %d %d\n' % (host, now, request_line,
                                                status_code, body_length)
        log_info(message, domain='itools.web_access')


    def listen(self, address, port):
        # Language negotiation
        init_language_selector(select_language)

        # Add handlers
        SoupServer.listen(self, address, port)
        self.add_handler('/', self.path_callback)
        self.add_handler('*', self.star_callback)

        # Run
        address = address if address is not None else '*'
        print 'Listen %s:%d' % (address, port)


    def stop(self):
        SoupServer.stop(self)
        if self.access_log:
            self.access_log_file.close()


    #######################################################################
    # Mounts
    #######################################################################
    def mount(self, path, mount):
        if type(path) is str:
            path = Path(path)

        aux = self.mounts
        for name in path:
            aux = aux[1].setdefault(name, [None, {}])
        aux[0] = mount


    def get_mount(self, path):
        mount, aux = self.mounts
        for name in path:
            aux = aux.get(name)
            if not aux:
                return mount
            if aux[0]:
                mount = aux[0]
            aux = aux[1]

        return mount


    #######################################################################
    # Callbacks
    #######################################################################
    known_methods = [
        'OPTIONS', 'GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'LOCK', 'UNLOCK']


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

        methods = self.known_methods
        soup_message.set_status(200)
        soup_message.set_header('Allow', ','.join(methods))


    def path_callback(self, soup_message, path):
        # 501 Not Implemented
        method = soup_message.get_method()
        if method not in self.known_methods:
            log_warning('Unexpected "%s" HTTP method' % method,
                        domain='itools.http')
            return set_response(soup_message, 501)

        # Mount
        path = Path(path)
        mount = self.get_mount(path)
        if mount is None:
            return set_response(soup_message, 404)

        # New context
        try:
            context = mount.get_context(soup_message, path)
        except Exception:
            log_error('Failed to make context instance', domain='itools.http')
            return set_response(soup_message, 500)

        # Handle request
        set_context(context)
        try:
            mount.handle_request(context)
        except Exception:
            log_error('Failed to handle request', domain='itools.http')
            set_response(soup_message, 500)
        finally:
            set_context(None)



class AccessLogger(Logger):
    def format(self, domain, level, message):
        return message
