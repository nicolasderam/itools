# -*- coding: UTF-8 -*-
# Copyright (C) 2006 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2007 Henry Obein <henry@itaapy.com>
# Copyright (C) 2007 Sylvain Taverne <sylvain@itaapy.com>
# Copyright (C) 2007-2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
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
from os.path import dirname
from subprocess import CalledProcessError

# Import from itools
from itools.core import get_pipe, lazy, send_subprocess
from itools.datatypes import ISODateTime
from itools.fs import lfs
from itools.handlers import Folder
from catalog import Catalog, make_catalog
from registry import get_register_fields
from ro import ROGitDatabase



MSG_URI_IS_BUSY = 'The "%s" URI is busy.'



class GitDatabase(ROGitDatabase):

    def __init__(self, path, size_min, size_max):
        super(GitDatabase, self).__init__(path, size_min, size_max)

        # The "git add" arguments
        self.added = set()
        self.changed = set()
        self.has_changed = False

        # The resources that been added, removed, changed and moved can be
        # represented as a set of two element tuples.  But we implement this
        # with two dictionaries (old2new/new2old), to be able to access any
        # "tuple" by either value.  With the empty tuple we represent the
        # absence of change.
        #
        #  Tuple        Description                Implementation
        #  -----------  -------------------------  -------------------
        #  ()           nothing has been done yet  {}/{}
        #  (None, 'b')  resource 'b' added         {}/{'b':None}
        #  ('b', None)  resource 'b' removed       {'b':None}/{}
        #  ('b', 'b')   resource 'b' changed       {'b':'b'}/{'b':'b'}
        #  ('b', 'c')   resource 'b' moved to 'c'  {'b':'c'}/{'c':'b'}
        #
        # In real life, every value is either None or an absolute path (as a
        # byte stringi).  For the description that follows, we use the tuples
        # as a compact representation.
        #
        # There are four operations:
        #
        #  A(b)   - add "b"
        #  R(b)   - remove "b"
        #  C(b)   - change "b"
        #  M(b,c) - move "b" to "c"
        #
        # Then, the algebra is:
        #
        # ()        -> A(b) -> (None, 'b')
        # (b, None) -> A(b) -> (b, b)
        # (None, b) -> A(b) -> error
        # (b, b)    -> A(b) -> error
        # (b, c)    -> A(b) -> (b, b), (None, c) FIXME Is this correct?
        #
        # TODO Finish
        #
        self.resources_old2new = {}
        self.resources_new2old = {}


    @lazy
    def catalog(self):
        path = '%s/catalog' % self.path
        return Catalog(path, get_register_fields())


    #######################################################################
    # Layer 0: handlers
    #######################################################################
    def is_phantom(self, handler):
        # Phantom handlers are "new"
        if handler.timestamp or not handler.dirty:
            return False
        # They are attached to this database, but they are not in the cache
        return handler.database is self and handler.key not in self.cache


    def has_handler(self, key):
        key = self.normalize_key(key)

        # A new file/directory is only in added
        n = len(key)
        for f_key in self.added:
            if f_key[:n] == key and (len(f_key) == n or f_key[n] == '/'):
                return True

        # Normal case
        return super(GitDatabase, self).has_handler(key)


    def _get_handler(self, key, cls=None, soft=False):
        # A hook to handle the new directories
        base = key + '/'
        n = len(base)
        for f_key in self.added:
            if f_key[:n] == base:
                if cls is None:
                    cls = Folder
                return cls(key, database=self)

        # The other files
        return super(GitDatabase, self)._get_handler(key, cls, soft)


    def set_handler(self, key, handler):
        if isinstance(handler, Folder):
            raise ValueError, 'unexpected folder (only files can be "set")'

        if handler.key is not None:
            raise ValueError, 'only new files can be added, try to clone first'

        key = self.normalize_key(key)
        if self._get_handler(key, soft=True) is not None:
            raise RuntimeError, MSG_URI_IS_BUSY % key

        self.push_handler(key, handler)
        self.added.add(key)
        # Changed
        self.has_changed = True


    def del_handler(self, key):
        key = self.normalize_key(key)

        # Case 1: file
        handler = self._get_handler(key)
        if not isinstance(handler, Folder):
            self._discard_handler(key)
            if key in self.added:
                self.added.remove(key)
            else:
                self.changed.discard(key)
                self.fs.remove(key)
            # Changed
            self.has_changed = True
            return

        # Case 2: folder
        base = key + '/'
        for k in self.added.copy():
            if k.startswith(base):
                self._discard_handler(k)
                self.added.discard(k)

        for k in self.changed.copy():
            if k.startswith(base):
                self._discard_handler(k)
                self.changed.discard(k)

        if self.fs.exists(key):
            self.fs.remove(key)

        # Changed
        self.has_changed = True


    def touch_handler(self, key, handler=None):
        key = self.normalize_key(key)

        # Useful for the phantoms
        if handler is None:
            handler = self._get_handler(key)

        # The phantoms become real files
        if self.is_phantom(handler):
            self.cache[key] = handler
            self.added.add(key)
            self.has_changed = True
            return

        if handler.dirty is None:
            # Load the handler if needed
            if handler.timestamp is None:
                handler.load_state()
            # Mark the handler as dirty
            handler.dirty = datetime.now()
            # Update database state (XXX Should we do this?)
            self.changed.add(key)
            # Changed
            self.has_changed = True


    def get_handler_names(self, key):
        key = self.normalize_key(key)

        # On the filesystem
        names = super(GitDatabase, self).get_handler_names(key)
        names = set(names)

        # In added
        base = key + '/'
        n = len(base)
        for f_key in self.added:
            if f_key[:n] == base:
                name = f_key[n:].split('/', 1)[0]
                names.add(name)

        # Remove .git
        if key == "":
            names.discard('.git')

        return list(names)


    def copy_handler(self, source, target):
        source = self.normalize_key(source)
        target = self.normalize_key(target)

        # The trivial case
        if source == target:
            return

        # Check the target is free
        if self._get_handler(target, soft=True) is not None:
            raise RuntimeError, MSG_URI_IS_BUSY % target

        handler = self._get_handler(source)

        # Folder
        if isinstance(handler, Folder):
            fs = self.fs
            for name in handler.get_handler_names():
                self.copy_handler(fs.resolve2(source, name),
                                  fs.resolve2(target, name))
        # File
        else:
            handler = handler.clone()
            self.push_handler(target, handler)
            self.added.add(target)

        # Changed
        self.has_changed = True


    def move_handler(self, source, target):
        source = self.normalize_key(source)
        target = self.normalize_key(target)

        # The trivial case
        if source == target:
            return

        # Check the target is free
        if self._get_handler(target, soft=True) is not None:
            raise RuntimeError, MSG_URI_IS_BUSY % target

        # Go
        fs = self.fs
        cache = self.cache

        # Case 1: file
        handler = self._get_handler(source)
        if not isinstance(handler, Folder):
            if fs.exists(source):
                fs.move(source, target)

            # Remove source
            self.added.discard(source)
            self.changed.discard(source)
            del cache[source]
            # Add target
            self.push_handler(target, handler)
            self.added.add(target)

            # Changed
            self.has_changed = True
            return

        # Case 2: Folder
        n = len(source)
        base = source + '/'
        for key in self.added.copy():
            if key.startswith(base):
                new_key = '%s%s' % (target, key[n:])
                handler = cache.pop(key)
                self.push_handler(new_key, handler)
                self.added.remove(key)
                self.added.add(new_key)

        for key in self.changed.copy():
            if key.startswith(base):
                new_key = '%s%s' % (target, key[n:])
                handler = cache.pop(key)
                self.push_handler(new_key, handler)
                self.changed.remove(key)

        if fs.exists(source):
            fs.move(source, target)
        for path in fs.traverse(target):
            if not fs.is_folder(path):
                path = fs.get_relative_path(path)
                self.added.add(path)

        # Changed
        self.has_changed = True


    #######################################################################
    # Layer 1: resources
    #######################################################################
    def remove_resource(self, resource):
        old2new = self.resources_old2new
        new2old = self.resources_new2old

        for x in resource.traverse_resources():
            path = str(x.get_canonical_path())
            old2new[path] = None
            new2old.pop(path, None)


    def add_resource(self, resource):
        old2new = self.resources_old2new
        new2old = self.resources_new2old

        # Catalog
        for x in resource.traverse_resources():
            path = str(x.get_canonical_path())
            new2old[path] = None


    def change_resource(self, resource):
        old2new = self.resources_old2new
        new2old = self.resources_new2old

        path = str(resource.get_canonical_path())
        if path in old2new and not old2new[path]:
            raise ValueError, 'cannot change a resource that has been removed'

        if path not in new2old:
            old2new[path] = path
            new2old[path] = path


    def move_resource(self, source, new_path):
        old2new = self.resources_old2new
        new2old = self.resources_new2old

        old_path = source.get_canonical_path()
        for x in source.traverse_resources():
            source_path = x.get_canonical_path()
            target_path = new_path.resolve2(old_path.get_pathto(source_path))

            source_path = str(source_path)
            target_path = str(target_path)
            if source_path in old2new and not old2new[source_path]:
                err = 'cannot move a resource that has been removed'
                raise ValueError, err

            source_path = new2old.pop(source_path, source_path)
            if source_path:
                old2new[source_path] = target_path
            new2old[target_path] = source_path


    #######################################################################
    # Transactions
    #######################################################################
    def _cleanup(self):
        super(GitDatabase, self)._cleanup()
        self.has_changed = False


    def _abort_changes(self):
        # 1. Handlers
        cache = self.cache
        for key in self.added:
            self._discard_handler(key)
        for key in self.changed:
            cache[key].abort_changes()

        # Clean the filesystem (in a try/except to avoid a problem with new
        # repositories)
        try:
            self.send_subprocess(['git', 'reset', '--hard', '-q'])
        except CalledProcessError:
            pass
        if self.added:
            self.send_subprocess(['git', 'clean', '-fxdq'])

        # Reset state
        self.added.clear()
        self.changed.clear()

        # 2. Catalog
        self.catalog.abort_changes()

        # 3. Resources
        self.resources_old2new.clear()
        self.resources_new2old.clear()


    def _rollback(self):
        pass


    def _save_changes(self, data):
        # Synchronize eventually the handlers and the filesystem
        for key in self.added:
            handler = self.cache.get(key)
            if handler and handler.dirty:
                parent_path = dirname(key)
                if not self.fs.exists(parent_path):
                    self.fs.make_folder(parent_path)
                handler.save_state()

        for key in self.changed:
            handler = self.cache[key]
            handler.save_state()

        self.changed.clear()

        # Call a "git add" eventually for new and/or moved files
        if self.added:
            self.send_subprocess(['git', 'add'] + list(self.added))
            self.added.clear()

        # Commit
        git_author, git_date, git_msg, docs_to_index, docs_to_unindex = data
        command = ['git', 'commit', '-aq', '-m', git_msg or 'no comment']
        if git_author:
            command.append('--author=%s' % git_author)
        if git_date:
            git_date = ISODateTime.encode(git_date)
            command.append('--date=%s' % git_date)
        try:
            self.send_subprocess(command)
        except CalledProcessError, excp:
            # Avoid an exception for the 'nothing to commit' case
            # FIXME Not reliable, we may catch other cases
            if excp.returncode != 1:
                raise

        # 2. Catalog
        catalog = self.catalog
        for path in docs_to_unindex:
            catalog.unindex_document(path)
        for resource, values in docs_to_index:
            catalog.index_document(values)
        catalog.save_changes()


    def save_changes(self, data=None):
        if not self.has_changed:
            return

        # Commit
        try:
            self._save_changes(data)
        except Exception:
            self._rollback()
            self._abort_changes()
            raise
        finally:
            self._cleanup()



def make_git_database(path, size_min, size_max):
    """Create a new empty Git database if the given path does not exists or
    is a folder.

    If the given path is a folder with content, the Git archive will be
    initialized and the content of the folder will be added to it in a first
    commit.
    """
    # 1. Make the data folder
    path = lfs.get_absolute_path(path)
    path_data = '%s/database' % path
    if not lfs.exists(path_data):
        lfs.make_folder(path_data)

    # 2. Initialize git
    send_subprocess(['git', 'init', '-q'], path=path_data)
    send_subprocess(['git', 'add', '.'], path=path_data)
    cmd = ['git', 'commit', '-q', '-m', 'Initial commit']
    try:
        send_subprocess(cmd, path=path_data)
    except CalledProcessError:
        pass

    # 3. The catalog
    make_catalog('%s/catalog' % path, get_register_fields())

    # Ok
    return GitDatabase(path, size_min, size_max)



def check_database(target):
    """This function checks whether the database is in a consisitent state,
    this is to say whether a transaction was not brutally aborted and left
    the working directory with changes not committed.

    This is meant to be used by scripts, like 'icms-start.py'
    """
    cwd = '%s/database' % target

    # Check modifications to the working tree not yet in the index.
    command = ['git', 'ls-files', '-m', '-d', '-o']
    data1 = get_pipe(command, cwd=cwd)

    # Check changes in the index not yet committed.
    command = ['git', 'diff-index', '--cached', '--name-only', 'HEAD']
    data2 = get_pipe(command, cwd=cwd)

    # Everything looks fine
    if len(data1) == 0 and len(data2) == 0:
        return True

    # Something went wrong
    print 'The database is not in a consistent state.  Fix it manually with'
    print 'the help of Git:'
    print
    print '  $ cd %s/database' % target
    print '  $ git clean -fxd'
    print '  $ git checkout -f'
    print
    return False
