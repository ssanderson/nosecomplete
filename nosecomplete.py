import os
import sys
import re
import ast

from optparse import OptionParser


class PythonTestFinder(object):
    def find_functions(self, ast_body, matcher):
        for obj in ast_body:
            if not matcher(obj):
                continue
            if isinstance(obj, ast.FunctionDef):
                yield obj.name
            if isinstance(obj, ast.ClassDef):
                for func in self.find_functions(obj.body, matcher):
                    yield '%s.%s' % (obj.name, func)

    def get_module_tests(self, module):
        with open(module) as f:
            data = f.read()
        result = ast.parse(data)

        def matcher(obj):
            if isinstance(obj, ast.FunctionDef):
                return re.search('test', obj.name, re.IGNORECASE)
            # Unlike nose, we're not able to determine whether this class
            # inherits from unittest.TestCase
            # So it may be the case that this class name lacks 'test'. As a
            # compromise, match all classes
            return isinstance(obj, ast.ClassDef)
        tests = list(
            self.find_functions(result.body, matcher)
        )
        return tests


class NoseTestFinder(object):
    def _generate_tests(self, suite):
        from nose.suite import ContextSuite
        from nose.case import Test
        for context in suite._tests:
            if isinstance(context, Test):
                yield context
                continue
            assert isinstance(context, ContextSuite)
            for test in self._generate_tests(context):
                yield test

    def _get_test_name(self, test_wrapper):
        from nose.case import FunctionTestCase
        test = test_wrapper.test
        if isinstance(test, FunctionTestCase):
            return test.test.__name__
        return test.__class__.__name__ + '.' + test._testMethodName

    def _generate_test_names(self, suite):
        return map(self._get_test_name, self._generate_tests(suite))

    def get_module_tests(self, module):
        import nose
        loader = nose.loader.defaultTestLoader()
        return self._generate_test_names(loader.loadTestsFromName(module))


def _get_prefixed(strings, prefix):
    for string in strings:
        if string.startswith(prefix):
            yield string.replace(prefix, '', 1)


def _get_py_or_dirs(directory, prefix, as_module=False):
    for entry in os.listdir(directory or '.'):
        path = os.path.join(directory, entry)
        if entry.startswith(prefix):
            leftover = entry.replace(prefix, '', 1)
            if os.path.isdir(path):
                if as_module:
                    yield leftover + '.'
                else:
                    yield leftover + '/'
            elif leftover.endswith('.py'):
                if as_module:
                    # Strip off .py if this is a module
                    yield leftover[:-3] + ':'
                else:
                    yield leftover + ':'

def _is_path_or_filelike(thing):
    """
    Return True if `thing` looks like a file, a path, or the start of a
    file/path.
    """
    return (os.path.exists(thing) or
            os.path.isdir(thing) or
            os.path.isdir(os.path.split(thing)[0]))

def _modname_to_filepath(thing):
    """
    Convert foo.bar.buzz -> foo/bar/buzz/
    """
    return os.path.join(*thing.split('.'))

def _is_modulelike(thing):
    """
    Return True if `thing` looks like python module name or the start of a
    python modulename.
    """
    return _is_path_or_filelike(_modname_to_filepath(thing.strip('.')))

def _complete(test_finder, thing):
    if ':' in thing:
        # complete a test
        module, test_part = thing.split(':')
        if not os.path.exists(module):
            # Try to convert from module-style syntax to file-style syntax.
            module = _modname_to_filepath(module) + '.py'

        tests = list(test_finder.get_module_tests(module))
        if '.' in test_part:
            # complete a method
            return _get_prefixed(strings=tests, prefix=test_part)
        funcs = [test for test in tests if test.count('.') == 0]
        classes = [test.split('.')[0] for test in tests if '.' in test]
        if test_part in classes:
            # indicate a method should be completed
            return ['.']
        return _get_prefixed(strings=funcs + classes, prefix=test_part)

    if _is_path_or_filelike(thing):
        if os.path.isdir(thing):
            # complete directory contents
            if thing != '.' and not thing.endswith('/'):
                return ['/']
            return _get_py_or_dirs(thing, '')
        elif os.path.exists(thing):
            # add a colon to indicate search for specific class/func
            return [':']
        else:
            # path not exists, complete a partial path
            directory, file_part = os.path.split(thing)
            return _get_py_or_dirs(directory, file_part)

    if _is_modulelike(thing):

        as_filepath = _modname_to_filepath(thing)
        if os.path.isdir(as_filepath):
            # complete directory contents
            if not thing.endswith('.'):
                return '.'
            return _get_py_or_dirs(as_filepath, '', as_module=True)

        elif os.path.exists(as_filepath + '.py'):
            # add a colon to indicate search for specific class/func
            return [':']
        else:
            # path not exists, complete a partial path
            directory, file_part = os.path.split(as_filepath)
            return _get_py_or_dirs(directory, file_part, as_module=True)

def complete(test_finder, thing):
    for option in set(_complete(test_finder, thing)):
        sys.stdout.write(thing + option + ' ')  # avoid print for python 3


def main():
    methods = {
        'nose': NoseTestFinder,
        'python': PythonTestFinder,
    }
    parser = OptionParser(usage='usage: %prog [options] ')
    parser.add_option(
        "-s",
        "--search-method",
        help="Search method to use when locating tests",
        choices=list(methods.keys()),
        default='python',
    )
    (options, args) = parser.parse_args()
    finder_class = methods[options.search_method]
    finder_instance = finder_class()

    complete(finder_instance, './' if len(args) == 0 else args[0])

if __name__ == '__main__':
    main()
