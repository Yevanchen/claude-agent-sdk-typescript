# Kanban Agent Eval 架构设计

## 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Eval Harness                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │ Task Suite   │  │ Trial Runner │  │ Graders               │  │
│  │ (YAML/JSON)  │  │              │  │ - State Check         │  │
│  │              │  │              │  │ - Tool Call Check     │  │
│  │ - task_id    │  │ 1. Reset DB  │  │ - LLM Rubric          │  │
│  │ - prompt     │  │ 2. Call Agent│  │                       │  │
│  │ - graders    │  │ 3. Run Grade │  │                       │  │
│  └──────────────┘  └──────┬───────┘  └───────────────────────┘  │
└────────────────────────────┼────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Harness (Dify Workflow)                 │
│                                                                  │
│  ┌──────────┐    ┌─────────────┐    ┌──────────────────────┐   │
│  │  Input   │───▶│   LLM Node  │───▶│  Tool Call Node      │   │
│  │  (Task)  │    │  (Claude)   │    │  (HTTP Request)      │   │
│  └──────────┘    └─────────────┘    └──────────┬───────────┘   │
│                         ▲                       │               │
│                         │                       │               │
│                         └───────────────────────┘               │
│                            (Loop until done)                    │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Kanban Tools API (FastAPI)                    │
│                                                                  │
│  POST /tools/list_boards      GET  /tools/get_board_overview    │
│  POST /tools/create_task      POST /tools/move_task             │
│  POST /tools/update_task      POST /tools/search_tasks          │
│  ...                                                            │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SQLite Database (kanban.db)                   │
│                                                                  │
│  boards ─┬─ columns ─── tasks ─┬─ task_labels                   │
│          │                     └─ comments                       │
│          └─ labels                                               │
└─────────────────────────────────────────────────────────────────┘
```

## 组件说明

### 1. Eval Harness (评估框架)

负责：
- 定义测试任务 (Task Suite)
- 运行测试 (Trial Runner)
- 评分 (Graders)

```python
# 示例任务定义
task = {
    "id": "move_high_priority_tasks",
    "prompt": "请将所有高优先级(high/urgent)的待办任务移动到'进行中'列",
    "setup": "reset_to_default",  # 每次测试前重置数据库
    "graders": [
        {
            "type": "state_check",
            "query": "SELECT COUNT(*) FROM tasks WHERE priority IN ('high','urgent') AND column_id = (SELECT id FROM columns WHERE name='待办')",
            "expect": 0  # 期望待办列没有高优先级任务
        },
        {
            "type": "state_check",
            "query": "SELECT COUNT(*) FROM tasks WHERE priority IN ('high','urgent') AND column_id = (SELECT id FROM columns WHERE name='进行中')",
            "expect": ">0"  # 期望进行中列有高优先级任务
        }
    ]
}
```

### 2. Agent Harness (Dify Workflow)

Dify Workflow 设计：

```
[Start]
    │
    ▼
[LLM Node: Task Planner]
    │ System: 你是一个项目管理助手，可以使用以下工具操作看板...
    │ User: {{task_prompt}}
    │
    ▼
[Tool Node: Execute Action]  ◄────┐
    │ 调用 Kanban API              │
    │                              │
    ▼                              │
[LLM Node: Evaluate Result]        │
    │ 判断任务是否完成              │
    │                              │
    ▼                              │
[Condition: Done?]                 │
    │                              │
    ├─ No ─────────────────────────┘
    │
    ▼ Yes
[End: Return Summary]
```

### 3. Kanban Tools API

暴露给 Dify 的工具接口：

| Tool | 描述 | 参数 |
|------|------|------|
| `list_boards` | 列出所有看板 | - |
| `get_board_overview` | 获取看板详情 | board_id |
| `list_tasks` | 列出任务 | column_id?, assignee_id? |
| `create_task` | 创建任务 | column_id, title, priority?, ... |
| `update_task` | 更新任务 | task_id, title?, priority?, ... |
| `move_task` | 移动任务 | task_id, target_column_id |
| `delete_task` | 删除任务 | task_id |
| `search_tasks` | 搜索任务 | query |

## 评估流程

```
1. Eval Harness 选择一个 Task
       │
       ▼
2. 重置数据库到初始状态 (隔离每个 trial)
       │
       ▼
3. 调用 Dify Workflow API，传入 task prompt
       │
       ▼
4. Dify Agent 执行 (可能多轮 tool calls)
       │
       ▼
5. Agent 返回结果 + 完整 transcript
       │
       ▼
6. Graders 检查:
   - 数据库状态是否符合预期
   - Agent 是否调用了必要的 tools
   - (可选) LLM 评判响应质量
       │
       ▼
7. 记录结果，进入下一个 trial 或 task
```

## 示例评估任务

### Task 1: 移动高优先级任务
```yaml
id: move_high_priority_001
prompt: 将所有高优先级和紧急的待办任务移动到进行中
graders:
  - type: state_check
    description: 待办列不应有高优先级任务
    sql: SELECT COUNT(*) FROM tasks t JOIN columns c ON t.column_id=c.id WHERE c.name='待办' AND t.priority IN ('high','urgent')
    expect: 0
```

### Task 2: 创建并分配任务
```yaml
id: create_and_assign_001
prompt: 在产品开发看板创建一个紧急任务"修复登录bug"，分配给 bob
graders:
  - type: state_check
    sql: SELECT COUNT(*) FROM tasks WHERE title LIKE '%登录bug%' AND priority='urgent' AND assignee_id=2
    expect: 1
```

### Task 3: 清理已完成任务
```yaml
id: cleanup_done_001
prompt: 删除所有已完成列中超过7天的任务
graders:
  - type: tool_calls
    required: [delete_task]
  - type: state_check
    sql: SELECT COUNT(*) FROM tasks t JOIN columns c ON t.column_id=c.id WHERE c.name='已完成'
    expect: "<initial_count"
```

## 运行多个 Trials

由于 LLM 输出的非确定性，每个 task 应该运行多次：

```python
results = []
for trial in range(k):
    reset_database()
    transcript = run_agent(task.prompt)
    score = run_graders(task.graders)
    results.append({"trial": trial, "score": score, "transcript": transcript})

# 计算 pass@k 和 pass^k
pass_at_k = any(r["score"] == 1.0 for r in results)
pass_pow_k = all(r["score"] == 1.0 for r in results)
```
