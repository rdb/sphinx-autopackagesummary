__version__ = '0.1'

from sphinx.util import logging
from sphinx.ext.autosummary import Autosummary, _import_by_name
import sphinx.ext.autosummary.generate as generate
import importlib
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
    path = spec.submodule_search_locations
    pkg = None

    names = []
    for importer, modname, ispkg in pkgutil.iter_modules(path):
        fullname = pkgname + '.' + modname
        if fullname in ignore_modules:
            continue

        # Try importing the module; if we can't, then don't add it to the list.
        try:
            mod = importer.find_module(fullname).load_module(fullname)
        except Exception as ex:
            logger.warning("Failed to import {0}: {1}".format(fullname, ex))
            continue

        #if pkg is None:
        #    pkg = _import_by_name(pkgname)[0]
        #setattr(pkg, modname, mod)
        names.append(fullname)

    return names


def find_autosummary_in_lines(lines, module=None, filename=None):
    """Overrides the autosummary version of this function to dynamically expand
    an autopackagesummary directive into a regular autosummary directive."""

    autopackagesummary_re = \
        re.compile(r'^(\s*)\.\.\s+autopackagesummary::\s*([A-Za-z0-9_.]+)\s*$')

    lines = list(lines)
    new_lines = []
    in_autopackagesummary = False

    while lines:
        line = lines.pop(0)
        m = autopackagesummary_re.match(line)
        if m:
            base_indent = m.group(1)
            name = m.group(2).strip()

            new_lines.append(base_indent + '.. autosummary::')

            line = lines.pop(0)
            while not line.strip() or line.startswith(base_indent + " "):
                new_lines.append(line)
                if not lines:
                    break
                line = lines.pop(0)

            new_lines.append("")

            for subname in get_package_modules(name):
                new_lines.append(base_indent + "   " + subname)

            new_lines.append("")
        else:
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
