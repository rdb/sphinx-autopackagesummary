__version__ = '1.4'

from sphinx.util import logging
from sphinx.ext.autosummary import Autosummary
from sphinx.ext.autodoc.importer import import_module
import sphinx.ext.autosummary.generate as generate
import hashlib
import importlib.util
import json
import os
import pathlib
import pkgutil
import re
import sys


ignore_modules = set()
orig_find_autosummary_in_lines = generate.find_autosummary_in_lines
logger = logging.getLogger(__name__)

# Persistent cache of `get_package_modules` results, keyed on a content
# signature of the package's .py files.  This avoids re-importing every
# submodule on each build, which is the dominant cost of the autopackagesummary
# expansion for large packages.
_cache_path = None
_module_cache = None
_cache_dirty = False


def _package_signature(pkgname):
    """Compute a signature for a package's on-disk contents.  Returns None if
    the package is not installed or is not a package (plain module)."""
    spec = importlib.util.find_spec(pkgname)
    if not spec or not spec.submodule_search_locations:
        return None
    h = hashlib.sha1()
    # Bind the cache to the Python environment — switching venvs or Python
    # versions invalidates the cache.
    h.update(sys.prefix.encode())
    h.update(repr(sys.version_info[:2]).encode())
    for root in spec.submodule_search_locations:
        root = pathlib.Path(root)
        for p in sorted(root.rglob('*.py')):
            try:
                st = p.stat()
            except OSError:
                continue
            h.update(
                '{}:{}:{}\n'.format(
                    p.relative_to(root), st.st_mtime_ns, st.st_size
                ).encode()
            )
    return h.hexdigest()


def _load_cache():
    global _module_cache
    if _module_cache is not None:
        return _module_cache
    if _cache_path and _cache_path.exists():
        try:
            _module_cache = json.loads(_cache_path.read_text())
            if not isinstance(_module_cache, dict):
                _module_cache = {}
        except (json.JSONDecodeError, OSError):
            _module_cache = {}
    else:
        _module_cache = {}
    return _module_cache


def _save_cache():
    global _cache_dirty
    if not _cache_path or not _cache_dirty or _module_cache is None:
        return
    try:
        _cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = _cache_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(_module_cache))
        os.replace(tmp, _cache_path)
        _cache_dirty = False
    except OSError as e:
        logger.warning(
            "Failed to write autopackagesummary cache: {}".format(e)
        )


def get_package_modules(pkgname):
    """Returns a list of module names within the given package."""
    global _cache_dirty

    if pkgname in ignore_modules:
        return []

    sig = _package_signature(pkgname)
    cache = _load_cache()
    cached = cache.get(pkgname) if sig else None
    if cached and cached.get('sig') == sig:
        names = list(cached.get('modules', []))
        failed = list(cached.get('failed', []))
        # Re-attempt previously failed imports: a missing dependency may have
        # since been installed even though no .py in the package changed.
        # This is cheap compared to re-importing everything, since `failed`
        # is typically small (a handful of optional-dep modules).
        still_failed = []
        for fullname in failed:
            if fullname in ignore_modules:
                # Don't retry, but keep in the list so it can be picked up
                # again if it's later un-ignored.
                still_failed.append(fullname)
                continue
            try:
                import_module(fullname)
            except ImportError:
                still_failed.append(fullname)
                continue
            names.append(fullname)
        if still_failed != failed:
            cache[pkgname] = {
                'sig': sig, 'modules': names, 'failed': still_failed,
            }
            _cache_dirty = True
        # Respect ignore_modules even on cache hit — the list may have changed
        # since the cache was written.
        return [m for m in names if m not in ignore_modules]

    spec = importlib.util.find_spec(pkgname)
    if not spec:
        logger.warning("Failed to find module {0}".format(pkgname))
        return []

    path = spec.submodule_search_locations

    if not path:
        # This is not a package, but a module.
        # (Fun fact: if we don't return here, we will start importing all the
        # modules on sys.path, which will have all sorts of hilarious effects
        # like reading out the Zen of Python and opening xkcd #353 in the web
        # browser.)
        return []

    names = []
    failed = []
    for importer, modname, ispkg in pkgutil.iter_modules(path):
        fullname = pkgname + '.' + modname
        if fullname in ignore_modules:
            continue

        # Try importing the module; if we can't, then don't add it to the list.
        try:
            import_module(fullname)
        except ImportError:
            logger.exception("Failed to import {0}".format(fullname))
            failed.append(fullname)
            continue

        names.append(fullname)

    if sig is not None:
        cache[pkgname] = {'sig': sig, 'modules': names, 'failed': failed}
        _cache_dirty = True

    return names


def find_autosummary_in_lines(lines, module=None, filename=None):
    """Overrides the autosummary version of this function to dynamically expand
    an autopackagesummary directive into a regular autosummary directive."""

    autopackagesummary_re = \
        re.compile(r'^(\s*)\.\.\s+autopackagesummary::\s*([A-Za-z0-9_.]+)\s*$')

    lines = list(lines)
    new_lines = []

    while lines:
        line = lines.pop(0)
        m = autopackagesummary_re.match(line)
        if m:
            base_indent = m.group(1)
            name = m.group(2).strip()

            new_lines.append(base_indent + '.. autosummary::')

            # Pass on any options.
            while lines:
                line = lines.pop(0)

                if line.strip() and not line.startswith(base_indent + " "):
                    # Deindented line, so end of the autosummary block.
                    break

                new_lines.append(line)

            if new_lines[-1].strip():
                new_lines.append("")

            for subname in get_package_modules(name):
                new_lines.append(base_indent + "   " + subname)

            new_lines.append("")

        new_lines.append(line)

    return orig_find_autosummary_in_lines(new_lines, module, filename)


class Autopackagesummary(Autosummary):
    """Extends Autosummary to dynamically add a package's submodules.
    It takes a single argument, the name of the package."""

    required_arguments = 1
    optional_arguments = 1

    def get_items(self, names):
        pkgname = self.arguments[0]

        names += get_package_modules(pkgname)
        return super().get_items(names)


def on_config_inited(app, config):
    global _cache_path, _module_cache, _cache_dirty
    for mod in config.autosummary_mock_imports:
        ignore_modules.add(mod)
    # Persist the cache next to the doctree cache so that it survives across
    # incremental builds but is discarded by a full clean.
    _cache_path = pathlib.Path(app.doctreedir) / 'autopackagesummary.json'
    # Reset in-memory state so that running multiple Sphinx builds in one
    # process (e.g. sphinx-autobuild, test harnesses) doesn't leak entries
    # from a previous project into the new cache file.
    _module_cache = None
    _cache_dirty = False


def on_build_finished(app, exception):
    _save_cache()


def setup(app):
    generate.find_autosummary_in_lines = find_autosummary_in_lines

    app.add_directive('autopackagesummary', Autopackagesummary)
    app.connect('config-inited', on_config_inited)
    app.connect('build-finished', on_build_finished)

    return {
        'version': __version__,
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
