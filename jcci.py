# -*- coding: UTF-8 -*-
import datetime
import json
import os
import sys
import time
import javalang
from unidiff import PatchSet
from .java_analyzer import JavaAnalyzer, JavaImports, JavaMethods, JavaDeclarators, JavaDiffResult
import atexit

sep = os.sep


# get all java files
def _get_java_files(dir_path):
    file_lists = []
    file_or_dir_list = os.walk(dir_path)
    for filepath, dir_names, file_names in file_or_dir_list:
        if '.git' in filepath or 'src' + sep + 'test' + sep in filepath:
            continue
        for filename in file_names:
            if filename.endswith('.java'):
                full_file_path = filepath + sep + filename
                file_lists.append(full_file_path)
    return file_lists


# analyze and return：{
# 	'filepath': '/path',
# 	'package_name': 'com.tal.wangxiao.conan.admin.controller',
# 	'imports': {
# 		'start': 3,
# 		'end': 10,
# 		'imports': ['com.tal.wangxiao.conan.common.domain.ApiInfo',
# 			'com.tal.wangxiao.conan.common.service.ApiService'
# 		]
# 	},
# 	'class_name': 'ApiController',
# 	'extends': 'ConanBaseController',
# 	'implements': ['a', 'b'],
# 	'declarators': [{
# 		'type': 'ApiService',
# 		'name': 'apiService',
#       'line': 46,
#       'contains_class': 'com.tal.wangxiao.conan.common.service.ApiService'
# 	}],
# 	'methods': [{
# 		'name': 'list',
# 		'start': 55,
# 		'end': 62,
# 		'content': 'public ApiResponse<PageInfoResponse<List<ApiInfo>>> list(ApiInfo api).....'
#       'contains_class': {
#           'com.tal.wangxiao.conan.common.service.ApiService': {
#               'methods': ['selectApiList']
#            }
#        }
#       'contains_declarators': ['abc','def']
# 	}]
# }
#
def _analyze_java_file(filepath, folder_name):
    print(filepath)
    if 'InsightsFeeController' in filepath:
        print("debug")
    import_list = []
    with open(filepath, encoding='UTF-8') as fp:
        file_content = fp.read()
    lines = file_content.split('\n')
    try:
        tree = javalang.parse.parse(file_content)
        package_name = tree.package.name
        types = tree.types[0]
        class_name = types.name
    except:
        return None
    # is controller or not
    is_controller = False
    base_request = ''
    annotations = types.annotations
    for annotation in annotations:
        if 'Controller' in annotation.name:
            is_controller = True
        if 'RequestMapping' == annotation.name:
            if type(annotation.element) != type([]):
                if annotation.element is not None:
                    if 'value' in annotation.element.attrs:
                        base_request = annotation.element.value.replace('"', '')
                    elif 'values' in annotation.element.attrs:
                        # print(annotation.element.values)
                        base_request = ' || '.join([literal.value for literal in annotation.element.values])
            else:
                base_request_list = [annotation_element.value.value.replace('"', '')
                                     for annotation_element in annotation.element
                                     if annotation_element.name == 'value' or annotation_element.name == 'path']
                if len(base_request_list) > 0:
                    base_request = base_request_list[0]
    if is_controller and not base_request.endswith('/'):
        base_request += '/'
    class_path = package_name + '.' + class_name
    extends_name = types.extends.name \
        if 'extends' in types.attrs and types.extends is not None \
           and type(types.extends) != type([]) else None
    extends_name_path = extends_name
    implements_names = [implement.name for implement in types.implements] \
        if 'implements' in types.attrs and types.implements is not None else None
    implements_names_list = []
    import_path_class_map = {}
    for import_Obj in tree.imports:
        import_path = import_Obj.path
        if not import_path.startswith('com.'):
            continue
        if not import_Obj.wildcard and not import_Obj.static:
            import_path_class = import_path.split('.')[-1]
            import_path_class_map[import_path_class] = import_path
            import_list.append(import_path)
            if extends_name and import_path.endswith(extends_name):
                extends_name_path = import_path
            if implements_names and import_path_class in implements_names:
                implements_names_list.append(import_path)
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
        if field_type in import_path_class_map.keys():
            field_map.contains_class = import_path_class_map[field_type]
        fields_list.append(field_map)

    methods_list = []
    methods_name_list = [method.name for method in types.methods]
    for method_obj in types.methods:
        method_name = method_obj.name
        method_start_line = method_obj.position.line
        if method_obj.annotations:
            method_start_line = method_obj.annotations[0].position.line
        method_end_line = _get_method_end_line(method_obj)
        method_content = lines[method_start_line - 1: method_end_line]
        # method is api or not
        is_api = False
        api_path_list = []
        if is_controller:
            method_annotations = method_obj.annotations
            req_method_list = []
            method_api_path = []
            for method_annotation in method_annotations:
                if 'Mapping' in method_annotation.name:
                    is_api = True
                    if method_annotation.name != 'RequestMapping':
                        req_method_list.append(method_annotation.name.replace('Mapping', ''))
                    else:
                        if type(method_annotation.element) == type([]):
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
                    if type(method_annotation.element) != type([]):
                        if method_annotation.element is not None and method_annotation.element.value is not None:
                            method_api_path += [method_annotation.element.value.replace('"', '')]
                    else:
                        method_api_path_list = [method_annotation_element.value for method_annotation_element in
                                                method_annotation.element
                                                if
                                                method_annotation_element.name == 'path' or method_annotation_element.name == 'value']
                        if len(method_api_path_list) > 0:
                            method_api_path_obj = method_api_path_list[0]
                            if 'value' in method_api_path_obj.attrs:
                                method_api_path += [method_api_path_obj.value.replace('"', '')]
                            else:
                                if 'values' in method_api_path_obj.attrs:
                                    method_api_path += [method_api_value.value.replace('"', '') for method_api_value in
                                                        method_api_path_obj.values]
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
                for req_method_temp in req_method_list:
                    full_api = '[' + req_method_temp + ']' + api_path
                    api_path_list.append(full_api)
        method_map = JavaMethods(method_name, method_start_line, method_end_line, method_content, is_api, api_path_list)
        # imports in this method or not
        for import_path_class in import_path_class_map.keys():
            if import_path_class in method_content:
                if import_path_class_map[import_path_class] not in method_map['contains_class']:
                    method_map.contains_class[import_path_class_map[import_path_class]] = {}
        # declarator in this method or not
        declarator_tmp_final = None
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
        for methods_name in methods_name_list:
            for method_content_line in method_content:
                if ' ' + methods_name + '(' in method_content_line and not method_content_line.endswith("{"):
                    if class_path not in method_map.contains_class.keys():
                        method_map.contains_class[class_path] = {'methods': [methods_name]}
                    else:
                        if 'methods' in method_map.contains_class[class_path].keys():
                            method_map.contains_class[class_path]['methods'].append(methods_name)
                        else:
                            method_map.contains_class[class_path] = {'methods': [methods_name]}
        if 'body' in method_obj.attrs and method_obj.body is not None:
            for method_body in method_obj.body:
                if str(type(method_body)) == "<class 'javalang.tree.LocalVariableDeclaration'>":
                    if 'type' in method_body.attrs and 'name' in method_body.type.attrs \
                            and method_body.type.name in import_path_class_map.keys() \
                            and 'declarators' in method_body.attrs \
                            and type(method_body.declarators) == type([]) \
                            and len(method_body.declarators) > 0:
                        class_method_list = []
                        if import_path_class_map.get(method_body.type.name) not in method_map.contains_class.keys():
                            method_map.contains_class[import_path_class_map.get(method_body.type.name)] = {}
                        else:
                            if 'methods' in method_map.contains_class[
                                import_path_class_map.get(method_body.type.name)].keys():
                                class_method_list = \
                                    method_map.contains_class[import_path_class_map.get(method_body.type.name)][
                                        'methods']
                        for method_content_line in method_content:
                            if method_body.declarators[0].name in method_content_line and len(
                                    method_content_line.split(method_body.declarators[0].name + '.')) > 1:
                                class_method = \
                                    method_content_line.split(method_body.declarators[0].name + '.')[1].split('(')[0]
                                if class_method not in class_method_list:
                                    class_method_list.append(class_method)
                        method_map.contains_class[import_path_class_map.get(method_body.type.name)][
                            'methods'] = class_method_list
                        # method_obj.append(method_body.declarators[0].name)
        methods_list.append(method_map)
    file_analyze = JavaAnalyzer(filepath.replace(sep, '/').replace(folder_name + '/', ''), package_name, class_name,
                                extends_name_path, is_controller)
    file_analyze.imports = imports
    file_analyze.implements = implements_names_list
    file_analyze.declarators = fields_list
    file_analyze.methods = methods_list
    return file_analyze


def _get_method_end_line(method_obj):
    method_end_line = method_obj.position.line
    if method_obj.body is not None and len(method_obj.body) > 0:
        method_end_line = method_obj.body[-1].position.line
        method_body = method_obj.body[-1]
        while True:
            method_obj_dict = method_body.__dict__
            method_last_attr = method_body.attrs[-1]
            if type(method_obj_dict[method_last_attr]) == type([]):
                if len(method_obj_dict[method_last_attr]) < 1:
                    break
                method_body = method_obj_dict[method_last_attr][-1]
                if type(method_body.__dict__[method_body.attrs[-1]]) == type([]) \
                        and len(method_body.__dict__[method_body.attrs[-1]]) == 0 \
                        and len(method_obj_dict[method_last_attr]) > 1:
                    method_body = method_obj_dict[method_last_attr][-2]
            elif type(method_obj_dict[method_last_attr]) == type(''):
                return method_end_line + 1
            else:
                if method_obj_dict[method_last_attr] is None:
                    if '_position' in method_obj_dict.keys():
                        method_end_line = method_obj_dict['_position'].line
                    return method_end_line + 1
                method_obj_dict_dict = method_obj_dict[method_last_attr].__dict__
                method_body = method_obj_dict[method_last_attr]
                if '_position' in method_obj_dict_dict.keys():
                    method_end_line = method_obj_dict[method_last_attr].position.line
                else:
                    return method_end_line + 1
    return method_end_line + 1


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
    if '.git' in patch.path or 'src' + sep + 'test' + sep in patch.path or not patch.path.endswith('.java'):
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
    java_analyze = java_file_analyze_result[
        java_file_path] if java_file_path in java_file_analyze_result.keys() else None
    if java_analyze is not None:
        java_methods = java_analyze.methods
        for line_num_index in range(0, len(line_num_mode)):
            line_num = line_num_mode[line_num_index]
            line_num_in_method = False
            for method in java_methods:
                if method.start <= line_num <= method.end:
                    line_num_in_method = True
                    if method.name not in methods_impacted.keys():
                        method.diff_impact = mode
                        methods_impacted[method.name] = method.__dict__
            if not line_num_in_method:
                java_declarators = java_analyze.declarators
                for declarator in java_declarators:
                    if line_num == declarator.line:
                        declarator.diff_impact = mode
                        declarators_impacted[declarator.name] = declarator.__dict__


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
                if targets[i].startswith('+') \
                        and not targets[i][1:].strip().startswith('*') \
                        and not targets[i][1:].strip().startswith('//') \
                        and not targets[i][1:].strip().startswith('import '):
                    line_num_added.append(target_start + i + 1)
                    line_content_added.append(targets[i][1:])
        if hunk.removed > 0:
            sources = hunk.source
            source_start = hunk.source_start
            for i in range(0, len(sources)):
                if sources[i].startswith('-') \
                        and not sources[i][1:].strip().startswith('*') \
                        and not sources[i][1:].strip().startswith('//') \
                        and not sources[i][1:].strip().startswith('import '):
                    line_num_removed.append(source_start + i + 1)
                    line_content_removed.append(sources[i][1:])
    return line_num_added, line_content_added, line_num_removed, line_content_removed


# judge in imports, java_analyze类是不是再java_file_analyze里面
def _in_import(java_analyze, java_file_analyze):
    if java_file_analyze is None or java_file_analyze.imports is None \
            or java_file_analyze.imports.imports is None:
        return False, False
    class_path = java_analyze.package_name + '.' + java_analyze.class_name
    implements = java_analyze.implements
    imports = java_file_analyze.imports.imports
    class_path_analyze = java_file_analyze.package_name + '.' + java_file_analyze.class_name
    if class_path_analyze == class_path:
        return True, True
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


def _get_commit_project_files(commit_id, folder_name):
    java_file_analyze_result = {}
    git_bash = 'cd ' + folder_name + ' && ' + 'git reset --hard ' + commit_id
    os.system(git_bash)
    time.sleep(1)
    commit_files = _get_java_files(folder_name)

    for commit_file in commit_files:
        commit_file_result = _analyze_java_file(commit_file, folder_name)
        if commit_file_result is not None:
            java_file_analyze_result[commit_file.replace(folder_name + sep, '').replace(sep, '/')] = commit_file_result
    return java_file_analyze_result


def _gen_treemap_data(diff_results, commit_first, commit_second):
    flare = {'name': commit_second + '..' + commit_first, 'children': []}
    api_list = []
    diff_results.reverse()
    diff_filepath = []
    for diff_result in diff_results:
        if diff_result.filepath in diff_filepath:
            continue
        diff_filepath.append(diff_result.filepath)
        class_name = diff_result.filepath.split('/')[-1].split('.')[0]
        flare_children = {'name': class_name, 'children': [], 'collapsed': True}
        flare_children_list = []
        changed_methods = diff_result.changed_methods
        for key in changed_methods.keys():
            if changed_methods[key]['is_api']:
                flare_children_children = {'name': 'methods.' + key + '(' + str(changed_methods[key]['api_path']) + ')',
                                           'children': [], 'collapsed': True}
                api_list_item = {'name': str(changed_methods[key]['api_path'])}
                if api_list_item not in api_list:
                    api_list.append(api_list_item)
            else:
                flare_children_children = {'name': 'methods.' + key, 'children': [], 'collapsed': True}
            flare_children_list.append(flare_children_children)
        changed_declarators = diff_result.changed_declarators
        for key in changed_declarators.keys():
            flare_children_children = {'name': 'declarators.' + key, 'children': [], 'collapsed': True}
            flare_children_list.append(flare_children_children)
        impact = diff_result.impact
        for key in impact.keys():
            tmp_impact_class_name = key.split('.')[-1]
            if 'methods' in impact[key].keys():
                impact_methods = impact[key]['methods']
                for impact_method in impact_methods:
                    impact_method_name = impact_method['name']
                    if impact_method['is_api']:
                        flare_children_children = {
                            'name': 'impacted.' + tmp_impact_class_name + '.' + impact_method_name + '(' + str(
                                impact_method['api_path']) + ')',
                            'children': [], 'collapsed': True}
                        api_list_item = {'name': str(impact_method['api_path'])}
                        if api_list_item not in api_list:
                            api_list.append(api_list_item)
                    else:
                        flare_children_children = {
                            'name': 'impacted.' + tmp_impact_class_name + '.' + impact_method_name,
                            'children': [], 'collapsed': True}
                    if 'contains_class' in impact_method.keys() and len(impact_method['contains_class'].keys()) > 0:
                        for impact_method_cc_key in impact_method['contains_class'].keys():
                            if 'methods' in impact_method['contains_class'][impact_method_cc_key].keys():
                                for impact_method_cc_m in impact_method['contains_class'][impact_method_cc_key][
                                    'methods']:
                                    if impact_method_cc_m in changed_methods.keys():
                                        for flare_children_list_item in flare_children_list:
                                            if 'methods.' + impact_method_cc_m in flare_children_list_item['name']:
                                                flare_children_list_item_index = flare_children_list.index(
                                                    flare_children_list_item)
                                                if impact_method['is_api']:
                                                    flare_children_list_item_children = {
                                                        'name': 'impacted.' + tmp_impact_class_name + '.' + impact_method_name + '(' + str(
                                                            impact_method['api_path']) + ')',
                                                        'children': [], 'collapsed': True}
                                                    api_list_item = {'name': str(impact_method['api_path'])}
                                                    if api_list_item not in api_list:
                                                        api_list.append(api_list_item)
                                                else:
                                                    flare_children_list_item_children = {
                                                        'name': 'impacted.' + tmp_impact_class_name + '.' + impact_method_name,
                                                        'children': [], 'collapsed': True}
                                                if flare_children_list_item_children not in flare_children_list_item[
                                                    'children']:
                                                    flare_children_list_item['children'].append(
                                                        flare_children_list_item_children)
                                                flare_children_list[
                                                    flare_children_list_item_index] = flare_children_list_item
                                            else:
                                                if flare_children_children not in flare_children_list:
                                                    flare_children_list.append(flare_children_children)
                                    else:
                                        if flare_children_children not in flare_children_list:
                                            flare_children_list.append(flare_children_children)
                            else:
                                if flare_children_children not in flare_children_list:
                                    flare_children_list.append(flare_children_children)
                    else:
                        if flare_children_children not in flare_children_list:
                            flare_children_list.append(flare_children_children)
            else:
                flare_children_children = {'name': 'impacted.' + tmp_impact_class_name, 'children': [],
                                           'collapsed': True}
                if flare_children_children not in flare_children_list:
                    flare_children_list.append(flare_children_children)
        flare_children['children'] = flare_children_list
        flare['children'].append(flare_children)
    flare['children'].reverse()
    flare['children'].insert(0, {'name': 'Impact_Apis', 'children': api_list})
    return flare


def _clean_occupy(occupy_path):
    if os.path.exists(occupy_path):
        os.remove(occupy_path)


def _class_in_method(class_name, method_content):
    if class_name + ' ' in method_content \
            or '<' + class_name + '>' in method_content \
            or class_name + '.' in method_content:
        return True
    else:
        return False


def _diff_result_impact(diff_result_item_index, diff_results_list, which_java_file_analyze_result, mode):
    diff_result_item = diff_results_list[diff_result_item_index]
    diff_result_filepath = diff_result_item.filepath
    if diff_result_filepath in which_java_file_analyze_result.keys():
        which_java_analyze = which_java_file_analyze_result[diff_result_filepath]
        which_class_name = which_java_analyze.class_name
        which_class_path = which_java_analyze.package_name + '.' + which_java_analyze.class_name
        which_implements = which_java_analyze.implements
        head_extends = which_java_analyze.extends
        which_implements.append(which_class_path)
        for which_java_file_analyze_key in which_java_file_analyze_result.keys():
            which_java_file_analyze = which_java_file_analyze_result[which_java_file_analyze_key]
            if which_java_file_analyze.extends is not None:
                which_java_file_analyze_extends = which_java_file_analyze.extends
                if '.' in which_java_file_analyze_extends:
                    which_java_file_analyze_extends = '/'.join(which_java_file_analyze_extends.split('.'))
                extends_analyzer_list = [which_java_file_analyze_result[obj] for obj in
                                         which_java_file_analyze_result.keys()
                                         if which_java_file_analyze_extends in obj]
                if len(extends_analyzer_list) > 0:
                    extends_analyzer = extends_analyzer_list[0]
                    which_java_file_analyze.methods = list(
                        set(which_java_file_analyze.methods + extends_analyzer.methods))
                    which_java_file_analyze.declarators = list(
                        set(which_java_file_analyze.declarators + extends_analyzer.declarators))
                    which_java_file_analyze.imports.imports = list(
                        set(which_java_file_analyze.imports.imports + extends_analyzer.imports.imports))
            is_in, directly = _in_import(which_java_analyze, which_java_file_analyze)
            if not is_in:
                continue
            which_java_file_methods = which_java_file_analyze.methods
            which_java_file_declarators = [declarator for declarator in which_java_file_analyze.declarators if
                                           declarator.type == which_class_name]
            for which_java_file_method in which_java_file_methods:
                classname_in_method = False
                tmp = []
                if diff_result_item.changed_declarators != {}:
                    classname_in_method = _class_in_method(which_class_name, str(which_java_file_method.content))
                if which_java_file_method.contains_class is not None:
                    for implement in which_implements:
                        if implement in which_java_file_method.contains_class.keys() and 'methods' in \
                                which_java_file_method.contains_class[implement].keys():
                            java_file_method_includes_methods = which_java_file_method.contains_class[implement][
                                'methods']
                            tmp = [j for j in diff_result_item.changed_methods.keys() if
                                   mode in diff_result_item.changed_methods[j][
                                       'diff_impact'] and j in java_file_method_includes_methods]
                if len(tmp) == 0:
                    method_content_str = str(which_java_file_method.content)
                    if len(which_java_file_declarators) > 0:
                        for declarator in which_java_file_declarators:
                            tmp += [j for j in diff_result_item.changed_methods.keys() if
                                    mode in diff_result_item.changed_methods[j]['diff_impact']
                                    and ('(' + j + '(' in method_content_str
                                         or '=' + j + '(' in method_content_str
                                         or '=' + j + '(' in method_content_str
                                         or '= ' + j + '(' in method_content_str
                                         or declarator.name + '.' + j + '(' in method_content_str
                                         )
                                    ]
                    else:
                        tmp += [j for j in diff_result_item.changed_methods.keys() if
                                mode in diff_result_item.changed_methods[j]['diff_impact']
                                and ('(' + j + '(' in method_content_str
                                     or '=' + j + '(' in method_content_str
                                     or '=' + j + '(' in method_content_str
                                     or '= ' + j + '(' in method_content_str
                                     )
                                ]
                if len(tmp) > 0 or classname_in_method:
                    if which_java_file_method.diff_impact is None or which_java_file_method.diff_impact != '':
                        which_java_file_method.diff_impact = mode
                    else:
                        which_java_file_method.diff_impact = which_java_file_method.diff_impact + '_' + mode
                    java_file_class_path = which_java_file_analyze.package_name + '.' + which_java_file_analyze.class_name
                    if java_file_class_path not in diff_result_item.impact.keys():
                        diff_result_item.impact[java_file_class_path] = {'methods': [which_java_file_method.__dict__]}
                    elif which_java_file_method.__dict__ not in diff_result_item.impact[java_file_class_path][
                        'methods']:
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


# Press the green button in the gutter to run the script.
def analyze(project_git_url, branch_name, commit_first, commit_second, request_user):
    t1 = datetime.datetime.now()
    print(datetime.datetime.now(), ':', 'Start At:', datetime.datetime.now(), flush=True)
    cur_dir = os.getcwd()
    project_name = project_git_url.split("/")[-1].split('.git')[0]
    folder_name = cur_dir + sep + project_name
    git_clone_bash = 'git clone -b ' + branch_name + ' ' + project_git_url + ' ' + folder_name
    git_pull_base = 'cd ' + folder_name + ' && git checkout ' + branch_name + ' && git pull'
    diff_base = 'cd ' + folder_name + ' && ' \
                + 'git diff ' + commit_second + '..' + commit_first + ' > diff_' + commit_second + '..' + commit_first + '.txt'
    atexit.register(_clean_occupy, folder_name + sep + 'Occupy.ing')
    if not os.path.exists(folder_name):
        print(datetime.datetime.now(), ':', 'Clone from git', flush=True)
        os.system(git_clone_bash)
    else:
        # had analyze result, skip
        if os.path.exists(folder_name + sep + commit_second + '..' + commit_first + '.cci'):
            print(datetime.datetime.now(), ':', 'Has analyze result, skip!', flush=True)
            with open(folder_name + sep + commit_second + '..' + commit_first + '.cci', 'r') as read:
                print(datetime.datetime.now(), ':', read.read(), flush=True)
            sys.exit(0)
        else:
            # analyzing, wait
            wait_index = 0
            while os.path.exists(folder_name + sep + 'Occupy.ing') and wait_index < 30:
                print(datetime.datetime.now(), ':', 'Analyzing by others, waiting......', flush=True)
                time.sleep(3)
                wait_index += 1
    print(datetime.datetime.now(), ':', 'Start occupying project, and others can not analyze until released',
          flush=True)
    with open(folder_name + sep + 'Occupy.ing', 'w') as ow:
        ow.write('Occupy by ' + request_user)
    time.sleep(1)
    print(datetime.datetime.now(), ':', 'Git pull project to HEAD', flush=True)
    os.system(git_pull_base)
    time.sleep(1)
    print(datetime.datetime.now(), ':', 'Git diff between ' + commit_second + ' and ' + commit_first, flush=True)
    os.system(diff_base)
    time.sleep(1)
    print(datetime.datetime.now(), ':', 'Get all ' + commit_second + ' files', flush=True)
    base_java_file_analyze_result = _get_commit_project_files(commit_second, folder_name)
    print(datetime.datetime.now(), ':', 'Get all ' + commit_first + ' files', flush=True)
    head_java_file_analyze_result = _get_commit_project_files(commit_first, folder_name)
    diff_txt = folder_name + sep + 'diff_' + commit_second + '..' + commit_first + '.txt'
    print(datetime.datetime.now(), ':', 'Get all diff file', flush=True)
    diff_results = _get_diff_results(diff_txt, head_java_file_analyze_result, base_java_file_analyze_result)
    diff_result_index = 0
    for diff_result in diff_results:
        if diff_result is None:
            continue
        print(datetime.datetime.now(), ':', 'Analyzing diff/impact file:' + diff_result.filepath, flush=True)
        _diff_result_impact(diff_result_index, diff_results, head_java_file_analyze_result, 'ADD')
        _diff_result_impact(diff_result_index, diff_results, base_java_file_analyze_result, 'DEL')
        diff_result_index = diff_result_index + 1
    print(datetime.datetime.now(), ':', 'Analyze success, generating......', flush=True)
    flare = _gen_treemap_data(diff_results, commit_first, commit_second)
    print(json.dumps(flare), flush=True)
    with open(folder_name + sep + flare['name'] + '.cci', 'w') as w:
        w.write(json.dumps(flare))
    t2 = datetime.datetime.now()
    try:
        print(datetime.datetime.now(), ':', 'Analyze done, remove occupy, others can analyze now', flush=True)
        os.remove(folder_name + sep + 'Occupy.ing')
    except:
        pass
    print(datetime.datetime.now(), ':', 'Analyze done, spend: ', t2 - t1, flush=True)
