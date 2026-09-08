"""Spec-break validation — material / rating consistency across each edge.

A declared SpecBreak records an intentional class/material change.
A mismatch without a SpecBreak is a ``spec_break_violation``.
Crafted 150# into 300# (no SpecBreak) must report that violation.
"""

from __future__ import annotations

from typing import Any, Optional

from threadforge.graph import TopologyGraph
from threadforge.models import Discipline, Equipment, FromTo, Nozzle, Pipeline, Tag


def parse_rating(value: Optional[object]) -> Optional[int]:
    if value in (None, ""):
        return None
    s = str(value).upper().replace("#", "").replace("CL", "").replace("CLASS", "").replace("LB", "")
    s = s.replace("ANSI", "").strip()
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _side_spec(graph: TopologyGraph, node_id: str) -> dict[str, Any]:
    material: Optional[str] = None
    rating: Optional[int] = None
    piping_class: Optional[str] = None
    source = node_id
    pipe = graph.pipelines.get(node_id)
    if pipe is None:
        for p in graph.pipelines.values():
            if node_id in (p.from_tag, p.to_tag) or node_id in p.component_tags:
                pipe = p
                break
    if pipe is not None:
        material = pipe.material
        piping_class = (pipe.metadata or {}).get("PipingClass") or (pipe.metadata or {}).get("spec")
        rating = parse_rating((pipe.metadata or {}).get("flange_class") or (pipe.metadata or {}).get("rating"))
        source = pipe.id
    nz = graph.nozzles.get(node_id)
    if nz is not None:
        if nz.rating:
            rating = parse_rating(nz.rating)
        source = nz.id
    tag = graph.tags.get(node_id)
    if tag is not None:
        extra = tag.engineering.extra or {}
        if extra.get("material"):
            material = str(extra["material"])
        if extra.get("rating") or extra.get("flange_class"):
            rating = parse_rating(extra.get("rating") or extra.get("flange_class"))
        ga = (tag.metadata or {}).get("generics") or {}
        if ga.get("MaterialOfConstructionCodeAssignmentClass"):
            material = str(ga["MaterialOfConstructionCodeAssignmentClass"])
    rec = graph.piping_components.get(node_id) or graph.spec_breaks.get(node_id)
    if rec:
        ga = rec.get("generics") or {}
        if ga.get("PipingClassCodeAssignmentClass"):
            piping_class = str(ga["PipingClassCodeAssignmentClass"])
    return {
        "id": node_id,
        "source": source,
        "material": (material or "").strip() or None,
        "rating": rating,
        "piping_class": (str(piping_class).strip() if piping_class else None),
    }


def _has_spec_break(graph: TopologyGraph, edge: FromTo) -> bool:
    if edge.connection_type in {"spec_break", "property_break"}:
        return True
    if (edge.metadata or {}).get("spec_break"):
        return True
    if edge.from_id in graph.spec_breaks or edge.to_id in graph.spec_breaks:
        return True
    return False


def _mismatch(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if a.get("rating") is not None and b.get("rating") is not None and a["rating"] != b["rating"]:
        reasons.append(f"rating {a['rating']}#->{b['rating']}#")
    ma, mb = a.get("material"), b.get("material")
    if ma and mb and ma != mb:
        reasons.append(f"material {ma}→{mb}")
    ca, cb = a.get("piping_class"), b.get("piping_class")
    if ca and cb and ca != cb:
        reasons.append(f"piping_class {ca}→{cb}")
    return reasons


def validate_spec_breaks(graph: TopologyGraph) -> dict[str, Any]:
    """Compare material/rating/piping_class on every connectivity edge."""
    edges: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    declared: list[dict[str, Any]] = []
    for edge in graph.from_tos.values():
        a = _side_spec(graph, edge.from_id)
        b = _side_spec(graph, edge.to_id)
        reasons = _mismatch(a, b)
        rec = {
            "edge_id": edge.id,
            "from": edge.from_id,
            "to": edge.to_id,
            "via_line": edge.via_line,
            "from_spec": a,
            "to_spec": b,
            "reasons": reasons,
            "declared_spec_break": _has_spec_break(graph, edge),
        }
        if reasons:
            edges.append(rec)
            if rec["declared_spec_break"]:
                declared.append(rec)
            else:
                rec["kind"] = "spec_break_violation"
                violations.append(rec)
    # Adjacent pipeline segments that share a line number but change class
    by_line: dict[str, list[Pipeline]] = {}
    for pipe in graph.pipelines.values():
        by_line.setdefault(pipe.line_number, []).append(pipe)
    for line_no, segs in by_line.items():
        if len(segs) < 2:
            continue
        for i, left in enumerate(segs):
            for right in segs[i + 1 :]:
                a = _side_spec(graph, left.id)
                b = _side_spec(graph, right.id)
                reasons = _mismatch(a, b)
                if not reasons:
                    continue
                # same line, different class — violation unless a SpecBreak sits on either
                declared_break = left.id in graph.spec_breaks or right.id in graph.spec_breaks
                rec = {
                    "edge_id": f"{left.id}->{right.id}",
                    "from": left.id,
                    "to": right.id,
                    "via_line": line_no,
                    "from_spec": a,
                    "to_spec": b,
                    "reasons": reasons,
                    "declared_spec_break": declared_break,
                }
                edges.append(rec)
                if declared_break:
                    declared.append(rec)
                else:
                    rec["kind"] = "spec_break_violation"
                    violations.append(rec)
    return {
        "edge_count": len(graph.from_tos),
        "mismatch_count": len(edges),
        "declared_spec_breaks": len(declared),
        "spec_break_violations": violations,
        "violation_count": len(violations),
        "ok": len(violations) == 0,
    }


def crafted_150_into_300() -> TopologyGraph:
    """Two segments, 150# into 300#, no SpecBreak — must violate."""
    g = TopologyGraph()
    g.equipment["EQ-A"] = Equipment(id="EQ-A", tag="EQ-A", nozzles=["N-A"])
    g.equipment["EQ-B"] = Equipment(id="EQ-B", tag="EQ-B", nozzles=["N-B"])
    g.nozzles["N-A"] = Nozzle(id="N-A", tag="N1", equipment_id="EQ-A", x=0.0, y=0.0, z=5.0, rating="150")
    g.nozzles["N-B"] = Nozzle(id="N-B", tag="N2", equipment_id="EQ-B", x=10.0, y=0.0, z=5.0, rating="300")
    g.tags["N-A"] = Tag(id="N-A", name="N-A", discipline=Discipline.PIP)
    g.tags["N-B"] = Tag(id="N-B", name="N-B", discipline=Discipline.PIP)
    g.pipelines["LINE-150"] = Pipeline(
        id="LINE-150",
        line_number="150-300",
        from_tag="N-A",
        to_tag="N-B",
        nominal_bore='6"',
        material="CS",
        metadata={"flange_class": 150, "rating": "150"},
    )
    g.pipelines["LINE-300"] = Pipeline(
        id="LINE-300",
        line_number="150-300",
        from_tag="N-B",
        to_tag="N-B",
        nominal_bore='6"',
        material="CS",
        metadata={"flange_class": 300, "rating": "300"},
    )
    g.add_from_to(
        FromTo(
            id="FT-150-300",
            from_id="LINE-150",
            to_id="LINE-300",
            via_line="150-300",
            connection_type="pipe",
        )
    )
    return g
