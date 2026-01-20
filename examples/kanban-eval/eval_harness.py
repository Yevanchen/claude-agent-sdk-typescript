#!/usr/bin/env python3
"""
Kanban Agent Evaluation Harness
评估框架：运行测试任务、调用 Agent、评分
"""

import yaml
import sqlite3
import requests
import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


# ==================== Configuration ====================

TOOLS_API_URL = "http://localhost:8000"
DIFY_API_URL = "http://localhost/v1"  # Dify API 地址
DIFY_API_KEY = ""  # 需要配置
DIFY_WORKFLOW_ID = ""  # 需要配置

DB_PATH = Path(__file__).parent / "kanban.db"
TASKS_FILE = Path(__file__).parent / "eval_tasks.yaml"
RESULTS_DIR = Path(__file__).parent / "eval_results"


@dataclass
class GraderResult:
    """评分结果"""
    grader_type: str
    description: str
    passed: bool
    score: float  # 0.0 - 1.0
    details: str = ""


@dataclass
class TrialResult:
    """单次试验结果"""
    task_id: str
    trial_num: int
    success: bool
    score: float
    grader_results: list[GraderResult]
    transcript: list[dict] = field(default_factory=list)
    agent_response: str = ""
    duration_seconds: float = 0
    error: Optional[str] = None


@dataclass
class TaskResult:
    """任务评估结果"""
    task_id: str
    task_name: str
    trials: list[TrialResult]
    pass_at_k: bool  # 至少一次成功
    pass_pow_k: bool  # 全部成功
    avg_score: float


# ==================== Graders ====================

class Graders:
    """评分器集合"""

    @staticmethod
    def state_check(sql: str, expect: dict, db_path: Path = DB_PATH) -> GraderResult:
        """
        检查数据库状态
        expect: {"column_name": expected_value} 或 {"column_name": ">0"}
        """
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql)
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return GraderResult(
                grader_type="state_check",
                description=f"SQL: {sql[:50]}...",
                passed=False,
                score=0.0,
                details="No rows returned"
            )

        row_dict = dict(row)
        all_passed = True
        details = []

        for key, expected in expect.items():
            actual = row_dict.get(key)

            # 处理比较操作符
            if isinstance(expected, str):
                if expected.startswith(">"):
                    threshold = int(expected[1:])
                    passed = actual is not None and actual > threshold
                elif expected.startswith("<"):
                    threshold = int(expected[1:])
                    passed = actual is not None and actual < threshold
                elif expected.startswith(">="):
                    threshold = int(expected[2:])
                    passed = actual is not None and actual >= threshold
                elif expected.startswith("<="):
                    threshold = int(expected[2:])
                    passed = actual is not None and actual <= threshold
                else:
                    passed = str(actual) == expected
            else:
                passed = actual == expected

            if not passed:
                all_passed = False
            details.append(f"{key}: expected={expected}, actual={actual}, passed={passed}")

        return GraderResult(
            grader_type="state_check",
            description=f"State check: {list(expect.keys())}",
            passed=all_passed,
            score=1.0 if all_passed else 0.0,
            details="; ".join(details)
        )

    @staticmethod
    def tool_calls(transcript: list[dict], required_tools: list[str]) -> GraderResult:
        """
        检查 Agent 是否调用了必要的工具
        transcript: Agent 的执行记录，包含 tool_calls
        """
        called_tools = set()
        for entry in transcript:
            if "tool" in entry:
                called_tools.add(entry["tool"])
            if "tool_calls" in entry:
                for tc in entry["tool_calls"]:
                    called_tools.add(tc.get("name", tc.get("tool", "")))

        required_set = set(required_tools)
        missing = required_set - called_tools

        if missing:
            return GraderResult(
                grader_type="tool_calls",
                description=f"Required tools: {required_tools}",
                passed=False,
                score=len(called_tools & required_set) / len(required_set) if required_set else 1.0,
                details=f"Missing tools: {missing}, Called: {called_tools}"
            )

        return GraderResult(
            grader_type="tool_calls",
            description=f"Required tools: {required_tools}",
            passed=True,
            score=1.0,
            details=f"All required tools called: {called_tools}"
        )

    @staticmethod
    def response_contains(response: str, contains: list[str]) -> GraderResult:
        """检查响应是否包含指定内容"""
        found = []
        missing = []
        for item in contains:
            if item.lower() in response.lower():
                found.append(item)
            else:
                missing.append(item)

        score = len(found) / len(contains) if contains else 1.0
        passed = len(missing) == 0

        return GraderResult(
            grader_type="response_contains",
            description=f"Response should contain: {contains}",
            passed=passed,
            score=score,
            details=f"Found: {found}, Missing: {missing}"
        )

    @staticmethod
    def llm_rubric(response: str, rubric: str, min_score: int = 6) -> GraderResult:
        """
        使用 LLM 评分（需要实现 LLM 调用）
        这里提供一个简化版本，实际使用时应调用 LLM API
        """
        # TODO: 实现实际的 LLM 调用
        # 这里返回一个占位结果
        return GraderResult(
            grader_type="llm_rubric",
            description=f"LLM rubric evaluation (min_score={min_score})",
            passed=True,  # 占位
            score=0.8,  # 占位
            details="LLM grading not implemented - placeholder result"
        )


# ==================== Eval Harness ====================

class EvalHarness:
    """评估框架主类"""

    def __init__(
        self,
        tools_api_url: str = TOOLS_API_URL,
        dify_api_url: str = DIFY_API_URL,
        dify_api_key: str = DIFY_API_KEY
    ):
        self.tools_api_url = tools_api_url
        self.dify_api_url = dify_api_url
        self.dify_api_key = dify_api_key
        self.tasks = []
        self.results = []

    def load_tasks(self, tasks_file: Path = TASKS_FILE):
        """加载评估任务"""
        with open(tasks_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.tasks = data.get("tasks", [])
        self.config = data.get("config", {})
        print(f"Loaded {len(self.tasks)} tasks")

    def reset_database(self):
        """重置数据库到初始状态"""
        try:
            resp = requests.post(f"{self.tools_api_url}/admin/reset_database")
            resp.raise_for_status()
            return True
        except Exception as e:
            print(f"Failed to reset database: {e}")
            return False

    def call_dify_agent(self, prompt: str) -> tuple[str, list[dict]]:
        """
        调用 Dify Workflow
        返回: (response_text, transcript)
        """
        if not self.dify_api_key:
            # 模拟模式：直接返回空结果
            return self._simulate_agent(prompt)

        try:
            headers = {
                "Authorization": f"Bearer {self.dify_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "inputs": {"task": prompt},
                "response_mode": "blocking",
                "user": "eval-harness"
            }
            resp = requests.post(
                f"{self.dify_api_url}/workflows/{DIFY_WORKFLOW_ID}/run",
                headers=headers,
                json=payload,
                timeout=60
            )
            resp.raise_for_status()
            data = resp.json()

            response_text = data.get("data", {}).get("outputs", {}).get("result", "")
            transcript = data.get("data", {}).get("steps", [])

            return response_text, transcript

        except Exception as e:
            print(f"Dify API error: {e}")
            return f"Error: {e}", []

    def _simulate_agent(self, prompt: str) -> tuple[str, list[dict]]:
        """
        模拟 Agent 行为（用于测试 eval harness）
        实际使用时应该调用真实的 Dify API
        """
        transcript = []
        response = ""

        # 简单模拟：根据 prompt 关键词调用相应 API
        if "列出" in prompt and "看板" in prompt:
            resp = requests.get(f"{self.tools_api_url}/tools/list_boards")
            data = resp.json()
            transcript.append({"tool": "list_boards", "result": data})
            response = f"系统中有以下看板：\n"
            for b in data.get("boards", []):
                response += f"- {b['name']}: {b['description']}\n"

        elif "查看" in prompt and "看板" in prompt:
            resp = requests.get(f"{self.tools_api_url}/tools/get_board_overview/1")
            data = resp.json()
            transcript.append({"tool": "get_board_overview", "result": data})
            board = data.get("board", {})
            response = f"看板 {board.get('name')} 的任务情况：\n"
            for col in board.get("columns", []):
                response += f"- {col['name']}: {len(col.get('tasks', []))} 个任务\n"

        elif "创建" in prompt and "任务" in prompt:
            # 解析任务信息
            title_match = re.search(r'标题[是为：:]+[「""]?([^」"""\n]+)', prompt)
            title = title_match.group(1) if title_match else "新任务"

            priority = "medium"
            if "紧急" in prompt or "urgent" in prompt:
                priority = "urgent"
            elif "高" in prompt or "high" in prompt:
                priority = "high"

            payload = {
                "column_id": 1,  # 默认待办列
                "title": title,
                "priority": priority
            }

            # 检查负责人
            if "bob" in prompt.lower():
                payload["assignee_id"] = 2
            elif "charlie" in prompt.lower():
                payload["assignee_id"] = 3
            elif "alice" in prompt.lower():
                payload["assignee_id"] = 1

            resp = requests.post(f"{self.tools_api_url}/tools/create_task", json=payload)
            data = resp.json()
            transcript.append({"tool": "create_task", "params": payload, "result": data})
            response = f"已创建任务：{title}"

        elif "移动" in prompt:
            # 简单实现：移动任务
            if "用户登录" in prompt:
                task_id = 1
            else:
                task_id = 1  # 默认

            target_column = 2  # 默认进行中
            if "进行中" in prompt:
                target_column = 2
            elif "评审" in prompt:
                target_column = 3
            elif "完成" in prompt:
                target_column = 4

            payload = {"task_id": task_id, "target_column_id": target_column}
            resp = requests.post(f"{self.tools_api_url}/tools/move_task", json=payload)
            data = resp.json()
            transcript.append({"tool": "move_task", "params": payload, "result": data})
            response = f"已移动任务 {task_id} 到列 {target_column}"

        elif "搜索" in prompt:
            query_match = re.search(r'[「""]([^」""]+)[」""]', prompt)
            query = query_match.group(1) if query_match else "API"

            resp = requests.post(
                f"{self.tools_api_url}/tools/search_tasks",
                json={"query": query}
            )
            data = resp.json()
            transcript.append({"tool": "search_tasks", "result": data})
            response = f"搜索 '{query}' 找到 {data.get('count', 0)} 个任务"

        else:
            response = "无法理解任务要求"

        return response, transcript

    def run_graders(
        self,
        graders_config: list[dict],
        response: str,
        transcript: list[dict]
    ) -> list[GraderResult]:
        """运行所有评分器"""
        results = []

        for grader in graders_config:
            grader_type = grader.get("type")

            if grader_type == "state_check":
                result = Graders.state_check(
                    sql=grader["sql"],
                    expect=grader["expect"]
                )
            elif grader_type == "tool_calls":
                result = Graders.tool_calls(
                    transcript=transcript,
                    required_tools=grader.get("required_tools", [])
                )
            elif grader_type == "response_contains":
                result = Graders.response_contains(
                    response=response,
                    contains=grader.get("contains", [])
                )
            elif grader_type == "llm_rubric":
                result = Graders.llm_rubric(
                    response=response,
                    rubric=grader.get("rubric", ""),
                    min_score=grader.get("min_score", 6)
                )
            else:
                result = GraderResult(
                    grader_type=grader_type,
                    description=f"Unknown grader type: {grader_type}",
                    passed=False,
                    score=0.0,
                    details="Grader not implemented"
                )

            result.description = grader.get("description", result.description)
            results.append(result)

        return results

    def run_trial(self, task: dict, trial_num: int) -> TrialResult:
        """运行单次试验"""
        task_id = task["id"]
        prompt = task["prompt"]
        graders_config = task.get("graders", [])

        # 重置数据库
        if self.config.get("reset_db_between_trials", True):
            self.reset_database()

        # 运行 Agent
        start_time = datetime.now()
        try:
            response, transcript = self.call_dify_agent(prompt)
        except Exception as e:
            return TrialResult(
                task_id=task_id,
                trial_num=trial_num,
                success=False,
                score=0.0,
                grader_results=[],
                error=str(e),
                duration_seconds=0
            )
        duration = (datetime.now() - start_time).total_seconds()

        # 运行评分器
        grader_results = self.run_graders(graders_config, response, transcript)

        # 计算总分
        if grader_results:
            avg_score = sum(g.score for g in grader_results) / len(grader_results)
            all_passed = all(g.passed for g in grader_results)
        else:
            avg_score = 1.0
            all_passed = True

        return TrialResult(
            task_id=task_id,
            trial_num=trial_num,
            success=all_passed,
            score=avg_score,
            grader_results=grader_results,
            transcript=transcript,
            agent_response=response,
            duration_seconds=duration
        )

    def run_task(self, task: dict, num_trials: int = None) -> TaskResult:
        """运行单个任务的所有试验"""
        if num_trials is None:
            num_trials = self.config.get("trials_per_task", 3)

        task_id = task["id"]
        task_name = task.get("name", task_id)
        trials = []

        print(f"\n{'='*50}")
        print(f"Task: {task_name} ({task_id})")
        print(f"{'='*50}")

        for trial_num in range(num_trials):
            print(f"\n  Trial {trial_num + 1}/{num_trials}...")
            result = self.run_trial(task, trial_num)
            trials.append(result)

            status = "✓ PASS" if result.success else "✗ FAIL"
            print(f"  {status} (score: {result.score:.2f})")

            for gr in result.grader_results:
                gr_status = "✓" if gr.passed else "✗"
                print(f"    {gr_status} {gr.grader_type}: {gr.description}")

        # 计算 pass@k 和 pass^k
        pass_at_k = any(t.success for t in trials)
        pass_pow_k = all(t.success for t in trials)
        avg_score = sum(t.score for t in trials) / len(trials) if trials else 0.0

        print(f"\n  Summary: pass@{num_trials}={pass_at_k}, pass^{num_trials}={pass_pow_k}, avg_score={avg_score:.2f}")

        return TaskResult(
            task_id=task_id,
            task_name=task_name,
            trials=trials,
            pass_at_k=pass_at_k,
            pass_pow_k=pass_pow_k,
            avg_score=avg_score
        )

    def run_all(self, task_filter: list[str] = None, num_trials: int = None):
        """运行所有任务（或指定任务）"""
        results = []
        tasks_to_run = self.tasks

        if task_filter:
            tasks_to_run = [t for t in self.tasks if t["id"] in task_filter]

        print(f"\n{'#'*60}")
        print(f"# Running {len(tasks_to_run)} tasks")
        print(f"{'#'*60}")

        for task in tasks_to_run:
            result = self.run_task(task, num_trials)
            results.append(result)

        self.results = results
        self._print_summary()
        return results

    def _print_summary(self):
        """打印评估总结"""
        print(f"\n{'#'*60}")
        print("# EVALUATION SUMMARY")
        print(f"{'#'*60}\n")

        total_tasks = len(self.results)
        passed_tasks = sum(1 for r in self.results if r.pass_at_k)
        perfect_tasks = sum(1 for r in self.results if r.pass_pow_k)
        avg_score = sum(r.avg_score for r in self.results) / total_tasks if total_tasks else 0

        print(f"Total tasks:     {total_tasks}")
        print(f"pass@k:          {passed_tasks}/{total_tasks} ({passed_tasks/total_tasks*100:.1f}%)")
        print(f"pass^k:          {perfect_tasks}/{total_tasks} ({perfect_tasks/total_tasks*100:.1f}%)")
        print(f"Average score:   {avg_score:.2f}")

        print(f"\n{'Task':<30} {'pass@k':<10} {'pass^k':<10} {'avg_score':<10}")
        print("-" * 60)
        for r in self.results:
            print(f"{r.task_name:<30} {'✓' if r.pass_at_k else '✗':<10} {'✓' if r.pass_pow_k else '✗':<10} {r.avg_score:.2f}")

    def save_results(self, output_dir: Path = RESULTS_DIR):
        """保存评估结果"""
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"eval_results_{timestamp}.json"

        data = {
            "timestamp": timestamp,
            "config": self.config,
            "summary": {
                "total_tasks": len(self.results),
                "pass_at_k": sum(1 for r in self.results if r.pass_at_k),
                "pass_pow_k": sum(1 for r in self.results if r.pass_pow_k),
                "avg_score": sum(r.avg_score for r in self.results) / len(self.results) if self.results else 0
            },
            "results": [
                {
                    "task_id": r.task_id,
                    "task_name": r.task_name,
                    "pass_at_k": r.pass_at_k,
                    "pass_pow_k": r.pass_pow_k,
                    "avg_score": r.avg_score,
                    "trials": [
                        {
                            "trial_num": t.trial_num,
                            "success": t.success,
                            "score": t.score,
                            "duration_seconds": t.duration_seconds,
                            "agent_response": t.agent_response,
                            "grader_results": [
                                {
                                    "type": g.grader_type,
                                    "description": g.description,
                                    "passed": g.passed,
                                    "score": g.score,
                                    "details": g.details
                                }
                                for g in t.grader_results
                            ]
                        }
                        for t in r.trials
                    ]
                }
                for r in self.results
            ]
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\nResults saved to: {output_file}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Kanban Agent Evaluation Harness")
    parser.add_argument("--tasks", nargs="*", help="Specific task IDs to run")
    parser.add_argument("--trials", type=int, default=1, help="Number of trials per task")
    parser.add_argument("--save", action="store_true", help="Save results to file")
    args = parser.parse_args()

    harness = EvalHarness()
    harness.load_tasks()

    harness.run_all(task_filter=args.tasks, num_trials=args.trials)

    if args.save:
        harness.save_results()


if __name__ == "__main__":
    main()
