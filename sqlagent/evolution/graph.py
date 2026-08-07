from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from sqlagent.db import QuerySafetyError, validate_read_only
from sqlagent.llm import LLMUnavailable, OllamaClient
from sqlagent.trajectories import read_trajectories
from sqlagent.workspace import Workspace


class EvolutionState(TypedDict, total=False):
    workspace_path: str
    trajectories: list[dict[str, Any]]
    clusters: list[dict[str, Any]]
    surface: str
    candidate_id: str
    branch: str
    changed_files: list[str]
    reason: str


MAX_MUTATION_FILES = 3
ALLOWED_WRITE_PREFIXES = ("templates/", "relationships/", "experience/")
ALLOWED_WRITE_FILES = {"manifest.yaml", "SKILL.md"}


def _dangerous_tables(workspace: Workspace) -> list[str]:
    data = workspace.read_yaml("relationships/dangerous_joins.yaml", default={}) or {}
    tables = set()
    for join in data.get("joins", []):
        for side in (join.get("right"), join.get("left")):
            if side and "." in str(side):
                tables.add(str(side).split(".", 1)[0])
    return sorted(tables)


def _cluster(state: EvolutionState, *, workspace: Workspace) -> dict[str, Any]:
    trajectories = state.get("trajectories", [])
    failed = [item for item in trajectories if item.get("error") or not (item.get("invariants") or {}).get("passed", True)]
    dangerous = _dangerous_tables(workspace)
    fanout_pattern = re.compile(r"\b(" + "|".join(re.escape(table) for table in dangerous) + r")\b", re.I) if dangerous else None
    fanout = [item for item in trajectories if fanout_pattern and fanout_pattern.search(item.get("sql") or "")]
    slow = [item for item in trajectories if float((item.get("result") or {}).get("elapsed_ms", 0) or 0) > 500]
    return {"clusters": [{"kind": "join_fanout", "count": len(fanout)}, {"kind": "failed", "count": len(failed)}, {"kind": "slow", "count": len(slow)}]}


def _attribute(state: EvolutionState) -> dict[str, Any]:
    clusters = {item["kind"]: item["count"] for item in state.get("clusters", [])}
    if clusters.get("join_fanout", 0):
        return {"surface": "joins", "reason": "trajectory references a known one-to-many relation"}
    if clusters.get("failed", 0):
        return {"surface": "experience", "reason": "failed trajectory needs a reusable correction"}
    if clusters.get("slow", 0):
        return {"surface": "templates", "reason": "slow trajectory needs a query-shape improvement"}
    return {"surface": "router", "reason": "no failures; add a routing hint for the next batch"}


def _valid_mutation_path(path: str) -> bool:
    return path in ALLOWED_WRITE_FILES or path.startswith(ALLOWED_WRITE_PREFIXES)


def _fallback_mutation(workspace: Workspace, surface: str) -> list[str]:
    changed: list[str] = []
    if surface == "joins":
        path = "relationships/learned_rules.yaml"
        rules = workspace.read_yaml(path, default={"rules": []}) or {"rules": []}
        rule = "preaggregate known one-to-many relations before joining coarser-grain measures"
        if not any(item.get("rule") == rule for item in rules.setdefault("rules", [])):
            rules["rules"].append({"rule": rule, "source": "trajectory", "confidence": 1.0})
            workspace.write_yaml(path, rules)
            changed.append(path)
    elif surface == "templates":
        workspace.write_text("templates/evolution_notes.md", "Use indexed date predicates and preaggregate one-to-many relations before coarse-grain sums.\n")
        changed.append("templates/evolution_notes.md")
    elif surface == "experience":
        workspace.write_text("experience/learned_failure_rules.yaml", "rules:\n  - avoid_unbounded_one_to_many_joins: true\n")
        changed.append("experience/learned_failure_rules.yaml")
    else:
        manifest = workspace.read_manifest()
        hint = "load relationships/dangerous_joins.yaml for metrics on fanout-prone tables"
        if hint not in manifest.setdefault("router_hints", []):
            manifest["router_hints"].append(hint)
            workspace.write_yaml("manifest.yaml", manifest)
            changed.append("manifest.yaml")
    return changed


def _llm_mutation(workspace: Workspace, state: EvolutionState, llm: OllamaClient) -> list[str]:
    trajectories = state.get("trajectories", [])[-10:]
    brief = [
        {
            "question": item.get("question"),
            "sql": item.get("sql"),
            "error": item.get("error"),
            "critic": item.get("critic"),
            "react_attempts": (item.get("react") or {}).get("attempts", 0),
            "elapsed_ms": (item.get("result") or {}).get("elapsed_ms"),
        }
        for item in trajectories
    ]
    context = {
        "clusters": state.get("clusters", []),
        "target_surface": state["surface"],
        "trajectories": brief,
        "dangerous_joins": (workspace.read_yaml("relationships/dangerous_joins.yaml", default={}) or {}).get("joins", []),
        "templates": workspace.read_manifest().get("templates", {}),
    }
    answer = llm.chat_json(
        "You improve your own SQL skill workspace from query trajectories. Propose one small mutation on "
        f"the '{state['surface']}' surface: at most {MAX_MUTATION_FILES} files. Allowed paths: files under "
        "templates/, relationships/, experience/, or manifest.yaml / SKILL.md. Template files must be a single "
        "read-only PostgreSQL SELECT/WITH. Return JSON "
        '{"files": [{"path": "...", "content": "..."}], "reason": "short rationale"}.',
        json.dumps(context, ensure_ascii=False, default=str),
    )
    files = answer.get("files") or []
    if not files or len(files) > MAX_MUTATION_FILES:
        raise ValueError("mutation must touch between 1 and 3 files")
    changed: list[str] = []
    for item in files:
        path = str(item.get("path") or "")
        content = str(item.get("content") or "")
        if not _valid_mutation_path(path) or not content:
            raise ValueError(f"mutation path is not allowed: {path}")
        if path.endswith(".sql"):
            content = validate_read_only(content) + ";\n"
        workspace.write_text(path, content)
        changed.append(path)
    if "manifest.yaml" in changed:
        # The model may serialize manifest templates as a list; restore the canonical shape.
        workspace.write_yaml("manifest.yaml", workspace.read_manifest())
    return changed


def _mutate(state: EvolutionState, *, llm: OllamaClient | None = None) -> dict[str, Any]:
    workspace = Workspace(Path(state["workspace_path"]))
    candidate_id = state.get("candidate_id") or uuid.uuid4().hex[:10]
    branch = workspace.create_candidate(candidate_id)
    surface = state["surface"]
    reason = state["reason"]
    changed: list[str] = []
    if llm:
        try:
            changed = _llm_mutation(workspace, state, llm)
        except (LLMUnavailable, ValueError, QuerySafetyError, KeyError, TypeError):
            changed = []
    if not changed:
        changed = _fallback_mutation(workspace, surface)
    workspace.write_json(f"experience/evolution_{candidate_id}.json", {"surface": surface, "reason": reason, "changed_files": changed})
    changed.append(f"experience/evolution_{candidate_id}.json")
    workspace.commit(f"evolution: mutate {surface} ({candidate_id})")
    return {"candidate_id": candidate_id, "branch": branch, "changed_files": changed}


def run_evolution(workspace: Workspace, min_trajectories: int = 1, llm: OllamaClient | None = None) -> dict[str, Any]:
    workspace.ensure_git()
    trajectory_path = workspace.root / "experience" / "trajectories.jsonl"
    trajectories = read_trajectories(trajectory_path)
    if len(trajectories) < min_trajectories:
        return {"status": "insufficient_trajectories", "count": len(trajectories), "required": min_trajectories}

    def cluster(state: EvolutionState) -> dict[str, Any]:
        return _cluster(state, workspace=workspace)

    def mutate(state: EvolutionState) -> dict[str, Any]:
        return _mutate(state, llm=llm)

    graph = StateGraph(EvolutionState)
    graph.add_node("cluster", cluster)
    graph.add_node("attribute", _attribute)
    graph.add_node("mutate", mutate)
    graph.add_edge(START, "cluster")
    graph.add_edge("cluster", "attribute")
    graph.add_edge("attribute", "mutate")
    graph.add_edge("mutate", END)
    result = graph.compile().invoke({"workspace_path": str(workspace.root), "trajectories": trajectories})
    return {"status": "candidate_created", **{key: value for key, value in result.items() if key != "trajectories"}}
