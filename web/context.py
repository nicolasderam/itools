# -*- coding: UTF-8 -*-
# Copyright (C) 2005-2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2006 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2007 Henry Obein <henry@itaapy.com>
# Copyright (C) 2007 Nicolas Deram <nicolas@itaapy.com>
# Copyright (C) 2007-2008 Sylvain Taverne <sylvain@itaapy.com>
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
from datetime import datetime
from base64 import decodestring
from urllib import unquote

# Import from pytz
from pytz import timezone

# Import from itools
from itools.core import freeze, lazy, local_tz, utc
from itools.datatypes import String
from itools.http import get_type, Entity
from itools.http import HTTPContext, ClientError, get_context
from itools.i18n import AcceptLanguageType, format_datetime
from itools.log import Logger, log_warning
from itools.uri import get_reference
from exceptions import FormError
from messages import ERROR



class WebContext(HTTPContext):

    status = None

    def __init__(self, soup_message, path):
        HTTPContext.__init__(self, soup_message, path)

        # Query
        self.query_schema = {}

        # Split the path so '/a/b/c/;view' becomes ('/a/b/c', 'view')
        path = self.path
        name = path.get_name()
        if name and name[0] == ';':
            self.resource_path = path[:-1]
            self.view_name = name[1:]
        else:
            self.resource_path = path
            self.view_name = None

        # Media files (CSS, javascript)
        # Set the list of needed resources. The method we are going to
        # call may need external resources to be rendered properly, for
        # example it could need an style sheet or a javascript file to
        # be included in the html head (which it can not control). This
        # attribute lets the interface to add those resources.
        self.styles = []
        self.scripts = []


    @lazy
    def timestamp(self):
        return datetime.utcnow().replace(tzinfo=utc)


    @lazy
    def accept_language(self):
        accept_language = self.soup_message.get_header('accept-language')
        if accept_language is None:
            accept_language = ''
        return AcceptLanguageType.decode(accept_language)


    def add_style(self, *args):
        styles = self.styles
        for style in args:
            if style not in styles:
                styles.append(style)


    def add_script(self, *args):
        scripts = self.scripts
        for script in args:
            if script not in scripts:
                scripts.append(script)


    def get_link(self, resource):
        """Return a link to the given resource, from the given context.
        """
        # FIXME This method should give an error if the given resource is
        # not within the site root.
        host = self.host
        return '/%s' % host.get_pathto(resource)


    #######################################################################
    # Lazy load
    #######################################################################
    def load_accept_language(self):
        accept_language = self.get_header('Accept-Language') or ''
        return AcceptLanguageType.decode(accept_language)


    def get_host(self, hostname):
        return None


    def load_host(self):
        return self.get_host(self.hostname)


    def get_resource(self, path, soft=False):
        raise NotImplementedError


    def load_resource(self):
        resource = self.get_resource(self.resource_path, soft=True)
        if resource is None:
            raise ClientError(404)
        return resource


    def load_view(self):
        return self.resource.get_view(self.view_name, self.query)


    def get_credentials(self):
        # Credentials
        cookie = self.get_cookie('__ac')
        if cookie is None:
            return None

        try:
            cookie = unquote(cookie)
            cookie = decodestring(cookie)
            username, password = cookie.split(':', 1)
        except Exception:
            log_warning('bad authentication cookie "%s"' % cookie)
            return None

        if username is None or password is None:
            return None

        return username, password


    def get_user(self, credentials):
        return None


    def load_user(self):
        credentials = self.get_credentials()
        if credentials is None:
            return None
        return self.get_user(credentials)


    def load_access(self):
        resource = self.resource
        ac = resource.get_access_control()
        if ac.is_access_allowed(self, resource, self.view):
            return True

        # XXX Special case, we raise an error instead of returning 'False'
        self.access = False
        if self.user:
            raise ClientError(403)
        raise ClientError(401)


    #######################################################################
    # Request
    #######################################################################
    def get_request_line(self):
        return self.soup_message.get_request_line()

    def get_headers(self):
        return self.soup_message.get_headers()


    def get_header(self, name):
        name = name.lower()
        datatype = get_type(name)
        value = self.soup_message.get_header(name)
        if value is None:
            return datatype.get_default()
        return datatype.decode(value)


    def set_header(self, name, value):
        datatype = get_type(name)
        value = datatype.encode(value)
        self.soup_message.set_header(name, value)


    def get_referrer(self):
        return self.soup_message.get_header('referer')


    def get_form(self):
        if self.method in ('GET', 'HEAD'):
            return self.uri.query
        # XXX What parameters with the fields defined in the query?
        return self.body


    def set_content_type(self, content_type):
        self.content_type = content_type


    def set_content_disposition(self, disposition, filename=None):
        if filename:
            disposition = '%s; filename="%s"' % (disposition, filename)

        self.soup_message.set_header('Content-Disposition', disposition)


    #######################################################################
    # API / Status
    #######################################################################
    def http_not_modified(self):
        self.soup_message.set_status(304)


    #######################################################################
    # API / Redirect
    #######################################################################
    def come_back(self, message, goto=None, keep=freeze([]), **kw):
        """This is a handy method that builds a resource URI from some
        parameters.  It exists to make short some common patterns.
        """
        # By default we come back to the referrer
        if goto is None:
            goto = self.get_referrer()
            # Replace goto if no referrer
            if goto is None:
                goto = str(self.uri)
                if '/;' in goto:
                    goto = goto.split('/;')[0]

        if type(goto) is str:
            goto = get_reference(goto)

        # Preserve some form values
        form = {}
        for key, value in self.form.items():
            # Be robust
            if not key:
                continue
            # Omit methods
            if key[0] == ';':
                continue
            # Omit files
            if isinstance(value, tuple) and len(value) == 3:
                continue
            # Keep form field
            if (keep is True) or (key in keep):
                form[key] = value
        if form:
            goto = goto.replace(**form)
        # Translate the source message
        if message:
            text = message.gettext(**kw)
            if isinstance(message, ERROR):
                return goto.replace(error=text)
            else:
                return goto.replace(info=text)
        return goto


    #######################################################################
    # API / Forms
    #######################################################################
    def add_query_schema(self, schema):
        self.query_schema.update(schema)


    def get_query_value(self, name, type=None, default=None):
        """Returns the value for the given name from the query.  Useful for
        POST requests.
        """
        if type is None:
            type = self.query_schema.get(name, String)

        return get_form_value(self.query, name, type, default)


    def get_form_value(self, name, type=String, default=None):
        return get_form_value(self.form, name, type, default)


    def get_form_keys(self):
        return self.form.keys()


    #######################################################################
    # API / Utilities
    #######################################################################
    def format_datetime(self, datetime, tz=None):
        # 1. Build the tzinfo object
        if tz is None and self.user:
            tz = self.user.get_timezone()

        # TODO default to the local host timezone
        tzinfo = timezone(tz) if tz else local_tz

        # 2. Change datetime
        if datetime.tzinfo:
            datetime = datetime.astimezone(tzinfo)
        else:
            datetime = tzinfo.localize(datetime)

        # Ok
        return format_datetime(datetime, self.accept_language)


    def agent_is_a_robot(self):
        footprints = [
            'Ask Jeeves/Teoma', 'Bot/', 'crawler', 'Crawler',
            'freshmeat.net URI validator', 'Gigabot', 'Google',
            'LinkChecker', 'msnbot', 'Python-urllib', 'Yahoo', 'Wget',
            'Zope External Editor']

        user_agent = self.get_header('User-Agent')
        for footprint in footprints:
            if footprint in user_agent:
                return True
        return False


    def get_remote_ip(self):
        remote_ip = self.get_header('X-Forwarded-For')
        return remote_ip.split(',', 1)[0].strip() if remote_ip else None


#######################################################################
# Get from the form or query
#######################################################################
def get_form_value(form, name, type=String, default=None):
    # Figure out the default value
    if default is None:
        default = type.get_default()

    # Missing
    is_mandatory = getattr(type, 'mandatory', False)
    is_missing = form.get(name) is None
    if is_missing:
        # Mandatory: raise an error
        if is_mandatory and is_missing:
            raise FormError(missing=True)
        # Optional: return the default value
        return default

    # Multiple values
    if type.multiple:
        value = form.get(name)
        if not isinstance(value, list):
            value = [value]
        try:
            values = [ type.decode(x) for x in value ]
        except Exception:
            raise FormError(invalid=True)
        # Check the values are valid
        for value in values:
            if not type.is_valid(value):
                raise FormError(invalid=True)
        return values

    # Single value
    value = form.get(name)
    if isinstance(value, list):
        value = value[0]
    try:
        value = type.decode(value)
    except Exception:
        raise FormError(invalid=True)

    # We consider that if the type deserializes the value to None, then we
    # must use the default.
    if value is None:
        if is_mandatory:
            raise FormError(missing=True)
        return default

    # We consider a blank string to be a missing value (FIXME not reliable).
    is_blank = isinstance(value, (str, unicode)) and not value.strip()
    if is_blank:
        if is_mandatory:
            raise FormError(missing=True)
    elif not type.is_valid(value):
        raise FormError(invalid=True)
    return value



class WebLogger(Logger):

    def get_body(self):
        context = get_context()
        if context is None:
            return Logger.get_body(self)

        # The URI and user
        if context.user:
            lines = ['%s (user: %s)\n\n' % (context.uri, context.user.name)]
        else:
            lines = ['%s\n\n' % context.uri]

        # Request header
        lines.append(context.get_request_line() + '\n')
        headers = context.get_headers()
        for key, value in headers:
            lines.append('%s: %s\n' % (key, value))
        lines.append('\n')

        # Ok
        body = Logger.get_body(self)
        lines.extend(body)
        return lines

