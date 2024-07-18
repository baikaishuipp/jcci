from . import constant as constant
from collections import deque

def max_relationship_length(relationships):
    if not relationships:
        return {}
    # 构建邻接列表
    graph = {}
    for relationship in relationships:
        source = relationship['source']
        target = relationship['target']
        if source == target:
            continue
        if source not in graph:
            graph[source] = set()
        if target not in graph:
            graph[target] = set()
        graph[source].add(target)

    # BFS遍历计算每个节点到起点的最长路径长度
    longest_paths = {node: 0 for node in graph.keys()}
    unvisited_nodes = set(graph.keys())
    while unvisited_nodes:
        start_node = unvisited_nodes.pop()
        queue = deque([(start_node, 0)])
        visited_queue_node_list = [start_node]
        while queue:
            node, path_length = queue.popleft()
            if node not in visited_queue_node_list:
                visited_queue_node_list.append(node)
            unvisited_nodes.discard(node)
            for neighbor in graph.get(node, set()):
                if path_length + 1 > longest_paths[neighbor]:
                    longest_paths[neighbor] = path_length + 1
                    if neighbor not in visited_queue_node_list:
                        queue.append((neighbor, path_length + 1))
    return longest_paths


class Graph(object):

    def __init__(self):
        self.nodes = []
        self.links = []
        self.categories = []
        self.node_index_init = 0

    def create_node_category(self, class_or_xml, name, type, diff_type, diff_content, file_path, documentation, body, extend_dict: dict):
        category = {
            'name': class_or_xml
        }
        if category not in self.categories:
            self.categories.append(category)
        if class_or_xml == name:
            return
        category_id = self.categories.index(category)
        node_create = {
            'category': category_id,
            'id': str(self.node_index_init),
            'name': class_or_xml + '.' + name,
            'type': type,
            'diff_type': [diff_type],
            'file_path': file_path,
        }
        if diff_type == constant.DIFF_TYPE_CHANGED:
            node_create.update({
                'diff_content': diff_content,
                'documentation': documentation,
                'body': body,
            })
        node_exist = [node for node in self.nodes if node['name'] == node_create['name'] and node['type'] == type and node['file_path'] == file_path]
        if node_exist:
            node_create: dict = node_exist[0]
            self.nodes.remove(node_create)
            if diff_type not in node_create['diff_type']:
                node_create['diff_type'].append(diff_type)
            node_create.update(extend_dict)
            self.nodes.append(node_create)
        else:
            node_create.update(extend_dict)
            self.nodes.append(node_create)
            self.node_index_init += 1
        return node_create['id']

    def create_node_link(self, source_node_id, target_node_id):
        if source_node_id is None or target_node_id is None:
            return
        if source_node_id == target_node_id:
            return
        link = {
            'source': source_node_id,
            'target': target_node_id
        }
        reverse_link = {
            'source': target_node_id,
            'target': source_node_id
        }
        if link not in self.links and reverse_link not in self.links:
            self.links.append(link)

    def draw_graph(self, canvas_width, canvas_height):
        # 每个类别区域划分的行数
        all_node = []
        result = max_relationship_length(self.links)
        changed_nodes = [node for node in self.nodes if 'changed' in node['diff_type']]
        impacted_nodes = [node for node in self.nodes if 'changed' not in node['diff_type']]
        for changed_node in changed_nodes:
            changed_node['x'] = 100
            changed_node['y'] = (changed_nodes.index(changed_node) + 1) * (canvas_height / len(changed_nodes))
            changed_node['symbolSize'] = 20
            changed_node['label'] = {
                'show': True,
                'formatter': changed_node["name"].split("(")[0]
            }
            tooltip = f'{changed_node["name"].split("(")[0]}<br>[Changed]{changed_node.get("diff_content", "")}'
            if changed_node.get('is_api'):
                tooltip = tooltip + f'<br>[API]{changed_node.get("api_path")}'
            changed_node['tooltip'] = {
                'show': True,
                'position': 'right',
                'formatter': tooltip
            }
            all_node.append(changed_node)
        max_link_count = max([value for key, value in result.items()]) if result else 1
        count_node_result = {}
        for key, value in result.items():
            value = str(value)
            if value not in count_node_result:
                count_node_result[value] = []
            count_node_result[value].append(key)
        for impacted_node in impacted_nodes:
            path_level = result.get(impacted_node['id'], 0)
            level_node_list = count_node_result.get(str(path_level), [impacted_node['id']])
            level_node_index = level_node_list.index(impacted_node['id']) if impacted_node['id'] in level_node_list else 1
            impacted_node['x'] = 100 + ((canvas_width - 100) / max_link_count) * (path_level + 1)
            impacted_node['y'] = (canvas_height / len(count_node_result.get(str(path_level), [1]))) * level_node_index
            impacted_node['label'] = {
                'show': True,
                'formatter': impacted_node["name"].split("(")[0]
            }
            if impacted_node.get('is_api'):
                tooltip = f'{impacted_node["name"].split("(")[0]}<br>[API]{impacted_node.get("api_path")}'
                impacted_node['tooltip'] = {
                    'show': True,
                    'position': 'right',
                    'formatter': tooltip
                }
            all_node.append(impacted_node)
        self.nodes = all_node

if __name__ == '__main__':
    # relationships = [{'source': '0', 'target': '9'}, {'source': '0', 'target': '2'}, {'source': '0', 'target': '10'}, {'source': '0', 'target': '1'}, {'source': '0', 'target': '11'}, {'source': '0', 'target': '12'}, {'source': '1', 'target': '13'}, {'source': '2', 'target': '13'}, {'source': '7', 'target': '14'}, {'source': '8', 'target': '15'}, {'source': '9', 'target': '13'}, {'source': '10', 'target': '13'}, {'source': '11', 'target': '13'}, {'source': '12', 'target': '13'}, {'source': '13', 'target': '16'}, {'source': '13', 'target': '17'}, {'source': '13', 'target': '18'}, {'source': '13', 'target': '19'}, {'source': '13', 'target': '20'}, {'source': '13', 'target': '21'}, {'source': '13', 'target': '22'}, {'source': '13', 'target': '23'}, {'source': '13', 'target': '24'}, {'source': '13', 'target': '25'}, {'source': '13', 'target': '26'}, {'source': '13', 'target': '27'}, {'source': '13', 'target': '28'}, {'source': '13', 'target': '7'}, {'source': '13', 'target': '8'}, {'source': '13', 'target': '29'}, {'source': '13', 'target': '30'}, {'source': '13', 'target': '31'}, {'source': '13', 'target': '32'}, {'source': '13', 'target': '33'}, {'source': '13', 'target': '34'}, {'source': '13', 'target': '35'}, {'source': '13', 'target': '36'}, {'source': '13', 'target': '37'}, {'source': '13', 'target': '38'}, {'source': '13', 'target': '39'}, {'source': '13', 'target': '40'}, {'source': '13', 'target': '41'}, {'source': '13', 'target': '42'}, {'source': '13', 'target': '43'}, {'source': '13', 'target': '44'}, {'source': '13', 'target': '45'}, {'source': '13', 'target': '46'}, {'source': '13', 'target': '47'}, {'source': '13', 'target': '48'}, {'source': '13', 'target': '49'}, {'source': '13', 'target': '50'}, {'source': '16', 'target': '51'}, {'source': '16', 'target': '52'}, {'source': '16', 'target': '53'}, {'source': '16', 'target': '54'}, {'source': '16', 'target': '55'}, {'source': '16', 'target': '56'}, {'source': '16', 'target': '57'}, {'source': '16', 'target': '58'}, {'source': '16', 'target': '59'}, {'source': '17', 'target': '60'}, {'source': '18', 'target': '61'}, {'source': '19', 'target': '62'}, {'source': '20', 'target': '63'}, {'source': '21', 'target': '64'}, {'source': '22', 'target': '65'}, {'source': '23', 'target': '66'}, {'source': '24', 'target': '67'}, {'source': '25', 'target': '68'}, {'source': '26', 'target': '69'}, {'source': '27', 'target': '70'}, {'source': '28', 'target': '71'}, {'source': '29', 'target': '72'}, {'source': '30', 'target': '73'}, {'source': '31', 'target': '74'}, {'source': '32', 'target': '75'}, {'source': '33', 'target': '76'}, {'source': '34', 'target': '77'}, {'source': '35', 'target': '78'}, {'source': '36', 'target': '79'}, {'source': '36', 'target': '80'}, {'source': '36', 'target': '81'}, {'source': '36', 'target': '82'}, {'source': '37', 'target': '83'}, {'source': '38', 'target': '84'}, {'source': '39', 'target': '85'}, {'source': '40', 'target': '86'}, {'source': '41', 'target': '87'}, {'source': '42', 'target': '83'}, {'source': '43', 'target': '88'}, {'source': '44', 'target': '89'}, {'source': '45', 'target': '90'}, {'source': '46', 'target': '91'}, {'source': '47', 'target': '92'}, {'source': '48', 'target': '93'}, {'source': '49', 'target': '94'}, {'source': '50', 'target': '95'}, {'source': '51', 'target': '96'}, {'source': '52', 'target': '97'}, {'source': '53', 'target': '52'}, {'source': '53', 'target': '98'}, {'source': '54', 'target': '99'}, {'source': '55', 'target': '100'}, {'source': '56', 'target': '101'}, {'source': '57', 'target': '98'}, {'source': '57', 'target': '102'}, {'source': '58', 'target': '103'}, {'source': '59', 'target': '104'}, {'source': '60', 'target': '105'}, {'source': '61', 'target': '105'}, {'source': '62', 'target': '105'}, {'source': '63', 'target': '105'}, {'source': '64', 'target': '105'}, {'source': '65', 'target': '106'}, {'source': '66', 'target': '105'}, {'source': '67', 'target': '105'}, {'source': '68', 'target': '105'}, {'source': '69', 'target': '105'}, {'source': '75', 'target': '107'}, {'source': '75', 'target': '108'}, {'source': '75', 'target': '109'}, {'source': '79', 'target': '110'}, {'source': '80', 'target': '111'}, {'source': '81', 'target': '105'}, {'source': '82', 'target': '112'}, {'source': '83', 'target': '113'}, {'source': '85', 'target': '114'}, {'source': '87', 'target': '115'}, {'source': '88', 'target': '105'}, {'source': '98', 'target': '116'}, {'source': '106', 'target': '105'}, {'source': '107', 'target': '117'}, {'source': '107', 'target': '118'}, {'source': '107', 'target': '119'}, {'source': '107', 'target': '120'}, {'source': '107', 'target': '121'}, {'source': '107', 'target': '122'}, {'source': '107', 'target': '123'}, {'source': '107', 'target': '124'}, {'source': '107', 'target': '125'}, {'source': '109', 'target': '126'}, {'source': '110', 'target': '13'}, {'source': '111', 'target': '13'}, {'source': '112', 'target': '105'}, {'source': '114', 'target': '127'}, {'source': '115', 'target': '105'}, {'source': '118', 'target': '128'}, {'source': '119', 'target': '129'}, {'source': '120', 'target': '130'}, {'source': '121', 'target': '131'}, {'source': '122', 'target': '132'}, {'source': '123', 'target': '133'}, {'source': '124', 'target': '134'}, {'source': '125', 'target': '135'}, {'source': '126', 'target': '136'}, {'source': '127', 'target': '105'}, {'source': '128', 'target': '105'}, {'source': '129', 'target': '105'}, {'source': '130', 'target': '105'}, {'source': '131', 'target': '105'}, {'source': '132', 'target': '105'}, {'source': '133', 'target': '105'}, {'source': '134', 'target': '105'}, {'source': '135', 'target': '105'}]
    relationships =  [{'source': 'A', 'target': 'B'},{'source': 'B', 'target': 'C'},{'source': 'C', 'target': 'D'},{'source': 'B', 'target': 'D'}]
    bb = max_relationship_length(relationships)
    print(bb)
