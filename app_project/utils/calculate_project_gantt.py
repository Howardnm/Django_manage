import json
from django.core.serializers.json import DjangoJSONEncoder


def get_project_gantt_data(project):
    """
    构造 Highcharts Gantt 数据 (平铺模式：不显示父级项目汇总条)
    """
    gantt_data = []

    # 1. 【修改】完全移除根节点的定义
    # 原来的 project_id 和 gantt_data.append({...}) 全部删掉
    # 这样图表中就不会出现第一行的“项目总览”条了

    # 我们只需要保留这个变量名用于逻辑（其实不用也没关系，为了代码改动最小，可以先删掉定义）
    # project_id = f"proj_{project.id}"

    start_time = project.created_at
    prev_node_id = None

    # 颜色配置
    COLORS = {
        'DOING': '#7cb5ec',  # 蓝
        'TERMINATED': '#f15c80',  # 红
        'FAILED': '#f15c80',
        'FEEDBACK': '#f7a35c',  # 橙
        'DONE': '#90ed7d',  # 绿
    }

    for i, node in enumerate(project.cached_nodes):
        if node.status == 'PENDING':
            continue

        end_time = node.updated_at
        node_id = str(node.id)

        # 计算完成度
        completion = 0
        if node.status == 'DONE':
            completion = 1
        elif node.status == 'DOING':
            completion = 0.5
        elif node.status in ['TERMINATED', 'FAILED', 'FEEDBACK']:
            completion = 1

        color = COLORS.get(node.status, '#e4d354')

        item = {
            'name': node.get_stage_display(),
            'id': node_id,
            # 【新增】把轮次传给前端。注意：Highcharts自定义字段最好不要和内置属性冲突
            'node_round': node.round,
            'start': int(start_time.timestamp() * 1000),
            'end': int(end_time.timestamp() * 1000),
            'color': color,
            'completed': {
                'amount': completion,
                'fill': color
            },
            'status_label': node.get_status_display(),
        }

        # 依赖关系保留 (虚线箭头依然有效)
        if prev_node_id:
            item['dependency'] = prev_node_id

        gantt_data.append(item)
        start_time = end_time
        prev_node_id = node_id

    return json.dumps(gantt_data, cls=DjangoJSONEncoder)