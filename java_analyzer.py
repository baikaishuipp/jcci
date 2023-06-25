# -*- coding: UTF-8 -*-

class JavaAnalyzer(object):
    def __init__(self, filepath, package_name, class_name, extends, is_controller):
        self.filepath = filepath
        self.package_name = package_name
        self.imports = JavaImports(None, None, None)
        self.class_name = class_name
        self.extends = extends
        self.implements = []
        self.declarators = []
        self.methods = []
        self.is_controller = is_controller


class JavaImports(object):
    def __init__(self, start, end, imports):
        self.start = start
        self.end = end
        self.imports = imports


class JavaDeclarators(object):
    def __init__(self, type, name, line):
        self.type = type
        self.name = name
        self.line = line
        self.contains_class = ''
        self.diff_impact = ''


class JavaMethods(object):
    def __init__(self, name, start, end, content, is_api, api_path):
        self.name = name
        self.start = start
        self.end = end
        self.content = content
        self.contains_class = {}
        self.contains_declarators = []
        self.is_api = is_api
        self.api_path = api_path
        self.diff_impact = None

    def __getitem__(self, item):
        return item

    def add_declarators(self, declarator):
        self.contains_declarators.append(declarator)


class JavaDiffResult(object):
    def __init__(self, filepath, added_line_nums, added_line_contents, removed_line_nums, removed_line_contents):
        self.filepath = filepath
        self.added_line_nums = added_line_nums
        self.added_line_contents = added_line_contents
        self.removed_line_nums = removed_line_nums
        self.removed_line_contents = removed_line_contents
        self.changed_methods = {}
        self.changed_declarators = {}
        self.impact = {}


class CodeImpact(object):
    def __init__(self, filepath, class_path):
        self.filepath = filepath
        self.class_path = class_path
        self.impact_methods = []

