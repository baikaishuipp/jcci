import os
import logging
import json
import javalang
from .database import SqliteHelper
from .constant import ENTITY, RETURN_TYPE, PARAMETERS, BODY, METHODS, FIELDS, PARAMETER_TYPE_METHOD_INVOCATION_UNKNOWN, JAVA_BASIC_TYPE

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)

class JavaParse(object):
    def __init__(self, db_path, project_id):
        self.project_id = project_id
        self.sqlite = SqliteHelper(db_path)

    def _handle_extends(self, extends, import_list: list, package_name):
        if isinstance(extends, list):
            extends_package_class_list = []
            extends_class = extends[0].name
            extends_package_class = self._get_extends_class_full_package(extends_class, import_list, package_name)
            extends_package_class_list.append(extends_package_class)
            if 'arguments' in extends[0].attrs and extends[0].arguments:
                extends_arguments = extends[0].arguments
                extends_argument_classes = []
                for extends_argument in extends_arguments:
                    if type(extends_argument) == javalang.tree.TypeArgument:
                        extends_argument_class = extends_argument.type.name
                    else:
                        extends_argument_class = extends_argument.name
                    extends_argument_package_class = self._get_extends_class_full_package(extends_argument_class, import_list, package_name)
                    extends_argument_classes.append(extends_argument_package_class)
                extends_package_class_list += extends_argument_classes
                return extends_package_class + '<' + ','.join(extends_argument_classes) + '>', extends_package_class_list
            else:
                return extends_package_class, [extends_package_class]
        else:
            extends_class = self._get_extends_class_full_package(extends.name, import_list, package_name)
            return extends_class, [extends_class]

    def _get_extends_class_full_package(self, extends_class, import_list, package_name):
        extends_in_imports = [import_obj for import_obj in import_list if extends_class in import_obj['import_path']]
        return extends_in_imports[0]['import_path'] if extends_in_imports else package_name + '.' + extends_class

    def _parse_class(self, node, filepath: str, package_name: str, import_list: list, commit_or_branch: str):
        # 处理class信息
        documentation = node.documentation
        class_name = node.name
        package_class = package_name + '.' + node.name
        class_type = type(node).__name__.replace('Declaration', '')
        access_modifier = [m for m in list(node.modifiers) if m.startswith('p')][0] if list([m for m in list(node.modifiers) if m.startswith('p')]) else 'public'
        annotations_json = json.dumps(node.annotations, default=lambda obj: obj.__dict__)
        is_controller, controller_base_url = self._judge_is_controller(node.annotations)
        extends_package_class = None
        if 'extends' in node.attrs and node.extends:
            extends_package_class, extends_package_class_list = self._handle_extends(node.extends, import_list, package_name)
            package_path = package_class.replace('.', '/') + '.java'
            base_filepath = filepath.replace(package_path, '')
            for extends_package_class_item in extends_package_class_list:
                extends_package = '.'.join(extends_package_class_item.split('.')[0: -1])
                extends_class_name = extends_package_class_item.split('.')[-1]
                extends_class_filepath = base_filepath + extends_package_class_item.replace('.', '/') + '.java'
                extends_class_db = self.sqlite.select_data(f'SELECT * FROM class WHERE project_id={self.project_id} and package_name = "{extends_package}" and class_name = "{extends_class_name}" and filepath= "{extends_class_filepath}"')
                # if not extends_class_db:
                # self.parse_java_file(extends_class_filepath, commit_or_branch)
        implements = ','.join([implement.name for implement in node.implements]) if 'implements' in node.attrs and node.implements else None
        class_id, new_add = self.sqlite.add_class(filepath.replace('\\', '/'), access_modifier, class_type, class_name, package_name, extends_package_class, self.project_id, implements, annotations_json, documentation, is_controller, controller_base_url, commit_or_branch)
        return class_id, new_add

    def _parse_imports(self, imports):
        import_list = []
        for import_decl in imports:
            import_obj = {
                'import_path': import_decl.path,
                'is_static': import_decl.static,
                'is_wildcard': import_decl.wildcard,
                'start_line': import_decl.position.line,
                'end_line': import_decl.position.line
            }
            import_list.append(import_obj)
        return import_list

    def _parse_fields(self, fields, package_name, class_id, import_map):
        field_list = []
        for field_obj in fields:
            field_annotations = json.dumps(field_obj.annotations, default=lambda obj: obj.__dict__)
            access_modifier = [m for m in list(field_obj.modifiers) if m.startswith('p')][0] if list([m for m in list(field_obj.modifiers) if m.startswith('p')]) else 'public'
            field_name = field_obj.declarators[0].name
            field_type: str = field_obj.type.name
            if field_type.lower() not in JAVA_BASIC_TYPE:
                if field_type in import_map.keys():
                    field_type = import_map.get(field_type)
                else:
                    import_map[field_obj.type.name] = package_name + '.' + field_obj.type.name
                    field_type = package_name + '.' + field_type
            is_static = 'static' in list(field_obj.modifiers)
            documentation = field_obj.documentation
            start_line = field_obj.position.line if not field_obj.annotations else field_obj.annotations[0].position.line
            end_line = field_obj.position.line
            field_obj = {
                'class_id': class_id,
                'project_id': self.project_id,
                'annotations': field_annotations,
                'access_modifier': access_modifier,
                'field_type': field_type,
                'field_name': field_name,
                'is_static': is_static,
                'documentation': documentation,
                'start_line': start_line,
                'end_line': end_line
            }
            field_list.append(field_obj)
        self.sqlite.update_data(f'DELETE FROM field where class_id={class_id}')
        self.sqlite.insert_data('field', field_list)
        return field_list

    def _parse_method(self, methods, lines, class_id, import_map, field_map, package_name, filepath):
        # 处理 methods
        all_method = []
        class_db = self.sqlite.select_data(f'SELECT * FROM class WHERE class_id = {class_id}')[0]
        base_url = class_db['controller_base_url'] if class_db['controller_base_url'] else ''
        method_name_entity_map = {method.name: method for method in methods}
        for method_obj in methods:
            method_invocation = {}
            variable_map = {}
            method_name = method_obj.name
            documentation = method_obj.documentation  # document
            annotations = json.dumps(method_obj.annotations, default=lambda obj: obj.__dict__)  # annotations
            is_api, api_path = self._judge_is_api(method_obj.annotations, base_url, method_name)
            access_modifier = [m for m in list(method_obj.modifiers) if m.startswith('p')][0] if list([m for m in list(method_obj.modifiers) if m.startswith('p')]) else 'public'
            is_static = 'static' in list(method_obj.modifiers)
            is_abstract = 'abstract' in list(method_obj.modifiers)
            # 处理返回对象
            return_type = self._deal_declarator_type(method_obj.return_type, import_map, method_invocation, RETURN_TYPE, package_name, filepath)
            method_start_line = method_obj.position.line
            if method_obj.annotations:
                method_start_line = method_obj.annotations[0].position.line
            method_end_line = self._get_method_end_line(method_obj)
            method_body = lines[method_start_line - 1: method_end_line + 1]
            # 处理参数
            parameters = []
            for parameter in method_obj.parameters:
                parameter_obj = {
                    'parameter_type': self._deal_declarator_type(parameter.type, import_map, method_invocation, PARAMETERS, package_name, filepath),
                    'parameter_name': parameter.name,
                    'parameter_varargs': parameter.varargs
                }
                parameters.append(parameter_obj)
            parameters_map = {parameter['parameter_name']: parameter['parameter_type'] for parameter in parameters}

            # 处理方法体
            if method_obj.body:
                for body in method_obj.body:
                    for path, node in body.filter(javalang.tree.VariableDeclaration):
                        var_declarator = node.declarators[0].name
                        var_declarator_type = self._deal_declarator_type(node.type, import_map, method_invocation, BODY, package_name, filepath)
                        variable_map[var_declarator] = var_declarator_type
                    for path, node in body.filter(javalang.tree.MethodInvocation):
                        qualifier = node.qualifier
                        member = node.member
                        # 类静态方法调用
                        if not qualifier and not member[0].islower():
                            qualifier_type = self._get_var_type(member, parameters_map, variable_map, field_map, import_map, method_invocation, BODY, package_name, filepath)
                            # todo a.b.c
                            if node.selectors is None:
                                continue
                            for selector in node.selectors:
                                selector_member = selector.member
                                selector_arguments = self._deal_var_type(selector.arguments, parameters_map, variable_map, field_map, import_map, method_invocation, BODY, package_name, filepath)
                                selector_line = selector.position.line
                                selector_method = f'{selector_member}({",".join(selector_arguments)})'
                                self._add_method_used_to_method_invocation(method_invocation, qualifier_type, selector_method, [selector_line])
                        elif qualifier:
                            qualifier_type = self._get_var_type(qualifier, parameters_map, variable_map, field_map, import_map, method_invocation, BODY, package_name, filepath)
                            node_arguments = self._deal_var_type(node.arguments, parameters_map, variable_map, field_map, import_map, method_invocation, BODY, package_name, filepath)
                            node_line = node.position.line
                            node_method = f'{member}({",".join(node_arguments)})'
                            self._add_method_used_to_method_invocation(method_invocation, qualifier_type, node_method, [node_line])
                        # 在一个类的方法或父类方法
                        elif member:
                            class_db = self.sqlite.select_data(f'SELECT * FROM class where class_id={class_id} limit 1')[0]
                            package_class = class_db['package_name'] + '.' + class_db['class_name']
                            node_line = node.position.line
                            node_arguments = self._deal_var_type(node.arguments, parameters_map, variable_map, field_map, import_map, method_invocation, BODY, package_name, filepath)
                            # todo 同级方法, 判断参数长度，不精确
                            if method_name_entity_map.get(member):
                                same_class_method = None
                                max_score = -float('inf')
                                for method_item in methods:
                                    if method_item.name != member or len(node.arguments) != len(method_item.parameters):
                                        continue
                                    method_item_param_types = [self._deal_declarator_type(parameter.type, import_map, method_invocation, PARAMETERS, package_name, filepath) for parameter in method_item.parameters]
                                    score = self._calculate_similar_score_method_params(node_arguments, method_item_param_types)
                                    if score > max_score:
                                        max_score = score
                                        same_class_method = method_item
                                if same_class_method:
                                    node_arguments = self._deal_var_type(same_class_method.parameters, parameters_map, variable_map, field_map, import_map, method_invocation, BODY, package_name, filepath)
                                    node_method = f'{member}({",".join(node_arguments)})'
                                    self._add_method_used_to_method_invocation(method_invocation, package_class, node_method, [node_line])
                            # todo 继承方法
                            elif class_db['extends_class']:
                                extends_package_class, method_params = self._find_method_in_extends(class_db['extends_class'], member, node_arguments)
                                if not extends_package_class:
                                    self._add_method_used_to_method_invocation(method_invocation, extends_package_class, method_params, [node_line])

                    # for path, node in body.filter(javalang.tree.SuperMethodInvocation):
                    #     print(node)
                    # for path, node in body.filter(javalang.tree.TypeArgument):
                    #     print(node)
                    # for path, node in body.filter(javalang.tree.TypeParameter):
                    #     print(node)
                    # for path, node in body.filter(javalang.tree.FieldDeclaration):
                    #     print(node)
            method_db = {
                'class_id': class_id,
                'project_id': self.project_id,
                'annotations': annotations,
                'access_modifier': access_modifier,
                'return_type': return_type,
                'method_name': method_name,
                'parameters': json.dumps(parameters),
                'body': json.dumps(method_body),
                'method_invocation_map': json.dumps(method_invocation),
                'is_static': is_static,
                'is_abstract': is_abstract,
                'is_api': is_api,
                'api_path': json.dumps(api_path) if is_api else None,
                'start_line': method_start_line,
                'end_line': method_end_line,
                'documentation': documentation
            }
            all_method.append(method_db)
        self.sqlite.update_data(f'DELETE FROM methods where class_id={class_id}')
        self.sqlite.insert_data('methods', all_method)

    def _find_method_in_extends(self, extend_package_class: str, method_name: str, method_arguments):
        if not extend_package_class:
            return None, None
        # 查表有没有记录
        extend_package = '.'.join(extend_package_class.split('.')[0: -1])
        extend_class = extend_package_class.split('.')[-1]
        extend_class_db = self.sqlite.select_data(f'SELECT * FROM class WHERE package_name="{extend_package}" '
                                                  f'AND class_name="{extend_class}" '
                                                  f'AND project_id={self.project_id} limit 1')

        if not extend_class_db:
            return None, None
        extend_class_entity = extend_class_db[0]
        extend_class_id = extend_class_entity['class_id']
        methods_db_list = self.sqlite.select_data(f'SELECT * FROM methods WHERE class_id={extend_class_id} and method_name = "{method_name}"')
        if not methods_db_list and not extend_class_entity['extends_class']:
            return None, None
        if not methods_db_list:
            return self._find_method_in_extends(extend_class_entity['extends_class'], method_name, method_arguments)
        else:
            filter_methods = [method for method in methods_db_list if len(json.loads(method['parameters'])) == len(method_arguments)]
            if not filter_methods:
                return self._find_method_in_extends(extend_class_entity['extends_class'], method_name, method_arguments)
            package_class = extend_class_entity['package_name'] + '.' + extend_class_entity['class_name']
            if len(filter_methods) == 1:
                method_db = filter_methods[0]
                method_params = f'{method_db["method_name"]}({",".join([param["parameter_type"] for param in json.loads(method_db["parameters"])])})'
                return package_class, method_params
            else:
                max_score = -float('inf')
                max_score_method = None
                for method_db in filter_methods:
                    method_db_params = [param["parameter_type"] for param in json.loads(method_db["parameters"])]
                    score = self._calculate_similar_score_method_params(method_arguments, method_db_params)
                    if score > max_score:
                        max_score = score
                        max_score_method = method_db
                if max_score_method is None:
                    max_score_method = filter_methods[0]
                method_params = f'{max_score_method["method_name"]}({",".join([param["parameter_type"] for param in json.loads(max_score_method["parameters"])])})'
                return package_class, method_params

    def _calculate_similar_score_method_params(self, except_method_param_list, method_param_list):
        score = 0
        positions = {}

        # 记录list1中每个元素的位置
        for i, item in enumerate(except_method_param_list):
            positions[item] = i

        # 遍历list2,计算分数
        for i, item in enumerate(method_param_list):
            if item in positions:
                score += 1
                score -= abs(i - positions[item])

        return score

    def _get_method_end_line(self, method_obj):
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

    def _get_element_value(self, method_element):
        method_api_path = []
        if type(method_element).__name__ == 'BinaryOperation':
            operandl = method_element.operandl
            operandr = method_element.operandr
            operandl_str = self._get_api_part_route(operandl)
            operandr_str = self._get_api_part_route(operandr)
            method_api_path = [operandl_str + operandr_str]
        elif type(method_element).__name__ == 'MemberReference':
            method_api_path = [method_element.member.replace('"', '')]
        elif type(method_element).__name__ == 'ElementArrayValue':
            method_api_path = self._get_element_with_values(method_element)
        elif method_element.value is not None:
            method_api_path = [method_element.value.replace('"', '')]
        return method_api_path

    def _get_element_with_values(self, method_api_path_obj):
        result = []
        for method_api_value in method_api_path_obj.values:
            result += self._get_element_value(method_api_value)
        return result

    def _get_api_part_route(self, part):
        part_class = type(part).__name__
        if part_class == 'MemberReference':
            return part.member.replace('"', '')
        elif part_class == 'Literal':
            return part.value.replace('"', '')

    def _judge_is_controller(self, annotation_list):
        is_controller = any('Controller' in annotation.name for annotation in annotation_list)
        base_request = ''
        if not is_controller:
            return is_controller, base_request
        for annotation in annotation_list:
            if 'RequestMapping' != annotation.name:
                continue
            if annotation.element is None:
                continue
            if isinstance(annotation.element, list):
                base_request_list = []
                for annotation_element in annotation.element:
                    if annotation_element.name != 'value' and annotation_element.name != 'path':
                        continue
                    if 'values' in annotation_element.value.attrs:
                        base_request_list += self._get_element_with_values(annotation_element.value)
                    else:
                        base_request_list += self._get_element_value(annotation_element.value)
                if len(base_request_list) > 0:
                    base_request = base_request_list[0]
            else:
                if 'value' in annotation.element.attrs:
                    base_request = annotation.element.value.replace('"', '')
                elif 'values' in annotation.element.attrs:
                    base_request = ' || '.join([literal.value for literal in annotation.element.values])
        if is_controller and not base_request.endswith('/'):
            base_request += '/'
        return is_controller, base_request

    def _judge_is_api(self, method_annotations, base_request, method_name):
        api_path_list = []
        req_method_list = []
        method_api_path = []
        is_api = False
        for method_annotation in method_annotations:
            if 'Mapping' not in method_annotation.name:
                continue
            is_api = True
            if method_annotation.name != 'RequestMapping':
                req_method_list.append(method_annotation.name.replace('Mapping', ''))
            else:
                if not method_annotation.element:
                    continue
                for method_annotation_element in method_annotation.element:
                    if type(method_annotation_element) == tuple:
                        req_method_list = ['ALL']
                        break
                    if 'name' not in method_annotation_element.attrs or method_annotation_element.name != 'method':
                        continue
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
                method_api_path += self._get_element_value(method_annotation.element)
            else:
                method_api_path_list = [method_annotation_element.value for method_annotation_element in method_annotation.element
                                        if method_annotation_element.name == 'path' or method_annotation_element.name == 'value']
                if len(method_api_path_list) == 0:
                    continue
                method_api_path_obj = method_api_path_list[0]
                if 'value' in method_api_path_obj.attrs:
                    method_api_path += [method_api_path_obj.value.replace('"', '')]
                else:
                    if 'values' in method_api_path_obj.attrs:
                        for method_api_value in method_api_path_obj.values:
                            method_api_path += self._get_element_value(method_api_value)
                    else:
                        method_api_path += [method_name + '/cci-unknown']
        if len(method_api_path) == 0:
            method_api_path = ['/']
        for method_api_path_obj in method_api_path:
            if method_api_path_obj.startswith('/'):
                method_api_path_obj = method_api_path_obj[1:]
            api_path = base_request + method_api_path_obj
            if not api_path:
                continue
            if api_path.endswith('/'):
                api_path = api_path[0:-1]
            if len(req_method_list) > 0:
                api_path_list += ['[' + req_method_temp + ']' + api_path for req_method_temp in req_method_list]
            else:
                api_path_list.append('[ALL]' + api_path)
        return is_api, api_path_list

    def _add_entity_used_to_method_invocation(self, method_invocation, package_class, section):
        if package_class not in method_invocation.keys():
            method_invocation[package_class] = {ENTITY: {section: True}}
        elif ENTITY not in method_invocation[package_class].keys():
            method_invocation[package_class][ENTITY] = {section: True}
        elif section not in method_invocation[package_class][ENTITY].keys():
            method_invocation[package_class][ENTITY][section] = True

    def _add_method_used_to_method_invocation(self, method_invocation, package_class, method, lines):
        if package_class not in method_invocation.keys():
            method_invocation[package_class] = {METHODS: {method: lines}}
        elif METHODS not in method_invocation[package_class].keys():
            method_invocation[package_class][METHODS] = {method: lines}
        elif method not in method_invocation[package_class][METHODS].keys():
            method_invocation[package_class][METHODS][method] = lines
        else:
            method_invocation[package_class][METHODS][method] += lines

    def _add_field_used_to_method_invocation(self, method_invocation, package_class, field, lines):
        if package_class not in method_invocation.keys():
            method_invocation[package_class] = {FIELDS: {field: lines}}
        elif FIELDS not in method_invocation[package_class].keys():
            method_invocation[package_class][FIELDS] = {field: lines}
        elif field not in method_invocation[package_class][FIELDS].keys():
            method_invocation[package_class][FIELDS][field] = lines
        else:
            method_invocation[package_class][FIELDS][field] += lines

    def _deal_declarator_type(self, node_type, import_map, method_invocation, section, package_name, filepath):
        if node_type is None:
            return node_type
        if type(node_type) == javalang.tree.BasicType:
            return node_type.name
        var_declarator_type = node_type.name
        if var_declarator_type in import_map.keys():
            var_declarator_type = import_map.get(var_declarator_type)
            self._add_entity_used_to_method_invocation(method_invocation, var_declarator_type, section)
        else:
            node_path = "/".join(filepath.split("/")[0: -1]) + "/" + var_declarator_type + ".java"
            if os.path.exists(node_path):
                var_declarator_type = f'{package_name}.{var_declarator_type}'
        var_declarator_type_arguments = self._deal_arguments_type(node_type.arguments, import_map, method_invocation, section)
        if var_declarator_type_arguments:
            var_declarator_type = var_declarator_type + '<' + '#'.join(var_declarator_type_arguments) + '>'
        return var_declarator_type

    def _deal_arguments_type(self, arguments, import_map, method_invocation, section):
        var_declarator_type_arguments_new = []
        if not arguments:
            return var_declarator_type_arguments_new
        var_declarator_type_arguments = []
        for argument in arguments:
            if type(argument) == javalang.tree.MethodInvocation:
                var_declarator_type_arguments.append(PARAMETER_TYPE_METHOD_INVOCATION_UNKNOWN)
                continue
            var_declarator_type_argument = self._deal_type(argument)
            if var_declarator_type_argument in import_map.keys():
                var_declarator_type_argument = import_map.get(var_declarator_type_argument)
                self._add_entity_used_to_method_invocation(method_invocation, var_declarator_type_argument, section)
            var_declarator_type_arguments.append(var_declarator_type_argument)
        return var_declarator_type_arguments

    def _deal_type(self, argument):
        if not argument:
            return None
        argument_type = type(argument)
        if argument_type == javalang.tree.MemberReference:
            var_declarator_type_argument = argument.member
        elif argument_type == javalang.tree.ClassCreator:
            var_declarator_type_argument = argument.type.name
        elif argument_type == javalang.tree.Literal:
            var_declarator_type_argument = self._deal_literal_type(argument.value)
        elif argument_type == javalang.tree.This:
            var_declarator_type_argument = 'This'
        elif argument_type == javalang.tree.LambdaExpression:
            var_declarator_type_argument = 'LambdaExpression'
        elif argument_type == javalang.tree.BinaryOperation:
            # todo BinaryOperation temp set string
            var_declarator_type_argument = 'String'
        elif argument_type == javalang.tree.MethodReference or argument_type == javalang.tree.TernaryExpression:
            # todo MethodReference temp set unknown
            var_declarator_type_argument = PARAMETER_TYPE_METHOD_INVOCATION_UNKNOWN
        elif argument_type == javalang.tree.SuperMethodInvocation:
            logging.info(argument_type)
            var_declarator_type_argument = PARAMETER_TYPE_METHOD_INVOCATION_UNKNOWN
        elif argument_type == javalang.tree.Assignment:
            var_declarator_type_argument = self._deal_type(argument.value)
        elif argument_type == javalang.tree.Cast:
            var_declarator_type_argument = argument.type.name
        # todo
        elif argument_type == javalang.tree.SuperMemberReference:
            var_declarator_type_argument = 'String'
        elif 'type' in argument.attrs and argument.type is not None:
            var_declarator_type_argument = argument.type.name
        else:
            logging.info(f'argument type is None：{argument}')
            var_declarator_type_argument = PARAMETER_TYPE_METHOD_INVOCATION_UNKNOWN
        return var_declarator_type_argument

    def _deal_literal_type(self, text):
        if 'true' == text or 'false' == text:
            return 'boolean'
        if text.isdigit():
            return 'int'
        return 'String'

    def _deal_var_type(self, arguments, parameters_map, variable_map, field_map, import_map, method_invocation, section, package_name, filepath):
        var_declarator_type_arguments_new = []
        if not arguments:
            return var_declarator_type_arguments_new
        var_declarator_type_arguments = []
        for argument in arguments:
            argument_type = type(argument)
            if argument_type == javalang.tree.MethodInvocation:
                var_declarator_type_arguments.append(PARAMETER_TYPE_METHOD_INVOCATION_UNKNOWN)
                continue
            var_declarator_type_argument = self._deal_type(argument)
            var_declarator_type_argument = self._get_var_type(var_declarator_type_argument, parameters_map, variable_map, field_map, import_map, method_invocation, section, package_name, filepath)
            type_arguments = self._deal_arguments_type(argument.type.arguments, import_map, method_invocation, section) \
                if 'type' in argument.attrs \
                   and not isinstance(argument.type, str) \
                   and 'arguments' in argument.type.attrs \
                   and argument.type.arguments \
                else []
            if type_arguments:
                var_declarator_type_argument = var_declarator_type_argument + '<' + '#'.join(type_arguments) + '>'
            var_declarator_type_arguments.append(var_declarator_type_argument)
        return var_declarator_type_arguments

    def _get_var_type(self, var, parameters_map, variable_map, field_map, import_map, method_invocation, section, package_name, filepath):
        if not var:
            return var
        if var in parameters_map.keys():
            return parameters_map.get(var)
        if var in variable_map.keys():
            return variable_map.get(var)
        if var in field_map.keys():
            field_type = field_map.get(var)['field_type']
            package_class = field_map.get(var)['package_class']
            start_line = field_map.get(var)['start_line']
            self._add_field_used_to_method_invocation(method_invocation, package_class, var, [start_line])
            return field_type
        if var in import_map.keys():
            var_type = import_map.get(var)
            self._add_entity_used_to_method_invocation(method_invocation, var_type, section)
            return var_type
        else:
            var_path = "/".join(filepath.split("/")[0: -1]) + "/" + var + ".java"
            if os.path.exists(var_path):
                var_type = f'{package_name}.{var}'
                return var_type
        return PARAMETER_TYPE_METHOD_INVOCATION_UNKNOWN

    def _get_extends_class_fields_map(self, class_id: int):
        class_db = self.sqlite.select_data(f'SELECT * FROM class WHERE class_id = {class_id}')[0]
        extend_package_class = class_db['extends_class']
        if not extend_package_class:
            return {}
        extend_package = '.'.join(extend_package_class.split('.')[0: -1])
        extend_class = extend_package_class.split('.')[-1]
        extend_class_db = self.sqlite.select_data(f'SELECT * FROM class WHERE package_name="{extend_package}" '
                                                  f'AND class_name="{extend_class}" '
                                                  f'AND project_id={self.project_id} limit 1')
        if not extend_class_db:
            return {}
        extend_class_entity = extend_class_db[0]
        extend_class_id = extend_class_entity['class_id']
        extend_class_fields = self.sqlite.select_data(f'SELECT * FROM field WHERE class_id = {extend_class_id}')
        extend_class_fields_map = {field_obj['field_name']: {'field_type': field_obj['field_type'], 'package_class': extend_package_class, 'start_line': field_obj['start_line']} for field_obj in extend_class_fields}
        if not extend_class_entity['extends_class']:
            return extend_class_fields_map
        else:
            extend_new_map = self._get_extends_class_fields_map(extend_class_id)
            extend_new_map.update(extend_class_fields_map)
            return extend_new_map

    def parse_java_file(self, filepath: str, commit_or_branch: str):
        if not filepath.endswith('.java'):
            return
        try:
            with open(filepath, encoding='UTF-8') as fp:
                file_content = fp.read()
        except:
            return
        logging.info(f'Parsing java file: {filepath}')
        lines = file_content.split('\n')
        try:
            tree = javalang.parse.parse(file_content)
            if not tree.types:
                return
        except Exception as e:
            logging.error(f"Error parsing {filepath}: {e}")
            return
        # 处理包信息
        package_name = tree.package.name if tree.package else 'unknown'
        class_name = tree.types[0].name
        package_class = package_name + '.' + class_name
        # 处理 import 信息
        import_list = self._parse_imports(tree.imports)
        import_map = {import_obj['import_path'].split('.')[-1]: import_obj['import_path'] for import_obj in import_list}

        # 处理 class 信息
        class_id, new_add = self._parse_class(tree.types[0], filepath, package_name, import_list, commit_or_branch)
        # 已经处理过了，返回
        # if not new_add:
        #     return
        # 导入import
        imports = [dict(import_obj, class_id=class_id, project_id=self.project_id) for import_obj in import_list]
        self.sqlite.update_data(f'DELETE FROM import WHERE class_id={class_id}')
        self.sqlite.insert_data('import', imports)

        # 处理 field 信息
        field_list = self._parse_fields(tree.types[0].fields, package_name, class_id, import_map)
        field_map = {field_obj['field_name']: {'field_type': field_obj['field_type'], 'package_class': package_class, 'start_line': field_obj['start_line']} for field_obj in field_list}
        import_map = dict((k, v) for k, v in import_map.items() if v.startswith('com.') or v.startswith('cn.'))

        # 将extend class的field导进来
        extends_class_fields_map = self._get_extends_class_fields_map(class_id)
        extends_class_fields_map.update(field_map)
        # 处理 methods 信息
        self._parse_method(tree.types[0].methods, lines, class_id, import_map, extends_class_fields_map, package_name, filepath)

    def parse_java_file_list(self, filepath_list: list, commit_or_branch: str):
        for file_path in filepath_list:
            self.parse_java_file(file_path, commit_or_branch)


if __name__ == '__main__':
    print('jcci')
