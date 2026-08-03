from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

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


def _cluster(state: EvolutionState) -> dict[str, Any]:
    trajectories = state.get("trajectories", [])
    failed = [item for item in trajectories if item.get("error") or not (item.get("invariants") or {}).get("passed", True)]
    fanout = [item for item in trajectories if re.search(r"order_(items|payments)", item.get("sql", ""), re.I)]
    slow = [item for item in trajectories if float((item.get("result") or {}).get("elapsed_ms", 0) or 0) > 500]
    return {"clusters": [{"kind": "join_fanout", "count": len(fanout)}, {"kind": "failed", "count": len(failed)}, {"kind": "slow", "count": len(slow)}]}


def _attribute(state: EvolutionState) -> dict[str, Any]:
    clusters = {item["kind"]: item["count"] for item in state.get("clusters", [])}
    if clusters.get("join_fanout", 0):
        return {"surface": "joins", "reason": "trajectory references a one-to-many order relation"}
    if clusters.get("failed", 0):
        return {"surface": "experience", "reason": "failed trajectory needs a reusable correction"}
    if clusters.get("slow", 0):
        return {"surface": "templates", "reason": "slow trajectory needs a query-shape improvement"}
    return {"surface": "router", "reason": "no failures; add a routing hint for the next batch"}


def _mutate(state: EvolutionState) -> dict[str, Any]:
    workspace = Workspace(Path(state["workspace_path"]))
    candidate_id = state.get("candidate_id") or uuid.uuid4().hex[:10]
    branch = workspace.create_candidate(candidate_id)
    surface = state["surface"]
    changed: list[str] = []
    if surface == "joins":
        path = workspace.root / "relationships" / "learned_rules.yaml"
        rules = workspace.read_yaml("relationships/learned_rules.yaml", default={"rules": []}) or {"rules": []}
        rules.setdefault("rules", []).append({"rule": "aggregate order_payments before joining order-grain measures", "source": "trajectory", "confidence": 1.0})
        workspace.write_yaml("relationships/learned_rules.yaml", rules)
        changed.append("relationships/learned_rules.yaml")
        workspace.write_text(
            "templates/payment_revenue.sql",
            """-- candidate template learned from payment-event trajectories\nSELECT date_trunc('month', paid_at)::date AS month,\n       round(sum(amount)::numeric, 2) AS revenue\nFROM order_payments\nWHERE status IN ('captured', 'partial')\nGROUP BY 1 ORDER BY 1;\n""",
        )
        changed.append("templates/payment_revenue.sql")
    elif surface == "templates":
        workspace.write_text("templates/evolution_notes.md", "Use indexed order_date predicates and preaggregate one-to-many relations before order-grain sums.\n")
        changed.append("templates/evolution_notes.md")
    elif surface == "experience":
        workspace.write_text("experience/learned_failure_rules.yaml", "rules:\n  - avoid_unbounded_one_to_many_joins: true\n")
        changed.append("experience/learned_failure_rules.yaml")
    else:
        manifest = workspace.read_yaml("manifest.yaml", default={}) or {}
        manifest.setdefault("router_hints", []).append("load relationships/dangerous_joins.yaml for order metrics")
        workspace.write_yaml("manifest.yaml", manifest)
        changed.append("manifest.yaml")
    workspace.write_json(f"experience/evolution_{candidate_id}.json", {"surface": surface, "reason": state["reason"], "changed_files": changed})
    changed.append(f"experience/evolution_{candidate_id}.json")
    workspace.commit(f"evolution: mutate {surface} ({candidate_id})")
    return {"candidate_id": candidate_id, "branch": branch, "changed_files": changed}


def run_evolution(workspace: Workspace, min_trajectories: int = 1) -> dict[str, Any]:
    workspace.ensure_git()
    trajectory_path = workspace.root / "experience" / "trajectories.jsonl"
    trajectories = read_trajectories(trajectory_path)
    if len(trajectories) < min_trajectories:
        return {"status": "insufficient_trajectories", "count": len(trajectories), "required": min_trajectories}
    graph = StateGraph(EvolutionState)
    graph.add_node("cluster", _cluster)
    graph.add_node("attribute", _attribute)
    graph.add_node("mutate", _mutate)
    graph.add_edge(START, "cluster")
    graph.add_edge("cluster", "attribute")
    graph.add_edge("attribute", "mutate")
    graph.add_edge("mutate", END)
    result = graph.compile().invoke({"workspace_path": str(workspace.root), "trajectories": trajectories})
    return {"status": "candidate_created", **{key: value for key, value in result.items() if key != "trajectories"}}
