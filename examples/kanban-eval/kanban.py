#!/usr/bin/env python3
"""
Kanban Board CRUD Operations
用于 AI Agent 评估的项目管理看板操作脚本
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


DB_PATH = Path(__file__).parent / "kanban.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


@dataclass
class Task:
    id: int
    column_id: int
    title: str
    description: Optional[str]
    priority: str
    assignee_id: Optional[int]
    due_date: Optional[str]
    position: int
    created_at: str
    updated_at: str


class KanbanDB:
    """看板数据库操作类"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def init_db(self):
        """初始化数据库，执行 schema.sql"""
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())
        self.conn.commit()

    # ==================== Users ====================
    def create_user(self, username: str, email: str) -> int:
        """创建用户"""
        cursor = self.conn.execute(
            "INSERT INTO users (username, email) VALUES (?, ?)",
            (username, email)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_user(self, user_id: int) -> Optional[dict]:
        """获取用户信息"""
        cursor = self.conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict]:
        """列出所有用户"""
        cursor = self.conn.execute("SELECT * FROM users")
        return [dict(row) for row in cursor.fetchall()]

    # ==================== Boards ====================
    def create_board(self, name: str, owner_id: int, description: str = None) -> int:
        """创建看板"""
        cursor = self.conn.execute(
            "INSERT INTO boards (name, description, owner_id) VALUES (?, ?, ?)",
            (name, description, owner_id)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_board(self, board_id: int) -> Optional[dict]:
        """获取看板信息"""
        cursor = self.conn.execute(
            "SELECT * FROM boards WHERE id = ?", (board_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_boards(self, owner_id: int = None) -> list[dict]:
        """列出看板"""
        if owner_id:
            cursor = self.conn.execute(
                "SELECT * FROM boards WHERE owner_id = ?", (owner_id,)
            )
        else:
            cursor = self.conn.execute("SELECT * FROM boards")
        return [dict(row) for row in cursor.fetchall()]

    def update_board(self, board_id: int, name: str = None, description: str = None) -> bool:
        """更新看板"""
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if not updates:
            return False
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(board_id)
        self.conn.execute(
            f"UPDATE boards SET {', '.join(updates)} WHERE id = ?",
            params
        )
        self.conn.commit()
        return self.conn.total_changes > 0

    def delete_board(self, board_id: int) -> bool:
        """删除看板（级联删除列和任务）"""
        self.conn.execute("DELETE FROM boards WHERE id = ?", (board_id,))
        self.conn.commit()
        return self.conn.total_changes > 0

    # ==================== Columns ====================
    def create_column(self, board_id: int, name: str, position: int = None) -> int:
        """创建列"""
        if position is None:
            cursor = self.conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM columns WHERE board_id = ?",
                (board_id,)
            )
            position = cursor.fetchone()[0]
        cursor = self.conn.execute(
            "INSERT INTO columns (board_id, name, position) VALUES (?, ?, ?)",
            (board_id, name, position)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_column(self, column_id: int) -> Optional[dict]:
        """获取列信息"""
        cursor = self.conn.execute(
            "SELECT * FROM columns WHERE id = ?", (column_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_columns(self, board_id: int) -> list[dict]:
        """列出看板的所有列（按位置排序）"""
        cursor = self.conn.execute(
            "SELECT * FROM columns WHERE board_id = ? ORDER BY position",
            (board_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def update_column(self, column_id: int, name: str = None, position: int = None) -> bool:
        """更新列"""
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if position is not None:
            updates.append("position = ?")
            params.append(position)
        if not updates:
            return False
        params.append(column_id)
        self.conn.execute(
            f"UPDATE columns SET {', '.join(updates)} WHERE id = ?",
            params
        )
        self.conn.commit()
        return self.conn.total_changes > 0

    def delete_column(self, column_id: int) -> bool:
        """删除列（级联删除任务）"""
        self.conn.execute("DELETE FROM columns WHERE id = ?", (column_id,))
        self.conn.commit()
        return self.conn.total_changes > 0

    # ==================== Tasks ====================
    def create_task(
        self,
        column_id: int,
        title: str,
        description: str = None,
        priority: str = "medium",
        assignee_id: int = None,
        due_date: str = None,
        position: int = None
    ) -> int:
        """创建任务"""
        if position is None:
            cursor = self.conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM tasks WHERE column_id = ?",
                (column_id,)
            )
            position = cursor.fetchone()[0]
        cursor = self.conn.execute(
            """INSERT INTO tasks
               (column_id, title, description, priority, assignee_id, due_date, position)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (column_id, title, description, priority, assignee_id, due_date, position)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_task(self, task_id: int) -> Optional[dict]:
        """获取任务详情"""
        cursor = self.conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_tasks(self, column_id: int = None, assignee_id: int = None) -> list[dict]:
        """列出任务"""
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if column_id is not None:
            query += " AND column_id = ?"
            params.append(column_id)
        if assignee_id is not None:
            query += " AND assignee_id = ?"
            params.append(assignee_id)
        query += " ORDER BY position"
        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def update_task(
        self,
        task_id: int,
        title: str = None,
        description: str = None,
        priority: str = None,
        assignee_id: int = None,
        due_date: str = None,
        column_id: int = None,
        position: int = None
    ) -> bool:
        """更新任务"""
        updates = []
        params = []
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if priority is not None:
            updates.append("priority = ?")
            params.append(priority)
        if assignee_id is not None:
            updates.append("assignee_id = ?")
            params.append(assignee_id)
        if due_date is not None:
            updates.append("due_date = ?")
            params.append(due_date)
        if column_id is not None:
            updates.append("column_id = ?")
            params.append(column_id)
        if position is not None:
            updates.append("position = ?")
            params.append(position)
        if not updates:
            return False
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(task_id)
        self.conn.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?",
            params
        )
        self.conn.commit()
        return self.conn.total_changes > 0

    def move_task(self, task_id: int, target_column_id: int, position: int = None) -> bool:
        """移动任务到另一列"""
        if position is None:
            cursor = self.conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM tasks WHERE column_id = ?",
                (target_column_id,)
            )
            position = cursor.fetchone()[0]
        return self.update_task(task_id, column_id=target_column_id, position=position)

    def delete_task(self, task_id: int) -> bool:
        """删除任务"""
        self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.conn.commit()
        return self.conn.total_changes > 0

    # ==================== Labels ====================
    def create_label(self, board_id: int, name: str, color: str = "#808080") -> int:
        """创建标签"""
        cursor = self.conn.execute(
            "INSERT INTO labels (board_id, name, color) VALUES (?, ?, ?)",
            (board_id, name, color)
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_labels(self, board_id: int) -> list[dict]:
        """列出看板的所有标签"""
        cursor = self.conn.execute(
            "SELECT * FROM labels WHERE board_id = ?", (board_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def add_label_to_task(self, task_id: int, label_id: int) -> bool:
        """给任务添加标签"""
        try:
            self.conn.execute(
                "INSERT INTO task_labels (task_id, label_id) VALUES (?, ?)",
                (task_id, label_id)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_label_from_task(self, task_id: int, label_id: int) -> bool:
        """移除任务标签"""
        self.conn.execute(
            "DELETE FROM task_labels WHERE task_id = ? AND label_id = ?",
            (task_id, label_id)
        )
        self.conn.commit()
        return self.conn.total_changes > 0

    def get_task_labels(self, task_id: int) -> list[dict]:
        """获取任务的所有标签"""
        cursor = self.conn.execute(
            """SELECT l.* FROM labels l
               JOIN task_labels tl ON l.id = tl.label_id
               WHERE tl.task_id = ?""",
            (task_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    # ==================== Comments ====================
    def add_comment(self, task_id: int, user_id: int, content: str) -> int:
        """添加评论"""
        cursor = self.conn.execute(
            "INSERT INTO comments (task_id, user_id, content) VALUES (?, ?, ?)",
            (task_id, user_id, content)
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_comments(self, task_id: int) -> list[dict]:
        """列出任务的所有评论"""
        cursor = self.conn.execute(
            """SELECT c.*, u.username
               FROM comments c
               JOIN users u ON c.user_id = u.id
               WHERE c.task_id = ?
               ORDER BY c.created_at""",
            (task_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def delete_comment(self, comment_id: int) -> bool:
        """删除评论"""
        self.conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        self.conn.commit()
        return self.conn.total_changes > 0

    # ==================== 查询辅助方法 ====================
    def get_board_overview(self, board_id: int) -> dict:
        """获取看板概览（包含所有列和任务）"""
        board = self.get_board(board_id)
        if not board:
            return None
        columns = self.list_columns(board_id)
        for col in columns:
            col["tasks"] = self.list_tasks(column_id=col["id"])
        board["columns"] = columns
        board["labels"] = self.list_labels(board_id)
        return board

    def get_task_details(self, task_id: int) -> Optional[dict]:
        """获取任务完整详情（含标签和评论）"""
        task = self.get_task(task_id)
        if not task:
            return None
        task["labels"] = self.get_task_labels(task_id)
        task["comments"] = self.list_comments(task_id)
        if task["assignee_id"]:
            task["assignee"] = self.get_user(task["assignee_id"])
        return task

    def search_tasks(self, query: str, board_id: int = None) -> list[dict]:
        """搜索任务"""
        sql = """SELECT t.*, c.name as column_name, b.name as board_name
                 FROM tasks t
                 JOIN columns c ON t.column_id = c.id
                 JOIN boards b ON c.board_id = b.id
                 WHERE (t.title LIKE ? OR t.description LIKE ?)"""
        params = [f"%{query}%", f"%{query}%"]
        if board_id:
            sql += " AND b.id = ?"
            params.append(board_id)
        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def init_database():
    """初始化数据库并插入示例数据"""
    db_path = DB_PATH
    if db_path.exists():
        db_path.unlink()
    with KanbanDB(db_path) as db:
        db.init_db()
    print(f"数据库已初始化: {db_path}")


def demo():
    """演示 CRUD 操作"""
    print("=" * 50)
    print("Kanban Board CRUD Demo")
    print("=" * 50)

    with KanbanDB() as db:
        # 列出所有看板
        print("\n📋 所有看板:")
        for board in db.list_boards():
            print(f"  - [{board['id']}] {board['name']}: {board['description']}")

        # 获取看板概览
        print("\n📊 看板 1 概览:")
        overview = db.get_board_overview(1)
        if overview:
            print(f"  看板: {overview['name']}")
            for col in overview["columns"]:
                print(f"  \n  📁 {col['name']} ({len(col['tasks'])} 任务):")
                for task in col["tasks"]:
                    priority_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "urgent": "🔴"}
                    print(f"    {priority_emoji.get(task['priority'], '⚪')} [{task['id']}] {task['title']}")

        # 创建新任务
        print("\n✨ 创建新任务...")
        new_task_id = db.create_task(
            column_id=1,
            title="测试新功能",
            description="这是一个通过脚本创建的测试任务",
            priority="high",
            assignee_id=2
        )
        print(f"  创建成功，任务ID: {new_task_id}")

        # 移动任务
        print("\n🔄 移动任务到'进行中'列...")
        db.move_task(new_task_id, target_column_id=2)
        task = db.get_task(new_task_id)
        print(f"  任务现在在列 ID: {task['column_id']}")

        # 添加标签
        print("\n🏷️ 添加标签...")
        db.add_label_to_task(new_task_id, label_id=2)  # feature 标签
        labels = db.get_task_labels(new_task_id)
        print(f"  任务标签: {[l['name'] for l in labels]}")

        # 添加评论
        print("\n💬 添加评论...")
        comment_id = db.add_comment(new_task_id, user_id=1, content="这个功能很重要!")
        comments = db.list_comments(new_task_id)
        print(f"  评论数: {len(comments)}")
        for c in comments:
            print(f"    - {c['username']}: {c['content']}")

        # 搜索任务
        print("\n🔍 搜索任务 '登录'...")
        results = db.search_tasks("登录")
        for r in results:
            print(f"  - [{r['id']}] {r['title']} (看板: {r['board_name']}, 列: {r['column_name']})")

        # 删除测试任务
        print("\n🗑️ 清理测试任务...")
        db.delete_task(new_task_id)
        print(f"  已删除任务 {new_task_id}")

    print("\n" + "=" * 50)
    print("Demo 完成!")
    print("=" * 50)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_database()
    else:
        # 如果数据库不存在，先初始化
        if not DB_PATH.exists():
            init_database()
        demo()
