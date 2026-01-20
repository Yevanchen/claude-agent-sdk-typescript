-- Kanban Board Schema for Project Management
-- 用于 AI Agent 评估的项目管理看板数据结构

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 项目/看板表
CREATE TABLE IF NOT EXISTS boards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    owner_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

-- 列/阶段表 (如: To Do, In Progress, Done)
CREATE TABLE IF NOT EXISTS columns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (board_id) REFERENCES boards(id) ON DELETE CASCADE
);

-- 任务/卡片表
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    column_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    priority TEXT CHECK(priority IN ('low', 'medium', 'high', 'urgent')) DEFAULT 'medium',
    assignee_id INTEGER,
    due_date DATE,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (column_id) REFERENCES columns(id) ON DELETE CASCADE,
    FOREIGN KEY (assignee_id) REFERENCES users(id)
);

-- 标签表
CREATE TABLE IF NOT EXISTS labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#808080',
    FOREIGN KEY (board_id) REFERENCES boards(id) ON DELETE CASCADE
);

-- 任务-标签关联表
CREATE TABLE IF NOT EXISTS task_labels (
    task_id INTEGER NOT NULL,
    label_id INTEGER NOT NULL,
    PRIMARY KEY (task_id, label_id),
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (label_id) REFERENCES labels(id) ON DELETE CASCADE
);

-- 评论表
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 插入示例数据
INSERT INTO users (username, email) VALUES
    ('alice', 'alice@example.com'),
    ('bob', 'bob@example.com'),
    ('charlie', 'charlie@example.com');

INSERT INTO boards (name, description, owner_id) VALUES
    ('产品开发', '产品功能开发跟踪', 1),
    ('营销活动', 'Q1营销计划', 2);

INSERT INTO columns (board_id, name, position) VALUES
    (1, '待办', 0),
    (1, '进行中', 1),
    (1, '评审中', 2),
    (1, '已完成', 3),
    (2, 'Ideas', 0),
    (2, 'Planning', 1),
    (2, 'Executing', 2),
    (2, 'Done', 3);

INSERT INTO labels (board_id, name, color) VALUES
    (1, 'bug', '#ff0000'),
    (1, 'feature', '#00ff00'),
    (1, 'urgent', '#ff6600'),
    (2, 'social', '#1da1f2'),
    (2, 'email', '#ea4335');

INSERT INTO tasks (column_id, title, description, priority, assignee_id, due_date, position) VALUES
    (1, '用户登录功能', '实现OAuth2.0登录', 'high', 1, '2026-02-01', 0),
    (1, '数据库优化', '优化查询性能', 'medium', 2, '2026-02-15', 1),
    (2, 'API文档编写', '完善REST API文档', 'low', 1, '2026-01-30', 0),
    (3, '单元测试覆盖', '提升测试覆盖率到80%', 'medium', 3, '2026-02-10', 0),
    (4, '版本1.0发布', '完成1.0版本发布', 'high', 1, '2026-01-15', 0),
    (5, '社交媒体推广方案', '制定Twitter和LinkedIn推广策略', 'medium', 2, NULL, 0),
    (6, '内容日历', '规划2月内容发布', 'low', 2, '2026-01-25', 0);

INSERT INTO task_labels (task_id, label_id) VALUES
    (1, 2),
    (2, 3),
    (3, 2),
    (6, 4);

INSERT INTO comments (task_id, user_id, content) VALUES
    (1, 2, '需要支持Google和GitHub登录'),
    (1, 1, '已添加到需求文档'),
    (2, 3, '建议先分析慢查询日志');
