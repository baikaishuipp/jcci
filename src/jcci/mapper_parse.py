# -*- coding: UTF-8 -*-
import xml.etree.ElementTree as ET


class Mapper(object):
    def __init__(self, namespace, result_maps, sqls, statements):
        self.namespace = namespace
        self.result_maps = result_maps
        self.sqls = sqls
        self.statements = statements


class MapperElement(object):
    def __init__(self, id, type, start, end, content):
        self.id = id
        self.name = id
        self.type = type
        self.start = start
        self.end = end
        self.content = content
        self.diff_impact = None


class MapperStatement(MapperElement):
    def __init__(self, id, type, start_line, end_line, content, statement_tag, result_map, include_sql):
        super(MapperStatement, self).__init__(id, type, start_line, end_line, content)
        self.statement_tag = statement_tag
        self.result_map = result_map
        self.include_sql = include_sql


def parse(filepath):
    # 读取XML文件内容
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            xml_content = file.read()
    except:
        return None

    # 解析XML文件
    tree = ET.ElementTree(ET.fromstring(xml_content))
    root = tree.getroot()

    # 获取namespace
    try:
        namespace = root.attrib["namespace"]
        if namespace is None:
            return None
    except:
        return None
    # 存储resultMap和每条语句的id以及对应的起始行号和截止行号
    result_map_info = []
    sql_info = []
    statement_info = []

    # 获取resultMap的id以及起始行号和截止行号
    for element in root.findall(".//resultMap"):
        result_map_id = element.attrib["id"]
        start_line = 0
        end_line = 0
        for i, line in enumerate(xml_content.splitlines(), start=1):
            if line.strip().startswith('<resultMap') and f'id="{result_map_id}"' in line:
                start_line = i
            if f'</resultMap>' in line and start_line != 0:
                end_line = i
                break
        content = xml_content.splitlines()[start_line - 1: end_line]
        result_map_info.append(MapperElement(result_map_id, 'resultMap', start_line, end_line, content))

    # 获取resultMap的id以及起始行号和截止行号
    for sql_element in root.findall(".//sql"):
        sql_id = sql_element.attrib["id"]
        start_line = 0
        end_line = 0
        for i, line in enumerate(xml_content.splitlines(), start=1):
            if line.strip().startswith('<sql') and f'id="{sql_id}"' in line:
                start_line = i
            if f'</sql>' in line and start_line != 0:
                end_line = i
                break
        content = xml_content.splitlines()[start_line - 1: end_line]
        sql_info.append(MapperElement(sql_id, 'sql', start_line, end_line, content))

    # 获取每条语句的id以及起始行号和截止行号
    statements = root.findall(".//select") + root.findall(".//insert") + root.findall(".//update") + root.findall(".//delete")
    for statement_element in statements:
        statement_id = statement_element.attrib["id"]
        start_line = 0
        end_line = 0
        result_map = None
        include_sql = None
        for i, line in enumerate(xml_content.splitlines(), start=1):
            if f'<{statement_element.tag} id="{statement_id}"' in line:
                start_line = i
            if f'resultMap="' in line and start_line != 0:
                result_map = line.split('resultMap="')[1].split('"')[0]
            if line.strip().startswith('<include') and start_line != 0:
                include_sql = line.split('refid="')[1].split('"')[0]
            if f'</{statement_element.tag}>' in line and start_line != 0:
                end_line = i
                break
        content = xml_content.splitlines()[start_line - 1: end_line]
        statement_info.append(MapperStatement(statement_id, 'statement', start_line, end_line, content, statement_element.tag, result_map, include_sql))

    return Mapper(namespace, result_map_info, sql_info, statement_info)

