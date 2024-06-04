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
            graph[source] = []
        if target not in graph:
            graph[target] = []
        graph[source].append(target)

    # BFS遍历计算每个节点到起点的最长路径长度
    longest_paths = {node: 0 for node in graph.keys()}
    graph_keys = [node for node in graph.keys()]
    longest_paths[graph_keys[0]] = 0
    queue = deque([(graph_keys[0], 0)])
    while queue:
        node, path_length = queue.popleft()
        if not graph.get(node) and not queue and graph_keys.index(node) + 1 < len(graph_keys):
            next_node = graph_keys[graph_keys.index(node) + 1]
            next_node_path_length = longest_paths[next_node]
            queue.append((next_node, next_node_path_length))
            continue
        for neighbor in graph.get(node, []):
            if path_length + 1 > longest_paths[neighbor]:
                longest_paths[neighbor] = path_length + 1
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
            if changed_node.get("annotations"):
                tooltip += f'<br>[annotations]{changed_node.get("annotations", "")}'
            if changed_node.get("class_annotations"):
                tooltip += f'<br>[class_annotations]{changed_node.get("class_annotations", "")}'
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
            tooltip = f'{impacted_node["name"].split("(")[0]}'
            if impacted_node.get('is_api'):
                tooltip += f'<br>[API]{impacted_node.get("api_path")}'
            if impacted_node.get("annotations"):
                tooltip += f'<br>[annotations]{impacted_node.get("annotations", "")}'
            if impacted_node.get("class_annotations"):
                tooltip += f'<br>[class_annotations]{impacted_node.get("class_annotations", "")}'
            impacted_node['tooltip'] = {
                'show': True,
                'position': 'right',
                'formatter': tooltip
            }
            all_node.append(impacted_node)
        self.nodes = all_node

if __name__ == '__main__':
    data = [{'source': '62', 'target': '61'}, {'source': '63', 'target': '64'}, {'source': '63', 'target': '65'}, {'source': '63', 'target': '66'}, {'source': '63', 'target': '67'}, {'source': '9', 'target': '8'}, {'source': '68', 'target': '25'}, {'source': '21', 'target': '18'}, {'source': '21', 'target': '19'}, {'source': '26', 'target': '25'}, {'source': '27', 'target': '25'}, {'source': '72', 'target': '5'}, {'source': '72', 'target': '8'}, {'source': '72', 'target': '9'}, {'source': '73', 'target': '18'}, {'source': '73', 'target': '19'}, {'source': '73', 'target': '20'}, {'source': '73', 'target': '21'}, {'source': '74', 'target': '17'}, {'source': '74', 'target': '54'}, {'source': '75', 'target': '76'}, {'source': '75', 'target': '3'}, {'source': '75', 'target': '77'}, {'source': '75', 'target': '5'}, {'source': '75', 'target': '78'}, {'source': '75', 'target': '79'}, {'source': '75', 'target': '6'}, {'source': '75', 'target': '80'}, {'source': '75', 'target': '8'}, {'source': '75', 'target': '9'}, {'source': '75', 'target': '81'}, {'source': '46', 'target': '47'}, {'source': '46', 'target': '60'}, {'source': '47', 'target': '61'}, {'source': '48', 'target': '47'}, {'source': '49', 'target': '46'}, {'source': '50', 'target': '46'}, {'source': '83', 'target': '17'}, {'source': '83', 'target': '18'}, {'source': '54', 'target': '17'}, {'source': '55', 'target': '18'}, {'source': '56', 'target': '55'}, {'source': '57', 'target': '55'}, {'source': '58', 'target': '56'}, {'source': '58', 'target': '57'}, {'source': '59', 'target': '54'}, {'source': '59', 'target': '55'}, {'source': '59', 'target': '56'}, {'source': '59', 'target': '57'}, {'source': '64', 'target': '66'}, {'source': '65', 'target': '64'}]
    bb = max_relationship_length(data)

