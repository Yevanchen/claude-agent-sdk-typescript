#!/usr/bin/env python3
"""
Kanban Tools API Server
为 Dify Workflow 提供工具调用接口
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import uvicorn
from pathlib import Path
import shutil

from kanban import KanbanDB, DB_PATH, SCHEMA_PATH

app = FastAPI(title="Kanban Tools API", version="1.0.0")

# 备份数据库路径，用于重置
BACKUP_DB_PATH = DB_PATH.parent / "kanban_backup.db"


# ==================== Request Models ====================

class CreateTaskRequest(BaseModel):
    column_id: int
    title: str
    description: Optional[str] = None
    priority: Optional[str] = "medium"
    assignee_id: Optional[int] = None
    due_date: Optional[str] = None


class UpdateTaskRequest(BaseModel):
    task_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[int] = None
    due_date: Optional[str] = None


class MoveTaskRequest(BaseModel):
    task_id: int
    target_column_id: int
    position: Optional[int] = None


class SearchTasksRequest(BaseModel):
    query: str
    board_id: Optional[int] = None


class AddCommentRequest(BaseModel):
    task_id: int
    user_id: int
    content: str


class AddLabelRequest(BaseModel):
    task_id: int
    label_id: int


# ==================== Database Management ====================

@app.post("/admin/reset_database")
def reset_database():
    """重置数据库到初始状态（用于 eval 隔离）"""
    if DB_PATH.exists():
        DB_PATH.unlink()
    with KanbanDB(DB_PATH) as db:
        db.init_db()
    return {"status": "success", "message": "Database reset to initial state"}


@app.post("/admin/backup_database")
def backup_database():
    """备份当前数据库"""
    if DB_PATH.exists():
        shutil.copy(DB_PATH, BACKUP_DB_PATH)
        return {"status": "success", "message": f"Backed up to {BACKUP_DB_PATH}"}
    raise HTTPException(status_code=404, detail="Database not found")


@app.post("/admin/restore_database")
def restore_database():
    """从备份恢复数据库"""
    if BACKUP_DB_PATH.exists():
        shutil.copy(BACKUP_DB_PATH, DB_PATH)
        return {"status": "success", "message": "Database restored from backup"}
    raise HTTPException(status_code=404, detail="Backup not found")


# ==================== Board Tools ====================

@app.get("/tools/list_boards")
def list_boards():
    """列出所有看板"""
    with KanbanDB() as db:
        boards = db.list_boards()
    return {"boards": boards}


@app.get("/tools/get_board/{board_id}")
def get_board(board_id: int):
    """获取看板基本信息"""
    with KanbanDB() as db:
        board = db.get_board(board_id)
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")
    return {"board": board}


@app.get("/tools/get_board_overview/{board_id}")
def get_board_overview(board_id: int):
    """获取看板完整概览（含所有列和任务）"""
    with KanbanDB() as db:
        overview = db.get_board_overview(board_id)
    if not overview:
        raise HTTPException(status_code=404, detail="Board not found")
    return {"board": overview}


# ==================== Column Tools ====================

@app.get("/tools/list_columns/{board_id}")
def list_columns(board_id: int):
    """列出看板的所有列"""
    with KanbanDB() as db:
        columns = db.list_columns(board_id)
    return {"columns": columns}


@app.get("/tools/get_column/{column_id}")
def get_column(column_id: int):
    """获取列信息"""
    with KanbanDB() as db:
        column = db.get_column(column_id)
    if not column:
        raise HTTPException(status_code=404, detail="Column not found")
    return {"column": column}


# ==================== Task Tools ====================

@app.get("/tools/list_tasks")
def list_tasks(column_id: Optional[int] = None, assignee_id: Optional[int] = None):
    """列出任务（可按列或负责人筛选）"""
    with KanbanDB() as db:
        tasks = db.list_tasks(column_id=column_id, assignee_id=assignee_id)
    return {"tasks": tasks}


@app.get("/tools/get_task/{task_id}")
def get_task(task_id: int):
    """获取任务基本信息"""
    with KanbanDB() as db:
        task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": task}


@app.get("/tools/get_task_details/{task_id}")
def get_task_details(task_id: int):
    """获取任务完整详情（含标签和评论）"""
    with KanbanDB() as db:
        task = db.get_task_details(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": task}


@app.post("/tools/create_task")
def create_task(request: CreateTaskRequest):
    """创建新任务"""
    with KanbanDB() as db:
        task_id = db.create_task(
            column_id=request.column_id,
            title=request.title,
            description=request.description,
            priority=request.priority,
            assignee_id=request.assignee_id,
            due_date=request.due_date
        )
        task = db.get_task(task_id)
    return {"status": "success", "task_id": task_id, "task": task}


@app.post("/tools/update_task")
def update_task(request: UpdateTaskRequest):
    """更新任务"""
    with KanbanDB() as db:
        success = db.update_task(
            task_id=request.task_id,
            title=request.title,
            description=request.description,
            priority=request.priority,
            assignee_id=request.assignee_id,
            due_date=request.due_date
        )
        if success:
            task = db.get_task(request.task_id)
            return {"status": "success", "task": task}
    raise HTTPException(status_code=404, detail="Task not found or no changes made")


@app.post("/tools/move_task")
def move_task(request: MoveTaskRequest):
    """移动任务到另一列"""
    with KanbanDB() as db:
        success = db.move_task(
            task_id=request.task_id,
            target_column_id=request.target_column_id,
            position=request.position
        )
        if success:
            task = db.get_task(request.task_id)
            return {"status": "success", "task": task}
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tools/delete_task/{task_id}")
def delete_task(task_id: int):
    """删除任务"""
    with KanbanDB() as db:
        success = db.delete_task(task_id)
    if success:
        return {"status": "success", "message": f"Task {task_id} deleted"}
    raise HTTPException(status_code=404, detail="Task not found")


@app.post("/tools/search_tasks")
def search_tasks(request: SearchTasksRequest):
    """搜索任务"""
    with KanbanDB() as db:
        tasks = db.search_tasks(query=request.query, board_id=request.board_id)
    return {"tasks": tasks, "count": len(tasks)}


# ==================== Label Tools ====================

@app.get("/tools/list_labels/{board_id}")
def list_labels(board_id: int):
    """列出看板的所有标签"""
    with KanbanDB() as db:
        labels = db.list_labels(board_id)
    return {"labels": labels}


@app.get("/tools/get_task_labels/{task_id}")
def get_task_labels(task_id: int):
    """获取任务的标签"""
    with KanbanDB() as db:
        labels = db.get_task_labels(task_id)
    return {"labels": labels}


@app.post("/tools/add_label_to_task")
def add_label_to_task(request: AddLabelRequest):
    """给任务添加标签"""
    with KanbanDB() as db:
        success = db.add_label_to_task(request.task_id, request.label_id)
    if success:
        return {"status": "success"}
    return {"status": "failed", "message": "Label already exists or invalid IDs"}


@app.delete("/tools/remove_label_from_task/{task_id}/{label_id}")
def remove_label_from_task(task_id: int, label_id: int):
    """移除任务标签"""
    with KanbanDB() as db:
        success = db.remove_label_from_task(task_id, label_id)
    if success:
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Label not found on task")


# ==================== Comment Tools ====================

@app.get("/tools/list_comments/{task_id}")
def list_comments(task_id: int):
    """列出任务的评论"""
    with KanbanDB() as db:
        comments = db.list_comments(task_id)
    return {"comments": comments}


@app.post("/tools/add_comment")
def add_comment(request: AddCommentRequest):
    """添加评论"""
    with KanbanDB() as db:
        comment_id = db.add_comment(
            task_id=request.task_id,
            user_id=request.user_id,
            content=request.content
        )
    return {"status": "success", "comment_id": comment_id}


# ==================== User Tools ====================

@app.get("/tools/list_users")
def list_users():
    """列出所有用户"""
    with KanbanDB() as db:
        users = db.list_users()
    return {"users": users}


@app.get("/tools/get_user/{user_id}")
def get_user(user_id: int):
    """获取用户信息"""
    with KanbanDB() as db:
        user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": user}


# ==================== Dify Tool Schema ====================

@app.get("/openapi_for_dify")
def get_dify_tool_schema():
    """
    返回 Dify 可用的工具描述
    可以直接导入到 Dify 的自定义工具中
    """
    tools = [
        {
            "name": "list_boards",
            "description": "列出所有看板项目",
            "parameters": {}
        },
        {
            "name": "get_board_overview",
            "description": "获取看板的完整概览，包含所有列和任务",
            "parameters": {
                "board_id": {"type": "integer", "description": "看板ID", "required": True}
            }
        },
        {
            "name": "list_tasks",
            "description": "列出任务，可按列或负责人筛选",
            "parameters": {
                "column_id": {"type": "integer", "description": "列ID（可选）"},
                "assignee_id": {"type": "integer", "description": "负责人ID（可选）"}
            }
        },
        {
            "name": "create_task",
            "description": "创建新任务",
            "parameters": {
                "column_id": {"type": "integer", "description": "目标列ID", "required": True},
                "title": {"type": "string", "description": "任务标题", "required": True},
                "description": {"type": "string", "description": "任务描述"},
                "priority": {"type": "string", "description": "优先级: low/medium/high/urgent", "default": "medium"},
                "assignee_id": {"type": "integer", "description": "负责人ID"},
                "due_date": {"type": "string", "description": "截止日期 YYYY-MM-DD"}
            }
        },
        {
            "name": "update_task",
            "description": "更新任务信息",
            "parameters": {
                "task_id": {"type": "integer", "description": "任务ID", "required": True},
                "title": {"type": "string", "description": "新标题"},
                "description": {"type": "string", "description": "新描述"},
                "priority": {"type": "string", "description": "新优先级"},
                "assignee_id": {"type": "integer", "description": "新负责人ID"},
                "due_date": {"type": "string", "description": "新截止日期"}
            }
        },
        {
            "name": "move_task",
            "description": "将任务移动到另一个列（如从待办移到进行中）",
            "parameters": {
                "task_id": {"type": "integer", "description": "任务ID", "required": True},
                "target_column_id": {"type": "integer", "description": "目标列ID", "required": True}
            }
        },
        {
            "name": "delete_task",
            "description": "删除任务",
            "parameters": {
                "task_id": {"type": "integer", "description": "任务ID", "required": True}
            }
        },
        {
            "name": "search_tasks",
            "description": "搜索任务（按标题或描述）",
            "parameters": {
                "query": {"type": "string", "description": "搜索关键词", "required": True},
                "board_id": {"type": "integer", "description": "限定在某个看板内搜索"}
            }
        },
        {
            "name": "list_users",
            "description": "列出所有用户，用于查找负责人ID",
            "parameters": {}
        }
    ]
    return {"tools": tools}


if __name__ == "__main__":
    # 确保数据库存在
    if not DB_PATH.exists():
        with KanbanDB(DB_PATH) as db:
            db.init_db()
        print(f"Database initialized at {DB_PATH}")

    print("Starting Kanban Tools API Server...")
    print("API docs: http://localhost:8000/docs")
    print("Dify tool schema: http://localhost:8000/openapi_for_dify")
    uvicorn.run(app, host="0.0.0.0", port=8000)
