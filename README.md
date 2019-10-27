sphinx-autopackagesummary
=========================

This is a [Sphinx](https://www.sphinx-doc.org/) extension that makes it
possible to automatically generate API documentation for deeply nested Python
packages using the built-in autosummary extension.

The problem with the built-in autosummary directive is that it does not
automatically pick up nested sub-modules, requiring tedious manual work to
specify the entire module tree.

Instead of this:

```rst
.. autosummary::
   :toctree: _autosummary

   mypackage.submodule1
   mypackage.submodule2
   mypackage.submodule3
```

You can now simply use this:

```rst
.. autopackagesummary:: mypackage
   :toctree: _autosummary
```

Usage
-----

To make use of this extension, the following steps are needed:

1. Install the module using pip.
```
pip install sphinx-autopackagesummary
```
2. Enable it in `conf.py`.
```python
extensions = ['sphinx.ext.autosummary', 'autopackagesummary']
```
3. Make use of the new syntax

Configuration
-------------

The `autopackagesummary` directive accepts all options that are supported by
`autosummary`, which are simply passed on.

To exclude packages from being imported, add them to the config setting
`autosummary_mock_imports`.

Recursive generation
--------------------

If your packages have subpackages, it is possible to use this recursively by
customizing the autosummary template.  For example, you could have your root
package documented like so:
```rst
.. py:package:: mypackage

   This is my package.

   .. autopackagesummary:: mypackage
      :toctree: _autosummary
      :template: autosummary/package.rst
```

And then create a `_templates/autosummary/package.rst` like so:

```rst
{{ fullname | escape | underline }}

.. automodule:: {{ fullname }}

   .. autopackagesummary:: {{ fullname }}
      :toctree: .
```

Note the use of `.` for the toctree setting: otherwise, the `_autosummary`
directories would keep nesting, like `_autosummary/_autosummary/module.rst`.

License
-------

This extension has been placed into the public domain.  If you make a
contribution to this repository, you are placing your modifications into the
public domain as well.
