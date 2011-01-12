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
from thread import get_ident, allocate_lock

# Import from pytz
from pytz import timezone

# Import from itools
from itools.core import freeze, lazy, local_tz, utc
from itools.datatypes import String
from itools.http import get_type, Entity
from itools.http import Cookie, SetCookieDataType
from itools.http import HTTPContext
from itools.i18n import AcceptLanguageType, format_datetime
from itools.log import Logger
from itools.uri import decode_query, get_reference, Path
from exceptions import FormError
from messages import ERROR



class Context(HTTPContext):

    user = None
    resource = None
    status = None


    def __init__(self, soup_message, path):
        HTTPContext.__init__(self, soup_message, path)

        # Set 'web_path' and 'web_view_name'
        # Split the path into path and method ("a/b/c/;view")
        path = self.path
        name = path.get_name()
        if name and name[0] == ';':
            self.web_path = path[:-1]
            self.web_view_name = name[1:]
        else:
            self.web_path = path
            self.web_view_name = None

        # Cookies
        self.cookies = {}

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
        site_root = self.site_root
        return '/%s' % site_root.get_pathto(resource)


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
        for key, value in self.get_form().items():
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
    def get_query_value(self, name, type=String, default=None):
        """Returns the value for the given name from the query.  Useful for
        POST requests.
        """
        form = self.uri.query
        return get_form_value(form, name, type, default)


    def get_form_value(self, name, type=String, default=None):
        form = self.get_form()
        return get_form_value(form, name, type, default)


    def get_form_keys(self):
        return self.get_form().keys()


    #######################################################################
    # Cookies
    #######################################################################
    def get_cookie(self, name, datatype=None):
        value = None
        if name in self.cookies:
            # Case 1: the cookie was set in this request
            value = self.cookies[name]
        else:
            # Case 2: read the cookie from the request
            cookies = self.get_header('cookie')
            if cookies:
                cookie = cookies.get(name)
                if cookie:
                    value = cookie.value

        if datatype is None:
            return value

        # Deserialize
        if value is None:
            return datatype.get_default()
        value = datatype.decode(value)
        if not datatype.is_valid(value):
            raise ValueError, "Invalid cookie value"
        return value


    def set_cookie(self, name, value, **kw):
        self.cookies[name] = value
        # libsoup
        cookie = Cookie(value, **kw)
        cookie = SetCookieDataType.encode({name: cookie})
        self.soup_message.append_header('Set-Cookie', cookie)


    def del_cookie(self, name):
        self.cookies[name] = None
        # libsoup
        expires = 'Wed, 31-Dec-97 23:59:59 GMT'
        cookie = Cookie('deleted', expires=expires, max_age='0')
        cookie = SetCookieDataType.encode({name: cookie})
        self.soup_message.append_header('Set-Cookie', cookie)


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


###########################################################################
# One context per thread
###########################################################################
contexts = {}
contexts_lock = allocate_lock()


def set_context(context):
    ident = get_ident()

    contexts_lock.acquire()
    try:
        contexts[ident] = context
    finally:
        contexts_lock.release()


def get_context():
    return contexts.get(get_ident())


def del_context():
    ident = get_ident()

    contexts_lock.acquire()
    try:
        del contexts[ident]
    finally:
        contexts_lock.release()



#######################################################################
# Internationalization
#######################################################################
def select_language(languages):
    accept = get_context().accept_language
    return accept.select_language(languages)


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

