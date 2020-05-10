__version__ = '1.3'

from sphinx.util import logging
from sphinx.ext.autosummary import Autosummary
from sphinx.ext.autodoc.importer import import_module
import sphinx.ext.autosummary.generate as generate
import importlib.util
import pkgutil
import re


ignore_modules = set()
orig_find_autosummary_in_lines = generate.find_autosummary_in_lines
logger = logging.getLogger(__name__)


def get_package_modules(pkgname):
    """Returns a list of module names within the given package."""
    if pkgname in ignore_modules:
        return []

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
    for importer, modname, ispkg in pkgutil.iter_modules(path):
        fullname = pkgname + '.' + modname
        if fullname in ignore_modules:
            continue

        # Try importing the module; if we can't, then don't add it to the list.
        try:
            import_module(fullname)
        except ImportError:
            logger.exception("Failed to import {0}".format(fullname))
            continue

        names.append(fullname)

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
    for mod in config.autosummary_mock_imports:
        ignore_modules.add(mod)


def setup(app):
    generate.find_autosummary_in_lines = find_autosummary_in_lines

    app.add_directive('autopackagesummary', Autopackagesummary)
    app.connect('config-inited', on_config_inited)

    return {
        'version': __version__,
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
