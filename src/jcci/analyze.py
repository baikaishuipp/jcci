import json
import os
import sys
import time
import atexit
import logging
import datetime
import fnmatch
from . import config as config
from .database import SqliteHelper
from .java_parse import JavaParse
from . import mapper_parse as mapper_parse
from . import diff_parse as diff_parse
from . import graph as graph
from . import constant as constant

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)


class JCCI(object):
    def __init__(self, git_url, username):
        self.git_url = git_url
        self.username: str = username
        # self.git_token = git_token
        self.branch_name: str = ''
        self.commit_or_branch_new: str = ''
        self.commit_or_branch_old: str = ''
        self.project_id: int = -1
        self.cci_filepath: str = ''
        self.project_name: str = ''
        self.file_path: str = ''
        self.sqlite = SqliteHelper(config.db_path + '/' + username + '_jcci.db')
        self.view = graph.Graph()
        self.t1 = datetime.datetime.now()
        self.need_analyze_obj_list = []
        self.analyzed_obj_set = []
        self.diff_parse_map = {}
        self.xml_parse_results_new = {}
        self.xml_parse_results_old = {}

    # Step 1.1
    def _can_analyze(self, filepath, cci_file_path):
        # 已有分析结果
        if os.path.exists(cci_file_path):
            logging.info('Has analyze result, skip!')
            with open(cci_file_path, 'r') as read:
                result = read.read()
                result_json = json.loads(result)
                print(result, flush=True)
                print(f'Impacted api list: {result_json["impacted_api_list"]}', flush=True)
            sys.exit(0)

        # 正在分析
        wait_index = 0
        occupy_filepath = os.path.join(filepath, 'Occupy.ing')
        atexit.register(self._clean_occupy, occupy_filepath)
        while os.path.exists(occupy_filepath) and wait_index < 30:
            logging.info(f'Analyzing by others, waiting or clean occupying file manually at: {occupy_filepath} to continue')
            time.sleep(3)
            wait_index += 1
        if os.path.exists(occupy_filepath):
            logging.info(f'Analyzing by others, waiting timeout')
            sys.exit(0)

    # Step 1.2
    def _clean_occupy(self, occupy_path):
        if os.path.exists(occupy_path):
            os.remove(occupy_path)

    # Step 1.3
    def _occupy_project(self):
        # 占住项目分析
        logging.info('Start occupying project, and others can not analyze until released')
        occupy_filepath = os.path.join(self.file_path, 'Occupy.ing')
        with open(occupy_filepath, 'w') as ow:
            ow.write(f'Occupy by {self.username}')
        time.sleep(1)

    # Step 2
    def _get_diff_parse_map(self, filepath, branch, commit_first, commit_second):
        logging.info('Git pull project to HEAD')
        os.system(f'cd {filepath} && git checkout {branch} && git pull')
        time.sleep(1)
        logging.info(f'Git diff between {commit_first} and {commit_second}')
        diff_base = f'cd {self.file_path} && git diff {commit_second}..{commit_first} > diff_{commit_second}..{commit_first}.txt'
        os.system(diff_base)
        diff_txt = os.path.join(self.file_path, f'diff_{commit_second}..{commit_first}.txt')
        logging.info(f'Analyzing diff file, location: {diff_txt}')
        return diff_parse.get_diff_info(diff_txt)

    # Step 2
    def _get_branch_diff_parse_map(self, filepath, branch_first, branch_second):
        logging.info('Git pull project to HEAD')
        os.system(f'cd {filepath} && git fetch --all && git checkout -b {branch_second} origin/{branch_second} && git checkout {branch_second} && git pull')
        time.sleep(1)
        os.system(f'cd {filepath} && git fetch --all && git checkout -b {branch_first} origin/{branch_first} && git checkout {branch_first} && git pull')
        time.sleep(1)
        logging.info(f'Git diff between {branch_first} and {branch_second}')
        diff_base = f'cd {self.file_path} && git diff {branch_second}..{branch_first} > diff_{branch_second.replace("/", "#")}..{branch_first.replace("/", "#")}.txt'
        os.system(diff_base)
        diff_txt = os.path.join(self.file_path, f'diff_{branch_second.replace("/", "#")}..{branch_first.replace("/", "#")}.txt')
        logging.info(f'Analyzing diff file, location: {diff_txt}')
        return diff_parse.get_diff_info(diff_txt)

    # Step 3
    def _parse_project(self, project_dir, new_commit_or_branch, old_commit_or_branch):
        # 解析最新的项目文件
        os.system(f'cd {project_dir} && git reset --hard {new_commit_or_branch}')
        time.sleep(2)
        file_path_list = self._get_project_files(project_dir)
        diff_xml_file_path = [key for key in file_path_list if key.endswith('.xml') and any(key.endswith(diff_path) for diff_path in self.diff_parse_map.keys())]
        java_parse = JavaParse(self.sqlite.db_path, self.project_id)
        java_parse.parse_java_file_list(file_path_list, new_commit_or_branch)
        xml_parse_result_new = self._parse_xml_file(diff_xml_file_path)
        xml_parse_result_old = {}
        if not old_commit_or_branch:
            return xml_parse_result_new, xml_parse_result_old
        # 解析旧版本有差异的文件
        os.system(f'cd {project_dir} && git reset --hard {old_commit_or_branch}')
        time.sleep(2)
        xml_parse_result_old = self._parse_xml_file(diff_xml_file_path)
        for key in self.diff_parse_map.keys():
            matched_file_path_list = [filepath for filepath in file_path_list if filepath.endswith(key)]
            if not matched_file_path_list:
                continue
            matched_file_path = matched_file_path_list[0]
            java_parse.parse_java_file(matched_file_path, old_commit_or_branch)
        return xml_parse_result_new, xml_parse_result_old

    # Step 3
    def _parse_branch_project(self, project_dir, new_branch, old_branch):
        # 解析最新的项目文件
        os.system(f'cd {project_dir} && git checkout {new_branch}')
        time.sleep(2)
        file_path_list = self._get_project_files(project_dir)
        diff_xml_file_path = [key for key in file_path_list if key.endswith('.xml') and any(key.endswith(diff_path) for diff_path in self.diff_parse_map.keys())]
        java_parse = JavaParse(self.sqlite.db_path, self.project_id)
        java_parse.parse_java_file_list(file_path_list, new_branch)
        xml_parse_result_new = self._parse_xml_file(diff_xml_file_path)
        # 解析旧版本有差异的文件
        os.system(f'cd {project_dir} && git checkout {old_branch}')
        time.sleep(2)
        xml_parse_result_old = self._parse_xml_file(diff_xml_file_path)
        for key in self.diff_parse_map.keys():
            matched_file_path_list = [filepath for filepath in file_path_list if filepath.endswith(key)]
            if not matched_file_path_list:
                continue
            matched_file_path = matched_file_path_list[0]
            java_parse.parse_java_file(matched_file_path, old_branch)
        return xml_parse_result_new, xml_parse_result_old

    # Step 3.1 get all java files
    def _get_project_files(self, project_dir):
        file_lists = []
        for root, dirs, files in os.walk(project_dir):
            if '.git' in root or os.path.join('src', 'test') in root:
                continue
            for file in files:
                ignore = False
                filepath = os.path.join(root, file)
                for pattern in config.ignore_file:
                    if fnmatch.fnmatch(filepath, pattern):
                        ignore = True
                        break
                if ignore:
                    continue
                file_lists.append(filepath.replace('\\', '/'))
        return file_lists

    # Step 3.3
    def _parse_xml_file(self, file_path_list):
        xml_parse_results = {}
        for filepath in file_path_list:
            if filepath.endswith('.xml'):
                xml_parse_result = mapper_parse.parse(filepath)
                if xml_parse_result:
                    xml_parse_results[filepath] = xml_parse_result
        return xml_parse_results

    # Step 4
    def _diff_analyze(self, patch_filepath: str, diff_parse_obj: dict):
        is_xml_file = patch_filepath.endswith('.xml')
        if is_xml_file:
            self._xml_diff_analyze(patch_filepath, diff_parse_obj)
        else:
            self._java_diff_analyze(patch_filepath, diff_parse_obj)

    # Step 4.1
    def _xml_diff_analyze(self, patch_filepath, diff_parse_obj: dict):
        xml_file_path_list = [filepath for filepath in self.xml_parse_results_new.keys() if filepath.endswith(patch_filepath)]
        if not xml_file_path_list:
            return
        xml_file_path = xml_file_path_list[0]
        xml_name = xml_file_path.split('/')[-1]
        xml_parse_result_new: mapper_parse.Mapper = self.xml_parse_results_new.get(xml_file_path)
        methods = xml_parse_result_new.result_maps + xml_parse_result_new.sqls + xml_parse_result_new.statements
        self._xml_method_diff_analyze(methods, diff_parse_obj['line_num_added'], diff_parse_obj['line_content_added'], xml_parse_result_new, xml_name, xml_file_path, self.commit_or_branch_new)
        xml_parse_result_old = self.xml_parse_results_old.get(xml_file_path)
        methods = xml_parse_result_old.result_maps + xml_parse_result_old.sqls + xml_parse_result_old.statements
        self._xml_method_diff_analyze(methods, diff_parse_obj['line_num_removed'], diff_parse_obj['line_content_removed'], xml_parse_result_old, xml_name, xml_file_path, self.commit_or_branch_old)

    # Step 4.1.1
    def _xml_method_diff_analyze(self, methods: list, line_num_list: list, line_content_list: list, xml_parse_result, xml_name, xml_file_path, commit_or_branch):
        namespace = xml_parse_result.namespace
        mapper_extend_dict = {
            'mapper_file_name': xml_name,
            'mapper_filepath': xml_file_path
        }
        for line_num in line_num_list:
            method_changed = [method for method in methods if self._is_line_num_in_xml_method_range(method, line_num)]
            method_changed_name = [method.name for method in method_changed]
            for method in method_changed:
                diff_content = line_content_list[line_num_list.index(line_num)]
                method_node_id = self.view.create_node_category(xml_name, method.name, method.type, constant.DIFF_TYPE_CHANGED, diff_content, xml_file_path, '', method.content, {})
                if method.type == constant.NODE_TYPE_MAPPER_STATEMENT:
                    mapper_extend_dict['method_node_id'] = method_node_id
                    self._add_to_need_analyze_obj_list('xml', namespace, None, method.name, commit_or_branch, mapper_extend_dict)
                    continue
                for statement in xml_parse_result.statements:
                    if statement.result_map in method_changed_name or statement.include_sql in method_changed_name:
                        statement_node_id = self.view.create_node_category(xml_name, statement.name, statement.type, constant.DIFF_TYPE_IMPACTED, '', xml_file_path, '', statement.content, {})
                        self.view.create_node_link(method_node_id, statement_node_id)
                        mapper_extend_dict['method_node_id'] = statement_node_id
                        self._add_to_need_analyze_obj_list('xml', namespace, None, statement.name, commit_or_branch, mapper_extend_dict)

    # Step 4.1.1.1
    def _is_line_num_in_xml_method_range(self, method, line_num):
        line_num_in_method = False
        if method.start <= line_num <= method.end:
            line_num_in_method = True
        return line_num_in_method

    # Step 4.2
    def _java_diff_analyze(self, patch_filepath: str, diff_parse_obj: dict):
        # new branch or commit
        class_db = self.sqlite.select_data(f'''SELECT * FROM class WHERE project_id = {self.project_id} and commit_or_branch = "{self.commit_or_branch_new}" and filepath LIKE "%{patch_filepath}"''')
        if class_db:
            class_db_obj = class_db[0]
            self._java_field_method_diff_analyze(class_db_obj, diff_parse_obj['line_num_added'], diff_parse_obj['line_content_added'], self.commit_or_branch_new)
        # old branch or commit
        if not self.commit_or_branch_old:
            return
        class_db = self.sqlite.select_data(f'SELECT * FROM class WHERE project_id = {self.project_id} and commit_or_branch = "{self.commit_or_branch_old}" and filepath LIKE "%{patch_filepath}"')
        if class_db:
            class_db_obj = class_db[0]
            self._java_field_method_diff_analyze(class_db_obj, diff_parse_obj['line_num_removed'], diff_parse_obj['line_content_removed'], self.commit_or_branch_old)

    # Step 4.2.1
    def _java_field_method_diff_analyze(self, class_db: dict, line_num_list: list, line_content_list: list, commit_or_branch: str or None):
        if not commit_or_branch:
            return
        class_name = class_db['class_name']
        class_filepath = class_db['filepath']
        is_controller = class_db['is_controller']
        data_in_annotation = [annotation for annotation in json.loads(class_db['annotations']) if annotation['name'] in ['Data', 'Getter', 'Setter', 'Builder', 'NoArgsConstructor', 'AllArgsConstructor']]
        for line_num in line_num_list:
            diff_content = line_content_list[line_num_list.index(line_num)]
            fields_list = self.sqlite.select_data(f'SELECT * FROM field WHERE class_id = {class_db["class_id"]} AND start_line <={line_num} AND end_line >= {line_num} order by start_line asc limit 1')
            methods_list = self.sqlite.select_data(f'SELECT * FROM methods WHERE class_id = {class_db["class_id"]} AND start_line <={line_num} AND end_line >= {line_num} order by start_line asc limit 1')
            if fields_list:
                is_not_static_fields = [field for field in fields_list if field.get('is_static') == 'False']
                if is_not_static_fields and data_in_annotation:
                    self._add_to_need_analyze_obj_list('java', f'{class_db["package_name"]}.{class_name}', None, None, commit_or_branch, class_db)
                elif is_not_static_fields and not data_in_annotation:
                    field_method_name = []
                    for field in is_not_static_fields:
                        field_name = field['field_name']
                        field_name_capitalize = field_name[0].upper() + field_name[1:]
                        field_method_name += ['get' + field_name_capitalize, 'set' + field_name_capitalize, 'is' + field_name_capitalize]
                    field_method_name_str = '"' + '","'.join(field_method_name) + '"'
                    field_method_db = self.sqlite.select_data(f'SELECT * FROM methods WHERE class_id = {class_db["class_id"]} AND method_name in ({field_method_name_str})')
                    if field_method_db:
                        self._add_to_need_analyze_obj_list('java', f'{class_db["package_name"]}.{class_name}', None, None, commit_or_branch, class_db)
            for field_db in fields_list:
                node_id = self.view.create_node_category(class_name, field_db['field_name'], constant.NODE_TYPE_FIELD, constant.DIFF_TYPE_CHANGED, diff_content, class_filepath, field_db['documentation'], '', {})
                field_db['field_node_id'] = node_id
                self._add_to_need_analyze_obj_list('java', f'{class_db["package_name"]}.{class_name}', field_db['field_name'], None, commit_or_branch, field_db)
            for method_db in methods_list:
                node_extend_dict = {'is_api': False}
                if is_controller and method_db['is_api']:
                    node_extend_dict = {
                        'is_api': True,
                        'api_path': method_db['api_path']
                    }
                method_name_param = f'{method_db["method_name"]}({",".join([param["parameter_type"] for param in json.loads(method_db["parameters"])])})'
                node_id = self.view.create_node_category(class_name, method_name_param, constant.NODE_TYPE_METHOD, constant.DIFF_TYPE_CHANGED, diff_content, class_filepath, method_db['documentation'], method_db['body'], node_extend_dict)
                method_db['method_node_id'] = node_id
                self._add_to_need_analyze_obj_list('java', f'{class_db["package_name"]}.{class_name}', None, method_name_param, commit_or_branch, method_db)

    # Step 5
    def _impacted_analyze(self, need_analyze_obj: dict):
        file_type = need_analyze_obj['file_type']
        package_class = need_analyze_obj['package_class']
        commit_or_branch = need_analyze_obj['commit_or_branch']
        package_name = '.'.join(package_class.split('.')[0: -1])
        class_name = package_class.split('.')[-1]
        class_db_list = self.sqlite.select_data(f'SELECT * FROM class WHERE project_id = {self.project_id} and class_name="{class_name}" and package_name="{package_name}"')
        class_entity = self._get_right_class_entity(class_db_list, commit_or_branch)
        if not class_entity:
            return
        class_filepath = class_entity['filepath']
        class_id = class_entity["class_id"]
        # gengxin
        commit_or_branch = class_entity['commit_or_branch']
        is_controller = class_entity['is_controller']
        # todo 粗查，待细化
        if file_type == 'xml':
            method_name = need_analyze_obj['method_param']
            mapper_method_node_id = need_analyze_obj['method_node_id']
            impacted_methods = self.sqlite.select_data(f'SELECT * FROM methods WHERE class_id={class_id} and method_name="{method_name}"')
            if not impacted_methods:
                return
            for impacted_method in impacted_methods:
                node_extend_dict = {'is_api': False}
                if is_controller and impacted_method['is_api']:
                    node_extend_dict = {
                        'is_api': True,
                        'api_path': impacted_method['api_path']
                    }
                method_name_param = f'{impacted_method["method_name"]}({",".join([param["parameter_type"] for param in json.loads(impacted_method["parameters"])])})'
                impacted_method_node_id = self.view.create_node_category(class_name, method_name_param,
                                                                         constant.NODE_TYPE_METHOD, constant.DIFF_TYPE_IMPACTED,
                                                                         impacted_method['body'], class_filepath, impacted_method['documentation'],
                                                                         impacted_method['body'], node_extend_dict)
                self.view.create_node_link(mapper_method_node_id, impacted_method_node_id)
                extend_dict = {'method_node_id': impacted_method_node_id}
                extend_dict.update(impacted_method)
                self._add_to_need_analyze_obj_list('java', package_class, None, self._get_method_param_string(impacted_method), commit_or_branch, extend_dict)
        else:
            # analyze entity use
            entity_impacted_methods = []
            source_node_id = None
            if not need_analyze_obj.get('field_name') and not need_analyze_obj.get('method_param'):
                class_node_id = self.view.create_node_category(class_name, 'entity', constant.NODE_TYPE_CLASS, constant.DIFF_TYPE_IMPACTED, '', self.file_path, '', '', {})
                entity_impacted_methods = self._get_entity_invocation_in_methods_table(package_class)
                source_node_id = class_node_id
            elif need_analyze_obj.get('field_name'):
                annotations: list = json.loads(class_entity['annotations'])
                entity_impacted_methods = self._get_field_invocation_in_methods_table(package_class, need_analyze_obj, annotations, commit_or_branch)
                source_node_id = need_analyze_obj.get('field_node_id')
            elif need_analyze_obj.get('method_param'):
                method_param = need_analyze_obj.get('method_param')
                method_name: str = method_param.split('(')[0]
                method_node_id = need_analyze_obj.get('method_node_id')
                source_node_id = method_node_id
                entity_impacted_methods = self._get_method_invocation_in_methods_table(package_class, method_param, commit_or_branch)
                method_db = self.sqlite.select_data(f'SELECT * FROM methods WHERE method_id = {need_analyze_obj.get("method_id")}')[0]
                is_override_method = 'Override' in method_db['annotations']
                if is_override_method:

                    if class_entity['extends_class']:
                        abstract_package_class = self._is_method_param_in_extends_package_class(method_param, class_entity['extends_class'], 'True', commit_or_branch)
                        if abstract_package_class:
                            extends_methods = self._get_method_invocation_in_methods_table(abstract_package_class, method_param, commit_or_branch)
                            for method in extends_methods:
                                method['class_id'] = class_id
                            entity_impacted_methods += extends_methods

                    if class_entity['implements']:
                        class_implements = class_entity['implements'].split(',')
                        class_implements_obj = self.sqlite.select_data(f'''select c.package_name , c.class_name from methods m left join class c on c.class_id = m.class_id 
                                                where c.project_id = {self.project_id} and m.method_name = '{method_name}' and c.class_name in ("{'","'.join(class_implements)}")''')
                        if class_implements_obj:
                            implements_package_class = class_implements_obj[0].get('package_name') + '.' + class_implements_obj[0].get('class_name')
                            implements_methods = self._get_method_invocation_in_methods_table(implements_package_class, method_param, commit_or_branch)
                            entity_impacted_methods += implements_methods
                else:
                    class_method_db = self.sqlite.select_data(f'SELECT * FROM methods WHERE class_id = {class_id} and method_name = "{method_name}"')
                    if not class_method_db:
                        extends_package_class = self._is_method_param_in_extends_package_class(method_param, class_entity['extends_class'], 'False', commit_or_branch)
                        if extends_package_class:
                            extends_methods = self._get_method_invocation_in_methods_table(extends_package_class, method_param, commit_or_branch)
                            entity_impacted_methods += extends_methods
            if not entity_impacted_methods:
                return
            self._handle_impacted_methods(entity_impacted_methods, source_node_id)

    def _is_method_param_in_extends_package_class(self, method_param, extends_package_class, is_abstract, commit_or_branch):
        method_name: str = method_param.split('(')[0]
        extends_package = '.'.join(extends_package_class.split('.')[0: -1])
        extends_class_name = extends_package_class.split('.')[-1]
        extends_class_db = self.sqlite.select_data(f'SELECT * FROM class WHERE package_name = "{extends_package}" and class_name = "{extends_class_name}" and project_id = {self.project_id} and commit_or_branch = "{commit_or_branch}"')
        if not extends_class_db:
            return None
        extends_class_id = extends_class_db[0]['class_id']
        methods_db = self.sqlite.select_data(f'SELECT * FROM methods WHERE class_id = {extends_class_id} and method_name = "{method_name}" and is_abstract = "{is_abstract}"')
        if methods_db:
            return extends_package_class
        else:
            if extends_class_db[0]['extends_class']:
                return self._is_method_param_in_extends_package_class(method_param, extends_class_db[0]['extends_class'], is_abstract, commit_or_branch)
            else:
                return None

    def _get_extends_package_class(self, package_class):
        extends_package_class_list = []
        extends_package_class_db = self.sqlite.select_data(f'SELECT * FROM class WHERE project_id = {self.project_id} AND extends_class="{package_class}"')
        if extends_package_class_db:
            extends_package_class_list = [f'{class_item["package_name"]}.{class_item["class_name"]}' for class_item in extends_package_class_db]
            for extends_package_class in extends_package_class_list:
                extends_package_class_list += self._get_extends_package_class(extends_package_class)
        return extends_package_class_list

    # Step 5.1
    def _get_right_class_entity(self, class_db_list, commit_or_branch):
        right_class_entity = next((item for item in class_db_list if item.get("commit_or_branch") == commit_or_branch), None)
        if right_class_entity is None:
            right_class_entity = next((item for item in class_db_list if item.get("commit_or_branch") == self.commit_or_branch_new), None)
        return right_class_entity

    # Step 5.2
    def _get_entity_invocation_in_methods_table(self, package_class: str):
        return self.sqlite.select_data(f'''SELECT * FROM methods WHERE project_id = {self.project_id} AND json_extract(method_invocation_map, '$."{package_class}".entity') IS NOT NULL''')

    # Step 5.3
    def _get_field_invocation_in_methods_table(self, package_class, field_obj, annotations, commit_or_branch):
        is_static = field_obj['is_static']
        field_name = field_obj['field_name']
        if not is_static:
            # todo static maybe has bug
            field_methods_set = set()
            field_name_capitalize = field_name[0].upper() + field_name[1:]
            for annotation in annotations:
                annotation_name = annotation.get('name')
                if annotation_name == 'Data':
                    field_methods_set.add(f'get{field_name_capitalize}(')
                    field_methods_set.add(f'set{field_name_capitalize}(')
                elif annotation_name == 'Getter':
                    field_methods_set.add(f'get{field_name_capitalize}(')
                elif annotation_name == 'Setter':
                    field_methods_set.add(f'set{field_name_capitalize}(')
                else:
                    continue
            if not field_methods_set:
                return []
            json_extract_sql_list = []
            for field_method in field_methods_set:
                sql_part = f'''json_extract(method_invocation_map, '$."{package_class}".methods.keys(@.startsWith("{field_method}"))') IS NOT NULL'''
                json_extract_sql_list.append(sql_part)
            sql = f'SELECT * FROM methods WHERE project_id = {self.project_id} AND (' + ' OR '.join(json_extract_sql_list) + ')'
        else:
            sql = f'''SELECT * FROM methods WHERE project_id = {self.project_id} AND json_extract(method_invocation_map, '$."{package_class}".fields.{field_name}') IS NOT NULL'''
        methods = self.sqlite.select_data(sql)
        if not methods:
            return []
        class_ids = [str(method['class_id']) for method in methods]
        class_sql = f'SELECT * FROM class WHERE class_id in ({", ".join(class_ids)}) and commit_or_branch ="{commit_or_branch}"'
        class_db = self.sqlite.select_data(class_sql)
        class_db_id = [class_item['class_id'] for class_item in class_db]
        return [method for method in methods if method['class_id'] in class_db_id]

    # Step 5.4
    def _get_method_invocation_in_methods_table(self, package_class, method_param, commit_or_branch):
        all_possible_method_param_type_list = self._gen_all_possible_method_param_list(method_param)
        json_extract_sql_list = []
        for param_type in all_possible_method_param_type_list:
            sql_part = f'''json_extract(method_invocation_map, '$."{package_class}".methods."{param_type}"') IS NOT NULL'''
            json_extract_sql_list.append(sql_part)
        if len(json_extract_sql_list) > 1000:
            json_extract_sql_list = json_extract_sql_list[0: 995]
        sql = f'SELECT * FROM methods WHERE project_id = {self.project_id} AND (' + ' OR '.join(json_extract_sql_list) + ')'
        logging.info(f'{package_class} {method_param} invocation sql: {sql}')
        methods = self.sqlite.select_data(sql)
        class_ids = [str(method['class_id']) for method in methods]
        class_sql = f'SELECT * FROM class WHERE class_id in ({", ".join(class_ids)}) and commit_or_branch ="{commit_or_branch}"'
        class_db = self.sqlite.select_data(class_sql)
        class_db_id = [class_item['class_id'] for class_item in class_db]
        return [method for method in methods if method['class_id'] in class_db_id]

    # Step 5.4.1
    def _gen_all_possible_method_param_list(self, method_param):
        method_param_list = []
        method_name = method_param.split('(')[0]
        param_type_str = method_param.split('(')[1].split(')')[0]
        param_type_list = param_type_str.split(',')
        if not param_type_list:
            return method_param_list
        all_possible_method_param_list = self._replace_with_null_unknown(param_type_list)
        for param_type_list in all_possible_method_param_list:
            method_param_list.append(f'{method_name}({",".join(param_type_list)})')
        return method_param_list

    def _replace_extends_class(self, new_lst, results):
        for i in range(0, len(new_lst)):
            if new_lst[i].lower() in constant.JAVA_BASIC_TYPE \
                    or new_lst[i] == constant.PARAMETER_TYPE_METHOD_INVOCATION_UNKNOWN \
                    or new_lst[i] == 'null':
                continue
            extends_package_class_list = self._get_extends_package_class(new_lst[i])
            for extends_package_class in extends_package_class_list:
                result_item = [item for item in new_lst]
                result_item[i] = extends_package_class
                results.append(result_item)

    def _is_duplicate_item(self, new_lst, lst):
        is_duplicate = False
        for item in lst:
            if item == new_lst:
                is_duplicate = True
                break
        return is_duplicate

    # Step 5.4.1.1
    def _replace_with_null_unknown(self, lst: list):
        need_replace_list = []
        replaced_list = []
        results = []
        self._replace_params_with_unknown(lst, results, 0, need_replace_list)
        for item in need_replace_list:
            if item not in replaced_list:
                replaced_list.append(item)
                self._replace_params_with_unknown(item['list'], results, item['index'], need_replace_list)
        return list(set(tuple(sub_list) for sub_list in results))

    def _replace_params_with_unknown(self, lst: list, results: list, idx: int, need_replace_list: list):
        # data = [item.split('<')[0].replace('<', '').replace('>', '') for item in data]
        for i in range(idx, len(lst)):
            new_lst = lst[:]
            if not self._is_duplicate_item(new_lst, results):
                results.append(new_lst)
            if new_lst[i].lower() not in constant.JAVA_BASIC_TYPE:
                new_lst2 = new_lst[:]
                if new_lst[i].startswith('List'):
                    new_lst2[i] = 'ArrayList'
                elif new_lst[i].startswith('Map'):
                    new_lst2[i] = 'HashMap'
                elif new_lst[i].startswith('Set'):
                    new_lst2[i] = 'HashSet'
                if not self._is_duplicate_item(new_lst2, results):
                    results.append(new_lst2)
                    need_replace_list.append({'list': new_lst2, 'index': idx})
            else:
                if new_lst[i][0].isupper() and new_lst[i] != 'String':
                    new_lst2 = new_lst[:]
                    new_lst2[i] = new_lst[i][0].lower() + new_lst[i][1:]
                    if not self._is_duplicate_item(new_lst2, results):
                        results.append(new_lst2)
                        need_replace_list.append({'list': new_lst2, 'index': idx})
            for el in ['null', 'unknown']:
                new_lst_tmp = new_lst[:]
                new_lst_tmp[i] = el
                if not self._is_duplicate_item(new_lst_tmp, results):
                    results.append(new_lst_tmp)
                    need_replace_list.append({'list': new_lst_tmp, 'index': min(idx, len(new_lst) - 1)})

    # Step 5.5
    def _get_method_param_string(self, method_db: dict):
        method_name: str = method_db['method_name']
        params: list = json.loads(method_db['parameters'])
        params_type_list = [param['parameter_type'] for param in params]
        return f'{method_name}({",".join(params_type_list)})'

    # Step 5.9
    def _handle_impacted_methods(self, impacted_methods: list, source_node_id):
        for impacted_method in impacted_methods:
            is_api = impacted_method.get('is_api') == 'True'
            node_extend_dict = impacted_method
            node_extend_dict['is_api'] = is_api
            class_id = impacted_method['class_id']
            class_entity = self.sqlite.select_data(f'SELECT * FROM class WHERE class_id={class_id}')[0]
            class_name = class_entity['class_name']
            package_name = class_entity['package_name']
            package_class = f'{package_name}.{class_name}'
            commit_or_branch = class_entity['commit_or_branch']
            class_filepath = class_entity['filepath']
            node_extend_dict['class_annotations'] = class_entity['annotations']
            method_name_param = f'{impacted_method["method_name"]}({",".join([param["parameter_type"] for param in json.loads(impacted_method["parameters"])])})'
            impacted_method_node_id = self.view.create_node_category(class_name, method_name_param, constant.NODE_TYPE_METHOD, constant.DIFF_TYPE_IMPACTED, impacted_method['body'], class_filepath, impacted_method['documentation'], impacted_method['body'], node_extend_dict)
            self.view.create_node_link(source_node_id, impacted_method_node_id)
            extend_dict = {'method_node_id': impacted_method_node_id, 'class_filepath': class_filepath}
            extend_dict.update(impacted_method)
            self._add_to_need_analyze_obj_list('java', package_class, None, self._get_method_param_string(impacted_method), commit_or_branch, extend_dict)

    def _add_to_need_analyze_obj_list(self, file_type: str, package_class: str, field_name: str or None, method_param: str or None, commit_or_branch: str, mapper_extend_dict: dict):
        need_analyze_entity: dict = {
            'file_type': file_type,
            'package_class': package_class,
            'field_name': field_name,
            'method_param': method_param,
            'commit_or_branch': commit_or_branch
        }
        is_exist = [obj for obj in self.need_analyze_obj_list if self.check_dict_keys_equal_values(need_analyze_entity, obj)]
        if not is_exist:
            need_analyze_entity.update(mapper_extend_dict)
            self.need_analyze_obj_list.append(need_analyze_entity)

    def check_dict_keys_equal_values(self, dict1, dict2):
        for key in dict1:
            if key in dict2 and dict1[key] != dict2[key]:
                return False
        return True

    def _draw_and_write_result(self):
        if self.view.nodes:
            self.view.draw_graph(1200, 600)
        logging.info(f'Analyze success, generating cci result file......')
        result = {
            'nodes': self.view.nodes,
            'links': self.view.links,
            'categories': self.view.categories,
            'impacted_api_list': [node['api_path'] for node in self.view.nodes if node.get('is_api')]
        }
        print(json.dumps(result), flush=True)
        print(f'Impacted api list: {result["impacted_api_list"]}', flush=True)
        with open(self.cci_filepath, 'w') as w:
            w.write(json.dumps(result))
        logging.info(f'Generating cci result file success, location: {self.cci_filepath}')

    def _start_analysis_diff_and_impact(self):
        for patch_path, patch_obj in self.diff_parse_map.items():
            self._diff_analyze(patch_path, patch_obj)

        # 遍历列表
        for obj in self.need_analyze_obj_list:
            if obj not in self.analyzed_obj_set:  # 判断对象是否已分析过
                self.analyzed_obj_set.append(obj)  # 标记为已分析过
                self._impacted_analyze(obj)  # 处理对象,返回新增对象列表

        self._draw_and_write_result()
        t2 = datetime.datetime.now()
        try:
            logging.info(f'Analyze done, remove occupy, others can analyze now')
            os.remove(os.path.join(self.file_path, 'Occupy.ing'))
        finally:
            pass
        logging.info(f'Analyze done, spend: {t2 - self.t1}')

    def analyze_two_branch(self, branch_first, branch_second):
        logging.info('*' * 10 + 'Analyze start' + '*' * 10)
        self.commit_or_branch_new = branch_first
        self.commit_or_branch_old = branch_second
        self.branch_name = branch_first
        self.project_name = self.git_url.split('/')[-1].split('.git')[0]
        self.file_path = os.path.join(config.project_path, self.project_name)
        self.project_id = self.sqlite.add_project(self.project_name, self.git_url, self.branch_name, branch_first, branch_second)
        # 已有分析结果
        self.cci_filepath = os.path.join(self.file_path, f'{branch_second.replace("/", "#")}..{branch_first.replace("/", "#")}.cci')
        self._can_analyze(self.file_path, self.cci_filepath)
        # 无此项目, 先clone项目
        if not os.path.exists(self.file_path):
            logging.info(f'Cloning project: {self.git_url}')
            os.system(f'git clone -b {branch_first} {self.git_url} {self.file_path}')
        self._occupy_project()
        self.diff_parse_map = self._get_branch_diff_parse_map(self.file_path, branch_first, branch_second)
        self.xml_parse_results_new, self.xml_parse_results_old = self._parse_branch_project(self.file_path, branch_first, branch_second)
        self._start_analysis_diff_and_impact()

    def analyze_two_commit(self, branch, commit_first, commit_second):
        logging.info('*' * 10 + 'Analyze start' + '*' * 10)
        self.branch_name = branch
        self.commit_or_branch_new = commit_first[0: 7] if len(commit_first) > 7 else commit_first
        self.commit_or_branch_old = commit_second[0: 7] if len(commit_second) > 7 else commit_second

        self.project_name = self.git_url.split('/')[-1].split('.git')[0]
        self.file_path = os.path.join(config.project_path, self.project_name)

        self.project_id = self.sqlite.add_project(self.project_name, self.git_url, self.branch_name, self.commit_or_branch_new, self.commit_or_branch_old)
        # 已有分析结果
        self.cci_filepath = os.path.join(self.file_path, f'{self.commit_or_branch_old}..{self.commit_or_branch_new}.cci')
        self._can_analyze(self.file_path, self.cci_filepath)

        # 无此项目, 先clone项目
        if not os.path.exists(self.file_path):
            logging.info(f'Cloning project: {self.git_url}')
            os.system(f'git clone -b {self.branch_name} {self.git_url} {self.file_path}')

        self._occupy_project()
        self.diff_parse_map = self._get_diff_parse_map(self.file_path, self.branch_name, self.commit_or_branch_new, self.commit_or_branch_old)

        self.xml_parse_results_new, self.xml_parse_results_old = self._parse_project(self.file_path, self.commit_or_branch_new, self.commit_or_branch_old)

        self._start_analysis_diff_and_impact()

    def analyze_class_method(self, branch, commit_id, package_class, method_nums):
        logging.info('*' * 10 + 'Analyze start' + '*' * 10)
        package_class = package_class.replace("\\", "/")
        self.branch_name = branch
        self.commit_or_branch_new = commit_id
        self.commit_or_branch_new = self.commit_or_branch_new[0: 7] if len(self.commit_or_branch_new) > 7 else self.commit_or_branch_new
        self.project_name = self.git_url.split('/')[-1].split('.git')[0]
        self.file_path = os.path.join(config.project_path, self.project_name)

        self.project_id = self.sqlite.add_project(self.project_name, self.git_url, self.branch_name, self.commit_or_branch_new, f'{package_class}.{method_nums}')
        class_name = package_class.split("/")[-1].replace('.java', '')
        cci_path = f'{branch.replace("/", "#")}_{commit_id}_{class_name}_{method_nums}.cci'
        self.cci_filepath = os.path.join(self.file_path, cci_path)
        self._can_analyze(self.file_path, self.cci_filepath)

        # 无此项目, 先clone项目
        if not os.path.exists(self.file_path):
            logging.info(f'Cloning project: {self.git_url}')
            os.system(f'git clone -b {self.branch_name} {self.git_url} {self.file_path}')
        self._occupy_project()

        logging.info('Git pull project to HEAD')
        os.system(f'cd {self.file_path} && git checkout {branch} && git pull')
        time.sleep(1)

        self.xml_parse_results_new, self.xml_parse_results_old = self._parse_project(self.file_path, self.commit_or_branch_new, None)

        if not method_nums:
            method_nums_all = []
            # todo
            class_db = self.sqlite.select_data('SELECT * FROM class WHERE project_id = ' + str(self.project_id) + ' and filepath LIKE "%' + package_class + '"')
            if not class_db:
                logging.error(f'Can not find {package_class} in db')
            class_id = class_db[0]['class_id']
            field_db = self.sqlite.select_data(f'SELECT * FROM field WHERE class_id = {class_id}')
            method_nums_all += [field['start_line'] for field in field_db]
            method_db = self.sqlite.select_data(f'SELECT * FROM methods WHERE class_id = {class_id}')
            method_nums_all += [method['start_line'] for method in method_db]
        else:
            method_nums_all = [int(num) for num in method_nums.split(',')]

        self.diff_parse_map[package_class] = {
            'line_num_added': method_nums_all,
            'line_content_added': method_nums_all,
            'line_num_removed': [],
            'line_content_removed': []
        }

        self._start_analysis_diff_and_impact()
