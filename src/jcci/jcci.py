# -*- coding: UTF-8 -*-
import atexit
import datetime
import json
import os
import re
import sys
import time
import logging
import javalang
from javalang.parser import JavaSyntaxError
from unidiff import PatchSet
from .java_analyzer import JavaAnalyzer, JavaImports, JavaMethods, JavaDeclarators, JavaDiffResult
from .mapper_parse import parse

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)


# get all java files
def _get_java_files(dir_path):
    file_lists = []
    for root, dirs, files in os.walk(dir_path):
        if '.git' in root or os.path.join('src', 'test') in root:
            continue
        file_lists.extend([os.path.join(root, file) for file in files if file.endswith(('.java', '.xml')) and not file.endswith('pom.xml')])
    return file_lists


def _analyze_java_file(filepath, folder_name):
    logging.info(f'Analyzing file: {filepath}')
    import_list = []
    with open(filepath, encoding='UTF-8') as fp:
        file_content = fp.read()
    lines = file_content.split('\n')
    try:
        tree = javalang.parse.parse(file_content)
        if tree.package is None or len(tree.types) == 0:
            return
        package_name = tree.package.name
        types = tree.types[0]
        class_name = types.name
    except JavaSyntaxError as e:
        logging.error(f'Analyze failed at {str(e.at)} cause {e.description} with file {filepath} ')
        return None
    except Exception as ee:
        logging.error(f'Analyze failed at {str(ee)} with file {filepath}')
        return None
    # is controller or not
    is_controller = False
    base_request = ''
    annotations = types.annotations
    for annotation in annotations:
        if 'Controller' in annotation.name:
            is_controller = True
        if 'RequestMapping' == annotation.name:
            if not isinstance(annotation.element, list):
                if annotation.element is not None:
                    if 'value' in annotation.element.attrs:
                        base_request = annotation.element.value.replace('"', '')
                    elif 'values' in annotation.element.attrs:
                        base_request = ' || '.join([literal.value for literal in annotation.element.values])
            else:
                base_request_list = []
                for annotation_element in annotation.element:
                    if annotation_element.name == 'value' or annotation_element.name == 'path':
                        if 'values' in annotation_element.value.attrs:
                            base_request_list += _get_element_with_values(annotation_element.value)
                        else:
                            base_request_list += _get_element_value(annotation_element.value)
                if len(base_request_list) > 0:
                    base_request = base_request_list[0]
    if is_controller and not base_request.endswith('/'):
        base_request += '/'
    class_path = package_name + '.' + class_name
    extends_name = types.extends.name if 'extends' in types.attrs and types.extends is not None and not isinstance(types.extends, list) else None
    extends_name_path = extends_name
    implements_names = [implement.name for implement in types.implements] if 'implements' in types.attrs and types.implements is not None else None
    implements_names_list = []
    import_path_class_map = {class_name: class_path}
    for import_Obj in tree.imports:
        import_path = import_Obj.path
        if not import_path.startswith('com.') and not import_path.startswith('cn.'):
            continue
        if not import_Obj.wildcard and not import_Obj.static:
            import_path_class = import_path.split('.')[-1]
            import_path_class_map[import_path_class] = import_path
            import_list.append(import_path)
            if extends_name and import_path.endswith(extends_name):
                extends_name_path = import_path
            if implements_names and import_path_class in implements_names:
                implements_names_list.append(import_path)
    if implements_names and not implements_names_list:
        implements_names_list.append(package_name + '.' + implements_names[0])
        import_path_class_map[implements_names[0]] = package_name + '.' + implements_names[0]
    imports = JavaImports(
        tree.imports[0].position.line if tree.imports else None,
        tree.imports[-1].position.line if tree.imports else None,
        tree.imports
    )
    fields = types.fields
    fields_list = []
    for field_obj in fields:
        field_type = field_obj.type.name
        field_declarators = field_obj.declarators[0].name
        field_map = JavaDeclarators(field_type, field_declarators, field_obj.position.line)
        field_resource_name = None
        field_resource_type = None
        if 'annotations' in field_obj.attrs:
            for field_anno in field_obj.annotations:
                if field_anno.name != 'Resource' or field_anno.element is None:
                    continue
                for field_anno_el in field_anno.element:
                    if field_anno_el.name == 'name':
                        field_resource_name = _get_element_value(field_anno_el.value)[0]
                    if field_anno_el.name == 'type':
                        field_resource_type = field_anno_el.value.type.name
                        if field_resource_type in import_path_class_map.keys():
                            field_resource_type = import_path_class_map.get(field_resource_type)
                        else:
                            field_resource_type = package_name + '.' + field_resource_type
            field_map.set_resource(field_resource_name, field_resource_type)
        if field_resource_type is not None:
            field_map.contains_class = field_resource_type
        elif field_resource_name is not None:
            field_map.contains_class = field_resource_name
        elif field_type in import_path_class_map.keys():
            field_map.contains_class = import_path_class_map[field_type]
        fields_list.append(field_map)

    methods_list = []
    method_name_param_map_list = [{'name': method.name, 'param': method.parameters} for method in types.methods]
    for method_obj in types.methods:
        method_name = method_obj.name
        method_start_line = method_obj.position.line
        if method_obj.annotations:
            method_start_line = method_obj.annotations[0].position.line
        method_end_line = _get_method_end_line(method_obj)
        method_content = lines[method_start_line - 1: method_end_line + 1]
        # method is api or not
        is_api = False
        api_path_list = []
        method_annotation_names = []
        if is_controller:
            method_annotations = method_obj.annotations
            req_method_list = []
            method_api_path = []
            for method_annotation in method_annotations:
                method_annotation_names.append(method_annotation.name)
                if 'Mapping' in method_annotation.name:
                    is_api = True
                    if method_annotation.name != 'RequestMapping':
                        req_method_list.append(method_annotation.name.replace('Mapping', ''))
                    else:
                        if isinstance(method_annotation.element, list):
                            for method_annotation_element in method_annotation.element:
                                if 'name' in method_annotation_element.attrs and method_annotation_element.name == 'method':
                                    method_annotation_element_value = method_annotation_element.value
                                    if 'member' in method_annotation_element_value.attrs:
                                        req_method_list.append(method_annotation_element_value.member)
                                    elif 'values' in method_annotation_element_value.attrs:
                                        method_annotation_element_values = method_annotation_element_value.values
                                        req_method_list += [method_annotation_element_temp.member for
                                                            method_annotation_element_temp in
                                                            method_annotation_element_values
                                                            if 'member' in method_annotation_element_temp.attrs]
                    if not isinstance(method_annotation.element, list):
                        if method_annotation.element is None:
                            continue
                        method_api_path += _get_element_value(method_annotation.element)
                    else:
                        method_api_path_list = [method_annotation_element.value for method_annotation_element in method_annotation.element
                                                if method_annotation_element.name == 'path' or method_annotation_element.name == 'value']
                        if len(method_api_path_list) > 0:
                            method_api_path_obj = method_api_path_list[0]
                            if 'value' in method_api_path_obj.attrs:
                                method_api_path += [method_api_path_obj.value.replace('"', '')]
                            else:
                                if 'values' in method_api_path_obj.attrs:
                                    for method_api_value in method_api_path_obj.values:
                                        method_api_path += _get_element_value(method_api_value)
                                else:
                                    method_api_path += [method_name + '/cci-unknown']
            if len(method_api_path) == 0:
                method_api_path = ['/']
            for method_api_path_obj in method_api_path:
                if method_api_path_obj.startswith('/'):
                    method_api_path_obj = method_api_path_obj[1:]
                api_path = base_request + method_api_path_obj
                if api_path.endswith('/'):
                    api_path = api_path[0:-1]
                if len(req_method_list) > 0:
                    api_path_list += ['[' + req_method_temp + ']' + api_path for req_method_temp in req_method_list]
                else:
                    api_path_list.append('[ALL]' + api_path)
        method_map = JavaMethods(method_name, method_obj.parameters, method_start_line, method_end_line + 1, method_content, is_api, api_path_list, method_annotation_names)
        # imports in this method or not
        method_content_str = ''.join(method_content)
        for import_path_class, import_path_info in import_path_class_map.items():
            if import_path_class in method_content_str:
                contain_class_lines = [line for line in method_content if import_path_class in line]
                contain_class_declarators = [line.strip().split('=')[0].strip()
                                                 .split(':')[0].strip()
                                                 .split(' ')[-1]
                                                 .replace(import_path_class, '').replace(';', '').strip()
                                             for line in contain_class_lines]
                if '' in contain_class_declarators:
                    contain_class_declarators.remove('')
                class_declarators_method = [method_content_line.split(import_path_class + '.')[1].split('(')[0]
                                            for method_content_line in method_content
                                            if import_path_class + '.' in method_content_line and len(method_content_line.split(import_path_class + '.')[1].split('(')) > 1]
                for class_declarator in contain_class_declarators:
                    class_declarators_method += [method_content_line.split(class_declarator + '.')[1].split('(')[0]
                                                 for method_content_line in method_content if
                                                 class_declarator + '.' in method_content_line and len(method_content_line.split(class_declarator + '.')[1].split('(')) > 1]
                if import_path_info not in method_map['contains_class']:
                    method_map.contains_class[import_path_info] = {}
                method_map.contains_class[import_path_info]['methods'] = list(set(class_declarators_method))
        for declarator_tmp in fields_list:
            declarator_tmp_final = declarator_tmp
            if declarator_tmp.name in str(method_content):
                if declarator_tmp.contains_class != '':
                    class_method_list = []
                    if declarator_tmp.contains_class not in method_map.contains_class.keys():
                        method_map.contains_class[declarator_tmp.contains_class] = {}
                    else:
                        if 'methods' in method_map.contains_class[declarator_tmp.contains_class].keys():
                            class_method_list = method_map.contains_class[declarator_tmp.contains_class]['methods']
                    for method_content_line in method_content:
                        if declarator_tmp.name in method_content_line and len(
                                method_content_line.split(declarator_tmp.name + '.')) > 1:
                            class_method = method_content_line.split(declarator_tmp.name + '.')[1].split('(')[0]
                            if class_method not in class_method_list:
                                class_method_list.append(class_method)
                    method_map.contains_class[declarator_tmp.contains_class]['methods'] = class_method_list
                else:
                    method_map.add_declarators(declarator_tmp_final.__dict__)
        # class method used in this class
        for method_name_param_map in method_name_param_map_list:
            if method_name_param_map['name'] == method_name and method_name_param_map['param'] == method_obj.parameters:
                continue
            for method_content_line in method_content:
                if method_name_param_map['name'] + '(' in method_content_line and not method_content_line.endswith('{'):
                    if class_path not in method_map.contains_class.keys():
                        method_map.contains_class[class_path] = {'methods': [method_name_param_map['name']]}
                    else:
                        if 'methods' in method_map.contains_class[class_path].keys():
                            method_map.contains_class[class_path]['methods'].append(method_name_param_map['name'])
                        else:
                            method_map.contains_class[class_path] = {'methods': [method_name_param_map['name']]}
        if 'body' in method_obj.attrs and method_obj.body is not None:
            for method_body in method_obj.body:
                if type(method_body).__name__ == 'LocalVariableDeclaration':
                    if 'type' in method_body.attrs and 'name' in method_body.type.attrs \
                            and method_body.type.name in import_path_class_map.keys() \
                            and 'declarators' in method_body.attrs \
                            and isinstance(method_body.declarators, list) \
                            and len(method_body.declarators) > 0:
                        class_method_list = []
                        if import_path_class_map.get(method_body.type.name) not in method_map.contains_class.keys():
                            method_map.contains_class[import_path_class_map.get(method_body.type.name)] = {}
                        else:
                            if 'methods' in method_map.contains_class[import_path_class_map.get(method_body.type.name)].keys():
                                class_method_list = method_map.contains_class[import_path_class_map.get(method_body.type.name)]['methods']
                        for method_content_line in method_content:
                            if method_body.declarators[0].name in method_content_line and len(method_content_line.split(method_body.declarators[0].name + '.')) > 1:
                                class_method = method_content_line.split(method_body.declarators[0].name + '.')[1].split('(')[0]
                                if class_method not in class_method_list:
                                    class_method_list.append(class_method)
                        method_map.contains_class[import_path_class_map.get(method_body.type.name)]['methods'] = class_method_list
                        # method_obj.append(method_body.declarators[0].name)
        methods_list.append(method_map)
    file_analyze = JavaAnalyzer(filepath.replace(os.sep, '/').replace(folder_name + '/', ''), package_name, class_name,
                                extends_name_path, is_controller)
    file_analyze.imports = imports
    file_analyze.implements = implements_names_list
    file_analyze.declarators = fields_list
    file_analyze.methods = methods_list
    return file_analyze


def _get_element_value(method_element):
    method_api_path = []
    if type(method_element).__name__ == 'BinaryOperation':
        operandl = method_element.operandl
        operandr = method_element.operandr
        operandl_str = _get_api_part_route(operandl)
        operandr_str = _get_api_part_route(operandr)
        method_api_path = [operandl_str + operandr_str]
    elif type(method_element).__name__ == 'MemberReference':
        method_api_path = [method_element.member.replace('"', '')]
    elif type(method_element).__name__ == 'ElementArrayValue':
        method_api_path = _get_element_with_values(method_element)
    elif method_element.value is not None:
        method_api_path = [method_element.value.replace('"', '')]
    return method_api_path


def _get_element_with_values(method_api_path_obj):
    result = []
    for method_api_value in method_api_path_obj.values:
        result += _get_element_value(method_api_value)
    return result


def _get_api_part_route(part):
    part_class = type(part).__name__
    if part_class == 'MemberReference':
        return part.member.replace('"', '')
    elif part_class == 'Literal':
        return part.value.replace('"', '')


def _get_method_end_line(method_obj):
    method_end_line = method_obj.position.line
    while True:
        if isinstance(method_obj, list):
            if None in method_obj:
                method_obj.remove(None)
            if len(method_obj) == 0:
                break
            length = len(method_obj)
            for i in range(0, length):
                temp = method_obj[length - 1 - i]
                if temp is not None:
                    method_obj = temp
                    break
            if method_obj is None:
                break
        if isinstance(method_obj, list):
            continue
        if hasattr(method_obj, 'position') \
                and method_obj.position is not None \
                and method_obj.position.line > method_end_line:
            method_end_line = method_obj.position.line
        if hasattr(method_obj, 'children'):
            method_obj = method_obj.children
        else:
            break
    return method_end_line


# handle diff result text
def _get_diff_results(diff_file, head_java_file_analyze_result, base_java_file_analyze_result):
    with open(diff_file, encoding='UTF-8') as f:
        diff_text = f.read()
    patch_set = PatchSet(diff_text)
    patch_results = []
    for patch in patch_set:
        patch_result = _analyze_diff_patch(patch, head_java_file_analyze_result, base_java_file_analyze_result)
        if patch_result is not None:
            patch_results.append(patch_result)
    return patch_results


def _analyze_diff_patch(patch, head_java_file_analyze_result, base_java_file_analyze_result):
    if '.git' in patch.path or os.path.join('src', 'test') in patch.path or (not patch.path.endswith(('.java', '.xml'))):
        return None
    line_num_added, line_content_added, line_num_removed, line_content_removed = _diff_patch_lines(patch)
    java_file_path = patch.path
    methods_impacted = {}
    declarators_impacted = {}
    _diff_patch_impact(methods_impacted, declarators_impacted, head_java_file_analyze_result, java_file_path,
                       line_num_added, 'ADD')
    _diff_patch_impact(methods_impacted, declarators_impacted, base_java_file_analyze_result, java_file_path,
                       line_num_removed, 'DEL')
    diff_result = JavaDiffResult(patch.path, line_num_added, line_content_added, line_num_removed, line_content_removed)
    diff_result.changed_methods = methods_impacted
    diff_result.changed_declarators = declarators_impacted
    return diff_result


def _diff_patch_impact(methods_impacted, declarators_impacted, java_file_analyze_result, java_file_path, line_num_mode,
                       mode):
    java_analyze = java_file_analyze_result.get(java_file_path)
    if java_analyze is None:
        return
    is_xml_file = java_file_path.endswith('.xml')
    if is_xml_file:
        methods = java_analyze.result_maps + java_analyze.sqls + java_analyze.statements
    else:
        methods = java_analyze.methods
    for line_num_index in range(0, len(line_num_mode)):
        line_num = line_num_mode[line_num_index]
        line_num_in_method = False
        for method in methods:
            line_num_in_method = _method_impact(method, line_num, methods_impacted, mode)
            if line_num_in_method:
                break
        if line_num_in_method:
            continue
        if is_xml_file:
            continue
        java_declarators = java_analyze.declarators
        for declarator in java_declarators:
            if line_num == declarator.line:
                declarator.diff_impact = mode
                declarators_impacted[declarator.name] = declarator.__dict__
                break
    if is_xml_file:
        for statement in java_analyze.statements:
            if statement.name in methods_impacted.keys():
                continue
            if statement.result_map in methods_impacted.keys() or statement.include_sql in methods_impacted.keys():
                statement.diff_impact = mode
                methods_impacted[statement.name] = statement.__dict__


def _method_impact(method, line_num, methods_impacted, mode):
    line_num_in_method = False
    if method.start <= line_num <= method.end:
        line_num_in_method = True
        if method.name not in methods_impacted.keys():
            method.diff_impact = mode
            methods_impacted[method.name] = method.__dict__
    return line_num_in_method


def _diff_patch_lines(patch):
    line_num_added = []
    line_num_removed = []
    line_content_added = []
    line_content_removed = []
    for hunk in patch:
        if hunk.added > 0:
            targets = hunk.target
            target_start = hunk.target_start
            for i in range(0, len(targets)):
                if targets[i].startswith('+') and not targets[i][1:].strip().startswith(('*', '//', 'import ')):
                    line_num_added.append(target_start + i)
                    line_content_added.append(targets[i][1:])
        if hunk.removed > 0:
            sources = hunk.source
            source_start = hunk.source_start
            for i in range(0, len(sources)):
                if sources[i].startswith('-') and not sources[i][1:].strip().startswith(('*', '//', 'import ')):
                    line_num_removed.append(source_start + i)
                    line_content_removed.append(sources[i][1:])
    return line_num_added, line_content_added, line_num_removed, line_content_removed


# judge in imports, java_analyze类是不是再java_file_analyze里面
def _in_import(java_analyze, java_file_analyze):
    if java_file_analyze is None or java_file_analyze.imports is None \
            or java_file_analyze.imports.imports is None:
        return False, False
    class_path = f'{java_analyze.package_name}.{java_analyze.class_name}'
    class_path_analyze = f'{java_file_analyze.package_name}.{java_file_analyze.class_name}'
    if class_path_analyze == class_path \
            or java_file_analyze.package_name == java_analyze.package_name \
            or java_file_analyze.extends == class_path:
        return True, True
    implements = java_analyze.implements
    imports = java_file_analyze.imports.imports
    for import_obj in imports:
        if not import_obj.wildcard:
            if class_path == import_obj.path or import_obj.path in implements:
                return True, True
        else:
            class_path_parent = '.'.join(class_path.split('.')[0: -1])
            if class_path_parent == import_obj.path:
                return True, False
    for declarator in java_file_analyze.declarators:
        if declarator.type == java_analyze.class_name:
            return True, False
    return False, False


def _get_commit_project_files(folder_name, git_bash):
    java_file_analyze_result = {}
    os.system(git_bash)
    time.sleep(2)
    commit_files = _get_java_files(folder_name)

    for commit_file in commit_files:
        commit_file_result = None
        if commit_file.endswith('.java'):
            commit_file_result = _analyze_java_file(commit_file, folder_name)
        elif commit_file.endswith('.xml'):
            commit_file_result = parse(commit_file)
        if commit_file_result is not None:
            java_file_analyze_result[commit_file.replace(folder_name + os.sep, '').replace(os.sep, '/')] = commit_file_result
    return java_file_analyze_result


def _gen_treemap_data(diff_results, commit_first, commit_second):
    flare = {'name': f'{commit_second}..{commit_first}', 'children': []}
    api_list = []
    diff_results.reverse()
    diff_filepath = []
    for diff_result in diff_results:
        if diff_result.filepath in diff_filepath:
            continue
        diff_filepath.append(diff_result.filepath)
        class_name = diff_result.filepath.split('/')[-1].split('.')[0]
        if diff_result.filepath.endswith('.xml'):
            class_name = diff_result.filepath.split('/')[-1]
        flare_children = {'name': class_name, 'children': [], 'collapsed': True}
        flare_children_list = []
        changed_methods = diff_result.changed_methods
        for key, method_info in changed_methods.items():
            if method_info.get('is_api'):
                flare_children_children = {'name': 'methods.' + key + '(' + str(method_info['api_path']) + ')',
                                           'children': [], 'collapsed': True}
                api_list_item = {'name': str(method_info['api_path'])}
                if api_list_item not in api_list:
                    api_list.append(api_list_item)
            else:
                flare_children_children = {'name': 'methods.' + key, 'children': [], 'collapsed': True}
            if method_info.get('impact') is not None:
                for method_impact in method_info['impact']:
                    flare_children_sub = {'name': 'impacted.' + method_impact, 'children': [],
                                          'collapsed': True}
                    if flare_children_sub not in flare_children_children['children']:
                        flare_children_children['children'].append(flare_children_sub)
            flare_children_list.append(flare_children_children)
        changed_declarators = diff_result.changed_declarators
        for key, declarator_info in changed_declarators.items():
            flare_children_children = {'name': 'declarators.' + key, 'children': [], 'collapsed': True}
            if declarator_info.get('impact') is not None:
                for declarator_impact in declarator_info['impact']:
                    if declarator_impact == class_name + '.' + key:
                        continue
                    flare_children_sub = {'name': 'impacted.' + declarator_impact, 'children': [],
                                          'collapsed': True}
                    if flare_children_sub not in flare_children_children['children']:
                        flare_children_children['children'].append(flare_children_sub)
            flare_children_list.append(flare_children_children)
        flare_children['children'] = flare_children_list
        flare['children'].append(flare_children)
    flare['children'].reverse()
    flare['children'].insert(0, {'name': 'Impact_Apis', 'children': api_list})
    return flare


def _clean_occupy(occupy_path):
    if os.path.exists(occupy_path):
        os.remove(occupy_path)


def _class_in_method(class_name, method):
    if method.contains_declarators is not None:
        dcl_in_method = [d for d in method.contains_declarators if d['type'] == class_name]
        if len(dcl_in_method) > 0:
            return True
    method_content = str(method.content)
    class_str_list = [f'{class_name} ', f'<{class_name}>', f'{class_name}.']
    if any(key in method_content for key in class_str_list):
        return True
    else:
        return False


def _declarator_in_method(declarators, method):
    method_content = str(method.content)
    declarator_in_method = []
    for declarator in declarators:
        declarator_capitalize = declarator[0].upper() + declarator[1:]
        keywords = [f'.{declarator}', f'.get{declarator_capitalize}(', f'.set{declarator_capitalize}(']
        if any(keyword in method_content for keyword in keywords):
            declarator_in_method.append(declarator)
    return declarator_in_method


def _method_override(method, extend_methods):
    extend_methods = [extend_method for extend_method in extend_methods if extend_method.name == method.name]
    if len(extend_methods) == 0:
        return False
    method_param_type = [param.type for param in method.params]
    for extend_method in extend_methods:
        if 'Override' not in extend_method.annotations:
            continue
        extend_method_param_type = [param.type for param in extend_method.params]
        if method_param_type == extend_method_param_type:
            return True
    return False


def _diff_result_impact(diff_result_item_index, diff_results_list, which_java_file_analyze_result, mode):
    diff_result_item = diff_results_list[diff_result_item_index]
    diff_result_filepath = diff_result_item.filepath
    if diff_result_filepath in which_java_file_analyze_result.keys():
        which_java_analyze = which_java_file_analyze_result[diff_result_filepath]
        if diff_result_filepath.endswith('.xml'):
            _diff_xml_impact(diff_result_item_index, diff_results_list, which_java_file_analyze_result, mode)
            return
        which_class_name = which_java_analyze.class_name
        which_class_path = which_java_analyze.package_name + '.' + which_java_analyze.class_name
        which_implements = which_java_analyze.implements
        which_implements.append(which_class_path)
        for which_java_file_analyze_key, which_java_file_analyze in which_java_file_analyze_result.items():
            if which_java_file_analyze_key.endswith('.xml'):
                continue
            which_java_file_extends = which_java_file_analyze.extends
            which_java_file_analyze_extends_list = [value for value in which_java_file_analyze_result.values()
                                                    if type(value) == JavaAnalyzer and
                                                    (value.package_name + '.' + value.class_name == which_java_file_extends or value.class_name == which_java_file_extends)
                                                    ]
            which_java_file_analyze_extends = None
            if len(which_java_file_analyze_extends_list) > 0:
                which_java_file_analyze_extends = which_java_file_analyze_extends_list[0]
                which_java_file_analyze.imports.imports += which_java_file_analyze_extends.imports.imports
                which_java_file_analyze.declarators += which_java_file_analyze_extends.declarators
                which_java_file_analyze.methods += [method for method in which_java_file_analyze_extends.methods if not _method_override(method, which_java_file_analyze.methods)]

            is_in, directly = _in_import(which_java_analyze, which_java_file_analyze)
            if not is_in:
                continue
            which_java_file_methods = which_java_file_analyze.methods
            which_java_file_declarators = [declarator for declarator in which_java_file_analyze.declarators
                                           if declarator.type == which_class_name or
                                           declarator.res_name == which_class_name or
                                           declarator.res_type == which_class_path or
                                           declarator.contains_class == which_implements[0]
                                           ]
            extends_changed = len(diff_result_item.changed_declarators.keys()) > 0 \
                              and which_java_file_analyze_extends is not None \
                              and f'{which_java_file_analyze_extends.package_name}.{which_java_file_analyze_extends.class_name}' == which_class_path
            if extends_changed:
                java_file_class_path = which_java_file_analyze.package_name + '.' + which_java_file_analyze.class_name
                if java_file_class_path not in diff_result_item.impact.keys():
                    diff_result_item.impact[java_file_class_path] = {'declarators': [decl for decl in diff_result_item.changed_declarators.values()]}
                elif diff_result_item.impact[java_file_class_path].get('declarators') is None:
                    diff_result_item.impact[java_file_class_path]['declarators'] = [decl for decl in diff_result_item.changed_declarators.values()]
                else:
                    diff_result_item.impact[java_file_class_path]['declarators'] += [decl for decl in diff_result_item.changed_declarators.values() if decl not in diff_result_item.impact[java_file_class_path]['declarators']]
                changed_declar = [decl['name'] for decl in diff_result_item.impact[java_file_class_path]['declarators'] if decl.get('name') is not None]
                for tmp_declar in changed_declar:
                    impact_declar = which_java_file_analyze.class_name + '.' + tmp_declar
                    if diff_result_item.changed_declarators.get(tmp_declar) is None:
                        impact_declar_obj = [decl_dict for decl_dict in which_java_file_analyze.declarators if decl_dict.name == tmp_declar][0]
                        impact_declar_obj.diff_impact = mode
                        impact_declar_dict = impact_declar_obj.__dict__
                        impact_declar_dict['impact'] = []
                        diff_result_item.changed_declarators[tmp_declar] = impact_declar_dict
                    elif diff_result_item.changed_declarators[tmp_declar].get('impact') is None:
                        diff_result_item.changed_declarators[tmp_declar]['impact'] = [impact_declar]
                    else:
                        diff_result_item.changed_declarators[tmp_declar]['impact'].append(impact_declar)
                diff_result_need_add = JavaDiffResult(which_java_file_analyze_key, None, None, None, None)
                index = -1
                for i in range(len(diff_results_list) - 1, -1, -1):
                    if diff_results_list[i] is None:
                        continue
                    if diff_results_list[i].filepath == which_java_file_analyze_key:
                        diff_result_need_add = JavaDiffResult(diff_results_list[i].filepath,
                                                              diff_results_list[i].added_line_nums,
                                                              diff_results_list[i].added_line_contents,
                                                              diff_results_list[i].removed_line_nums,
                                                              diff_results_list[i].removed_line_contents)
                        diff_result_need_add.impact = diff_results_list[i].impact.copy()
                        diff_result_need_add.changed_methods = diff_results_list[i].changed_methods.copy()
                        diff_result_need_add.changed_declarators = diff_results_list[i].changed_declarators.copy()
                        index = i
                        break
                diff_result_need_add.changed_declarators.update(diff_result_item.changed_declarators)
                if index > diff_result_item_index:
                    diff_results_list[index] = diff_result_need_add
                else:
                    diff_results_list.append(diff_result_need_add)

            for which_java_file_method in which_java_file_methods:
                classname_in_method = False
                tmp = []
                declarator_in_method_key = []
                if diff_result_item.changed_declarators != {}:
                    classname_in_method = _class_in_method(which_class_name, which_java_file_method)
                    if classname_in_method:
                        declarator_in_method_key = _declarator_in_method(diff_result_item.changed_declarators.keys(), which_java_file_method)
                if which_java_file_method.contains_class is not None:
                    for implement in which_implements:
                        implement_name = implement.split('.')[-1]
                        if implement in which_java_file_method.contains_class.keys() and 'methods' in \
                                which_java_file_method.contains_class[implement].keys():
                            java_file_method_includes_methods = which_java_file_method.contains_class[implement]['methods']
                            tmp += [diff_result_item.changed_methods[j] for j in diff_result_item.changed_methods.keys()
                                    if mode in diff_result_item.changed_methods[j]['diff_impact'] and j in java_file_method_includes_methods]
                        elif implement_name in which_java_file_method.contains_class.keys() and 'methods' in \
                                which_java_file_method.contains_class[implement_name].keys():
                            java_file_method_includes_methods = which_java_file_method.contains_class[implement_name]['methods']
                            tmp += [diff_result_item.changed_methods[j] for j in diff_result_item.changed_methods.keys()
                                    if mode in diff_result_item.changed_methods[j]['diff_impact'] and j in java_file_method_includes_methods]
                if len(tmp) == 0:
                    method_content_str = str(which_java_file_method.content)
                    tmp += [diff_result_item.changed_methods[j] for j in diff_result_item.changed_methods.keys() if
                            mode in diff_result_item.changed_methods[j]['diff_impact']
                            and ('(' + j + '(' in method_content_str
                                 or '=' + j + '(' in method_content_str
                                 or '= ' + j + '(' in method_content_str
                                 or which_class_name + '.' + j + '(' in method_content_str
                                 )
                            ]
                    for declarator in which_java_file_declarators:
                        tmp += [diff_result_item.changed_methods[j] for j in diff_result_item.changed_methods.keys() if
                                mode in diff_result_item.changed_methods[j]['diff_impact']
                                and declarator.name + '.' + j + '(' in method_content_str
                                ]
                if len(tmp) > 0 or classname_in_method:
                    ##
                    impact_method = which_java_file_analyze.class_name + '.' + which_java_file_method.name
                    if which_java_file_method.is_api:
                        impact_method += '(' + str(which_java_file_method.api_path) + ')'
                    if len(tmp) > 0:
                        for tmp_method in tmp:
                            if tmp_method.get('impact') is None:
                                tmp_method['impact'] = []
                            if impact_method not in tmp_method.get('impact'):
                                tmp_method_name = tmp_method['name']
                                tmp_method['impact'].append(impact_method)
                                diff_result_item.changed_methods[tmp_method_name] = tmp_method
                    if classname_in_method:
                        for declarator_key in declarator_in_method_key:
                            if diff_result_item.changed_declarators[declarator_key].get('impact') is None:
                                diff_result_item.changed_declarators[declarator_key]['impact'] = []
                            if impact_method not in diff_result_item.changed_declarators[declarator_key]['impact']:
                                diff_result_item.changed_declarators[declarator_key]['impact'].append(impact_method)
                    ##
                    if which_java_file_method.diff_impact is None or which_java_file_method.diff_impact != '':
                        which_java_file_method.diff_impact = mode
                    else:
                        which_java_file_method.diff_impact = which_java_file_method.diff_impact + '_' + mode
                    java_file_class_path = which_java_file_analyze.package_name + '.' + which_java_file_analyze.class_name
                    if java_file_class_path not in diff_result_item.impact.keys():
                        diff_result_item.impact[java_file_class_path] = {'methods': [which_java_file_method.__dict__]}
                    elif diff_result_item.impact[java_file_class_path].get('methods') is None:
                        diff_result_item.impact[java_file_class_path]['methods'] = [which_java_file_method.__dict__]
                    elif which_java_file_method.__dict__ not in diff_result_item.impact[java_file_class_path]['methods']:
                        diff_result_item.impact[java_file_class_path]['methods'].append(which_java_file_method.__dict__)
                    diff_result_need_add = JavaDiffResult(which_java_file_analyze_key, None, None, None, None)
                    index = -1
                    for i in range(len(diff_results_list) - 1, -1, -1):
                        if diff_results_list[i] is None:
                            continue
                        if diff_results_list[i].filepath == which_java_file_analyze_key:
                            diff_result_need_add = JavaDiffResult(diff_results_list[i].filepath,
                                                                  diff_results_list[i].added_line_nums,
                                                                  diff_results_list[i].added_line_contents,
                                                                  diff_results_list[i].removed_line_nums,
                                                                  diff_results_list[i].removed_line_contents)
                            diff_result_need_add.impact = diff_results_list[i].impact.copy()
                            diff_result_need_add.changed_methods = diff_results_list[i].changed_methods.copy()
                            diff_result_need_add.changed_declarators = diff_results_list[i].changed_declarators.copy()
                            index = i
                            break
                    if which_java_file_method.name not in diff_result_need_add.changed_methods.keys():
                        # or diff_result_need_add.changed_methods[
                        #         which_java_file_method.name] != which_java_file_method.__dict__:
                        diff_result_need_add.changed_methods[
                            which_java_file_method.name] = which_java_file_method.__dict__
                        if index > diff_result_item_index:
                            diff_results_list[index] = diff_result_need_add
                        else:
                            diff_results_list.append(diff_result_need_add)


def _diff_xml_impact(diff_result_item_index, diff_results_list, which_java_file_analyze_result, mode):
    diff_result_item = diff_results_list[diff_result_item_index]
    diff_result_filepath = diff_result_item.filepath
    which_java_analyze = which_java_file_analyze_result[diff_result_filepath]
    namespace = which_java_analyze.namespace
    namespace_java_result_list = [key for key in which_java_file_analyze_result.keys()
                                  if not key.endswith('.xml') and which_java_file_analyze_result[key].package_name
                                  + '.' + which_java_file_analyze_result[key].class_name == namespace]
    if len(namespace_java_result_list) == 0:
        return
    namespace_java_path = namespace_java_result_list[0]
    namespace_java_result = which_java_file_analyze_result[namespace_java_path]
    for changed_method_key, changed_method in diff_result_item.changed_methods.items():
        if changed_method['diff_impact'] != mode:
            continue
        if changed_method.get('impact') is None:
            changed_method['impact'] = []
        for namespace_java_method in namespace_java_result.methods:
            impact_method = namespace_java_result.class_name + '.' + namespace_java_method.name
            if namespace_java_method.name == changed_method['name'] and impact_method not in changed_method['impact']:
                changed_method['impact'].append(impact_method)
                namespace_java_method.diff_impact = mode
                diff_result_need_add = JavaDiffResult(namespace_java_path, None, None, None, None)
                index = -1
                for i in range(len(diff_results_list) - 1, -1, -1):
                    if diff_results_list[i] is None:
                        continue
                    if diff_results_list[i].filepath == namespace_java_path:
                        diff_result_need_add = JavaDiffResult(diff_results_list[i].filepath,
                                                              diff_results_list[i].added_line_nums,
                                                              diff_results_list[i].added_line_contents,
                                                              diff_results_list[i].removed_line_nums,
                                                              diff_results_list[i].removed_line_contents)
                        diff_result_need_add.impact = diff_results_list[i].impact.copy()
                        diff_result_need_add.changed_methods = diff_results_list[i].changed_methods.copy()
                        diff_result_need_add.changed_declarators = diff_results_list[i].changed_declarators.copy()
                        index = i
                        break
                if namespace_java_method.name not in diff_result_need_add.changed_methods.keys():
                    diff_result_need_add.changed_methods[
                        namespace_java_method.name] = namespace_java_method.__dict__
                    if index > diff_result_item_index:
                        diff_results_list[index] = diff_result_need_add
                    else:
                        diff_results_list.append(diff_result_need_add)


# Press the green button in the gutter to run the script.
def analyze(project_git_url, branch_name, commit_first, commit_second, request_user):
    if len(commit_first) > 7:
        commit_first = commit_first[0: 7]
    if len(commit_second) > 7:
        commit_second = commit_second[0: 7]
    t1 = datetime.datetime.now()
    logging.info('*' * 10 + 'Analyze start' + '*' * 10)
    project_name = project_git_url.split('/')[-1].split('.git')[0]
    folder_name = os.path.join(os.getcwd(), project_name)
    git_clone_bash = f'git clone -b {branch_name} {project_git_url} {folder_name}'
    git_pull_base = f'cd {folder_name} && git checkout {branch_name} && git pull'
    diff_base = f'cd {folder_name} && git diff {commit_second}..{commit_first} > diff_{commit_second}..{commit_first}.txt'
    occupy_filepath = os.path.join(folder_name, 'Occupy.ing')
    atexit.register(_clean_occupy, occupy_filepath)
    cci_filepath = os.path.join(folder_name, f'{commit_second}..{commit_first}.cci')
    if not os.path.exists(folder_name):
        logging.info(f'Cloning project: {project_git_url}')
        os.system(git_clone_bash)
    else:
        # had analyze result, skip
        if os.path.exists(cci_filepath):
            logging.info('Has analyze result, skip!')
            with open(cci_filepath, 'r') as read:
                logging.info(read.read())
            sys.exit(0)
        else:
            # analyzing, wait
            wait_index = 0
            while os.path.exists(occupy_filepath) and wait_index < 30:
                logging.info(f'Analyzing by others, waiting or clean occupying file manually at: {occupy_filepath} to continue')
                time.sleep(3)
                wait_index += 1
    logging.info('Start occupying project, and others can not analyze until released')
    with open(occupy_filepath, 'w') as ow:
        ow.write(f'Occupy by {request_user}')
    time.sleep(1)
    logging.info('Git pull project to HEAD')
    os.system(git_pull_base)
    time.sleep(1)
    logging.info(f'Git diff between {commit_second} and {commit_first}')
    os.system(diff_base)
    time.sleep(1)
    logging.info(f'Get all commit_id:{commit_second} files')
    base_java_file_analyze_result = _get_commit_project_files(folder_name, f'cd {folder_name} && git reset --hard {commit_second}')
    logging.info(f'Get all commit_id:{commit_first} files')
    head_java_file_analyze_result = _get_commit_project_files(folder_name, f'cd {folder_name} && git reset --hard {commit_first}')
    diff_txt = os.path.join(folder_name, f'diff_{commit_second}..{commit_first}.txt')
    logging.info(f'Analyzing diff file, location: {diff_txt}')
    diff_results = _get_diff_results(diff_txt, head_java_file_analyze_result, base_java_file_analyze_result)
    diff_result_index = 0
    for diff_result in diff_results:
        if diff_result is None:
            continue
        logging.info(f'Analyzing diff/impact file: {diff_result.filepath}')
        _diff_result_impact(diff_result_index, diff_results, head_java_file_analyze_result, 'ADD')
        _diff_result_impact(diff_result_index, diff_results, base_java_file_analyze_result, 'DEL')
        diff_result_index = diff_result_index + 1
    logging.info(f'Analyze success, generating cci result file......')
    flare = _gen_treemap_data(diff_results, commit_first, commit_second)
    logging.info(json.dumps(flare))
    with open(cci_filepath, 'w') as w:
        w.write(json.dumps(flare))
    logging.info(f'Generating cci result file success, location: {cci_filepath}')
    t2 = datetime.datetime.now()
    try:
        logging.info(f'Analyze done, remove occupy, others can analyze now')
        os.remove(occupy_filepath)
    finally:
        pass
    logging.info(f'Analyze done, spend: {t2 - t1}')

#
# has some bug, can't use
# def analyze_branches(project_git_url, branch_name_first, branch_name_second, request_user):
#     t1 = datetime.datetime.now()
#     logging.info('*' * 10 + 'Analyze start' + '*' * 10)
#     project_name = project_git_url.split('/')[-1].split('.git')[0]
#     folder_name = os.path.join(os.getcwd(), project_name)
#     git_clone_bash = f'git clone -b {branch_name_first} {project_git_url} {folder_name}'
#     diff_txt = re.sub(r'[\/:?<>|]', '#', f'diff_{branch_name_second}..{branch_name_first}.txt')
#     diff_base = f'cd {folder_name} && git diff {branch_name_first} {branch_name_second} > {diff_txt}'
#     occupy_filepath = os.path.join(folder_name, 'Occupy.ing')
#     atexit.register(_clean_occupy, occupy_filepath)
#     cci_filepath = os.path.join(folder_name, re.sub(r'[\/:?<>|]', '#', f'{branch_name_second}..{branch_name_first}.cci'))
#     if not os.path.exists(folder_name):
#         logging.info(f'Cloning project: {project_git_url}')
#         os.system(git_clone_bash)
#     else:
#         # had analyze result, skip
#         if os.path.exists(cci_filepath):
#             logging.info('Has analyze result, skip!')
#             with open(cci_filepath, 'r') as read:
#                 logging.info(read.read())
#             sys.exit(0)
#         else:
#             # analyzing, wait
#             wait_index = 0
#             while os.path.exists(occupy_filepath) and wait_index < 30:
#                 logging.info(f'Analyzing by others, waiting or clean occupying file manually at: {occupy_filepath} to continue')
#                 time.sleep(3)
#                 wait_index += 1
#     logging.info('Start occupying project, and others can not analyze until released')
#     with open(occupy_filepath, 'w') as ow:
#         ow.write(f'Occupy by {request_user}')
#     time.sleep(1)
#     logging.info(f'Git diff between {branch_name_second} and {branch_name_first}')
#     os.system(diff_base)
#     time.sleep(3)
#     logging.info(f'Get all branch:{branch_name_first} files')
#     base_java_file_analyze_result = _get_commit_project_files(folder_name, f'cd {folder_name}')
#     logging.info(f'Get all branch:{branch_name_second} files')
#     head_java_file_analyze_result = _get_commit_project_files(folder_name, f'cd {folder_name} && git checkout {branch_name_second}')
#     diff_txt_path = os.path.join(folder_name, diff_txt)
#     logging.info(f'Analyzing diff file, location: {diff_txt_path}')
#     diff_results = _get_diff_results(diff_txt_path, head_java_file_analyze_result, base_java_file_analyze_result)
#     diff_result_index = 0
#     for diff_result in diff_results:
#         if diff_result is None:
#             continue
#         logging.info(f'Analyzing diff/impact file: {diff_result.filepath}')
#         _diff_result_impact(diff_result_index, diff_results, head_java_file_analyze_result, 'ADD')
#         _diff_result_impact(diff_result_index, diff_results, base_java_file_analyze_result, 'DEL')
#         diff_result_index = diff_result_index + 1
#     logging.info(f'Analyze success, generating cci result file......')
#     flare = _gen_treemap_data(diff_results, branch_name_first, branch_name_second)
#     logging.info(json.dumps(flare))
#     with open(cci_filepath, 'w') as w:
#         w.write(json.dumps(flare))
#     logging.info(f'Generating cci result file success, location: {cci_filepath}')
#     t2 = datetime.datetime.now()
#     try:
#         logging.info(f'Analyze done, remove occupy, others can analyze now')
#         os.remove(occupy_filepath)
#     finally:
#         pass
#     logging.info(f'Analyze done, spend: {t2 - t1}')


