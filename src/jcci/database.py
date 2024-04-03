# -*- coding: UTF-8 -*-
import sqlite3
import time
import logging
import os
from src.jcci.sql import create_tables

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)

class SqliteHelper(object):
    def __init__(self, db_path):
        self.db_path = db_path

    def connect(self):
        try:
            if not os.path.exists(os.path.dirname(self.db_path)):
                os.makedirs(os.path.dirname(self.db_path))
            if not os.path.exists(self.db_path):
                db_file = open(self.db_path, "x")
                db_file.close()
                conn = sqlite3.connect(self.db_path)
                # 执行创建表的SQL语句
                try:
                    conn.cursor().executescript(create_tables)
                    logging.info("Table created successfully")
                except sqlite3.Error as e:
                    logging.error(f"Error creating table: {e}")
            else:
                conn = sqlite3.connect(self.db_path)
        except Exception as e:
            logging.error(f'connect fail {e}')
            time.sleep(1)
            conn = sqlite3.connect(self.db_path)
        return conn

    def add_project(self, project_name, git_url, branch, commit_or_branch_new, commit_or_branch_old):
        try:
            projects = self.select_data(f'SELECT * FROM project where project_name="{project_name}" and git_url="{git_url}" '
                                        f'and branch="{branch}" AND commit_or_branch_new="{commit_or_branch_new}" and commit_or_branch_old="{commit_or_branch_old}"')
            if projects:
                return projects[0]['project_id']
            conn = self.connect()
            c = conn.cursor()
            c.execute(f'INSERT INTO project '
                      f'(project_name, git_url, branch, commit_or_branch_new, commit_or_branch_old) '
                      f'VALUES("{project_name}", "{git_url}", "{branch}", "{commit_or_branch_new}", "{commit_or_branch_old}")')
            project_id = c.lastrowid
            conn.commit()
            conn.close()
            return project_id
        except Exception as e:
            logging.error(f'add_project fail')

    def add_class(self, filepath, access_modifier, class_type, class_name, package_name, extends_class, project_id, implements, annotations, documentation, is_controller, controller_base_url, commit_or_branch):
        try:
            class_list = self.select_data(f'SELECT * FROM class WHERE project_id={project_id} and package_name="{package_name}" and class_name="{class_name}" and commit_or_branch="{commit_or_branch}"')
            if class_list:
                return class_list[0]['class_id'], False
            conn = self.connect()
            c = conn.cursor()
            c.execute('INSERT INTO class (filepath, access_modifier, class_type, class_name, package_name, extends_class, project_id, implements, annotations, documentation, is_controller, controller_base_url, commit_or_branch) '
                      'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (filepath, access_modifier, class_type, class_name, package_name, extends_class, project_id, implements, annotations, documentation, is_controller, controller_base_url, commit_or_branch))
            class_id = c.lastrowid
            conn.commit()
            conn.close()
            return class_id, True
        except Exception as e:
            logging.error(e)
            logging.error(f'add_class fail')

    def select_data(self, sql):
        try:
            conn = self.connect()
            c = conn.cursor()
            cursor = c.execute(sql)
            res = cursor.fetchall()
            columns = cursor.description
            field = [column_name[0] for column_name in columns]
            zip_data = [dict(zip(field, item)) for item in res]
            conn.close()
            return zip_data
        except Exception as e:
            logging.error(f'select_data fail')
            raise e

    def update_data(self, sql):
        try:
            conn = self.connect()
            c = conn.cursor()
            c.execute(sql)
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f'select_data fail')

    def insert_data(self, table_name: str, data) -> bool:
        try:
            conn = self.connect()
            c = conn.cursor()
            if isinstance(data, list):
                for item in data:
                    keys = ",".join(list(item.keys()))
                    values = ",".join([f'''"{x.replace('"', '""').replace("'", "''")}"''' if isinstance(x, str) else f"'{x}'" for x in list(item.values())])
                    sql = f"INSERT INTO {table_name} ({keys}) VALUES ({values});"
                    c.execute(sql)
            elif isinstance(data, dict):
                keys = ",".join(list(data.keys()))
                values = ",".join([f"'{x}'" for x in list(data.values())])
                sql = f"INSERT INTO {table_name} ({keys}) VALUES ({values});"
                c.execute(sql)
            conn.commit()
            conn.close()
            return True
        except Exception as ex:
            logging.error(f"insert data error {ex}")
            return False
