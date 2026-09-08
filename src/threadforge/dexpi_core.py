"""DEXPI 1.3 core enrichment: component subtypes, loops, breaks, branches."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Optional

from threadforge.graph import TopologyGraph
from threadforge.models import Discipline, EngineeringAttributes, Tag


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _attr(el: ET.Element, name: str, default: str = "") -> str:
    return el.attrib.get(name, default)


def _text(el: Optional[ET.Element], default: str = "") -> str:
    if el is None or el.text is None:
        return default
    return el.text.strip()


def _opt_float(el: ET.Element, *names: str) -> Optional[float]:
    for name in names:
        raw = _attr(el, name)
        if raw not in ("", None):
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def _findall_local(root: ET.Element, name: str) -> list[ET.Element]:
    return [el for el in root.iter() if _local(el.tag) == name]


def _collect_generic_attributes(el: ET.Element) -> dict[str, str]:
    generics: dict[str, str] = {}
    nodes = [el]
    nodes.extend(c for c in el if _local(c.tag) == "GenericAttributes")
    for node in nodes:
        if _local(node.tag) == "GenericAttributes":
            candidates = list(node)
        elif _local(node.tag) == "GenericAttribute":
            candidates = [node]
        else:
            candidates = [c for c in node if _local(c.tag) == "GenericAttribute"]
            for ga_parent in node:
                if _local(ga_parent.tag) == "GenericAttributes":
                    candidates.extend(list(ga_parent))
        for ga in candidates:
            if _local(ga.tag) != "GenericAttribute":
                continue
            n = _attr(ga, "Name")
            v = _attr(ga, "Value") or _text(ga)
            if n:
                generics[n] = v or ""
    return generics


def _ga_first(generics: dict[str, str], *names: str) -> Optional[str]:
    for n in names:
        if n in generics and generics[n] not in ("", None):
            return generics[n]
    return None


def _apply_tagname(generics: dict[str, str], fallback: str) -> str:
    tag = _ga_first(generics, "TagNameAssignmentClass", "TagName")
    if tag:
        return tag
    prefix = _ga_first(generics, "TagNamePrefixAssignmentClass") or ""
    seq = _ga_first(generics, "TagNameSequenceNumberAssignmentClass") or ""
    suffix = _ga_first(generics, "TagNameSuffixAssignmentClass") or ""
    return f"{prefix}{seq}{suffix}" or fallback


def _association_targets(el: ET.Element) -> list[str]:
    out: list[str] = []
    for child in el:
        if _local(child.tag) == "Association":
            item = _attr(child, "ItemID") or _attr(child, "ItemId")
            if item:
                out.append(item)
    return out

TEE_CLASSES = {"PIPETEE", "TEE", "TTYPECONNECTION"}
CROSS_CLASSES = {"PIPECROSS", "CROSS"}
BREAK_PROPERTY = {"PROPERTYBREAK", "PIPINGPROPERTYBREAK"}
BREAK_SPEC = {"SPECBREAK", "PIPINGSPECBREAK", "SPECIFICATIONBREAK"}
SIGNAL_CLASSES = {
    "SIGNALLINE",
    "SIGNALCONVEYINGFUNCTION",
    "MEASURINGLINEFUNCTION",
    "INFORMATIONFLOW",
}
INLINE_CLASSES = {
    "INLINECOMPONENT",
    "PIPEREDUCER",
    "FLANGE",
    "BLINDFLANGE",
    "PIPEFITTING",
    "RESTRICTIONORIFICE",
}


def _in_shape_catalogue(el: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    cur = parents.get(el)
    while cur is not None:
        if _local(cur.tag) == "ShapeCatalogue":
            return True
        cur = parents.get(cur)
    return False


def _norm(raw: str) -> str:
    return (raw or "").replace(" ", "").replace("_", "").upper()


def _location_xyz(el: ET.Element) -> Optional[tuple[float, float, float]]:
    for pos in el:
        if _local(pos.tag) != "Position":
            continue
        for loc in pos:
            if _local(loc.tag) != "Location":
                continue
            x = _opt_float(loc, "X", "x")
            y = _opt_float(loc, "Y", "y")
            if x is None or y is None:
                continue
            z = _opt_float(loc, "Z", "z")
            return (x, y, z if z is not None else 0.0)
    return None


def _process_nodes(el: ET.Element) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    index = 0
    for cp in el:
        if _local(cp.tag) != "ConnectionPoints":
            continue
        for node in cp:
            if _local(node.tag) != "Node":
                continue
            index += 1
            ntype = (_attr(node, "Type") or "").lower()
            if ntype and ntype != "process":
                continue
            nid = _attr(node, "ID") or f"node-{index}"
            xyz = _location_xyz(node)
            nodes.append({"id": nid, "index": index, "xyz": xyz})
    return nodes


def _segment_parent_id(el: ET.Element, parents: dict[ET.Element, ET.Element]) -> Optional[str]:
    cur = parents.get(el)
    while cur is not None:
        loc = _local(cur.tag)
        if loc == "PipingNetworkSegment":
            return _attr(cur, "ID") or None
        cur = parents.get(cur)
    return None


def enrich_dexpi_core(
    root: ET.Element,
    graph: TopologyGraph,
    parents: dict[ET.Element, ET.Element],
) -> None:
    """Populate 1.3 core collections. Does not change A02 C01 entity counts."""
    insulation = 0
    tracing = 0

    for el in _findall_local(root, "PipingComponent") + _findall_local(root, "InlineComponent"):
        if _in_shape_catalogue(el, parents):
            continue
        cid = _attr(el, "ID") or _attr(el, "Tag")
        if not cid:
            continue
        cls = _attr(el, "ComponentClass") or _local(el.tag)
        ga = _collect_generic_attributes(el)
        rec = {
            "id": cid,
            "component_class": cls,
            "tag": _apply_tagname(ga, _attr(el, "TagName") or cid),
            "generics": ga,
            "segment_id": _segment_parent_id(el, parents),
            "xyz": _location_xyz(el),
            "nodes": _process_nodes(el),
            "associations": _association_targets(el),
        }
        graph.piping_components[cid] = rec
        nrm = _norm(cls)
        if nrm in INLINE_CLASSES or _local(el.tag) == "InlineComponent" or _norm(cid) in INLINE_CLASSES:
            graph.inline_components[cid] = rec
        if nrm in BREAK_PROPERTY:
            graph.property_breaks[cid] = rec
        if nrm in BREAK_SPEC:
            graph.spec_breaks[cid] = rec
        if cid not in graph.tags:
            graph.add_tag(
                Tag(
                    id=cid,
                    name=str(rec["tag"]),
                    discipline=Discipline.PIP,
                    engineering=EngineeringAttributes(component_class=cls),
                    metadata={"role": "piping_component", "generics": ga, "xyz": rec["xyz"]},
                )
            )

    for loc_name, bucket, default_cls in (
        ("PropertyBreak", graph.property_breaks, "PropertyBreak"),
        ("PipingPropertyBreak", graph.property_breaks, "PropertyBreak"),
        ("SpecBreak", graph.spec_breaks, "SpecBreak"),
        ("PipingSpecBreak", graph.spec_breaks, "SpecBreak"),
    ):
        for el in _findall_local(root, loc_name):
            if _in_shape_catalogue(el, parents):
                continue
            bid = _attr(el, "ID") or _attr(el, "TagName") or loc_name
            if bid in bucket:
                continue
            ga = _collect_generic_attributes(el)
            bucket[bid] = {
                "id": bid,
                "component_class": _attr(el, "ComponentClass") or default_cls,
                "generics": ga,
                "segment_id": _segment_parent_id(el, parents),
                "xyz": _location_xyz(el),
            }

    for el in _findall_local(root, "ActuatingSystem"):
        aid = _attr(el, "ID")
        if not aid:
            continue
        ga = _collect_generic_attributes(el)
        graph.actuating_systems[aid] = {
            "id": aid,
            "component_class": _attr(el, "ComponentClass") or "ActuatingSystem",
            "tag": _apply_tagname(ga, _attr(el, "TagName") or aid),
            "generics": ga,
            "components": [
                _attr(c, "ID")
                for c in el
                if _local(c.tag) == "ActuatingSystemComponent" and _attr(c, "ID")
            ],
            "associations": _association_targets(el),
        }

    for loc_name in ("InstrumentationLoopFunction", "InstrumentationLoop"):
        for el in _findall_local(root, loc_name):
            lid = _attr(el, "ID")
            if not lid:
                continue
            ga = _collect_generic_attributes(el)
            graph.instrumentation_loops[lid] = {
                "id": lid,
                "component_class": _attr(el, "ComponentClass") or loc_name,
                "number": _ga_first(ga, "InstrumentationLoopFunctionNumberAssignmentClass") or lid,
                "generics": ga,
            }

    for loc_name in ("InformationFlow", "SignalLine", "SignalConveyingFunction", "MeasuringLineFunction"):
        for el in _findall_local(root, loc_name):
            if _in_shape_catalogue(el, parents):
                continue
            sid = _attr(el, "ID")
            if not sid:
                continue
            ga = _collect_generic_attributes(el)
            cls = _attr(el, "ComponentClass") or loc_name
            graph.signal_lines[sid] = {
                "id": sid,
                "component_class": cls,
                "generics": ga,
                "connections": [
                    {"from": _attr(c, "FromID"), "to": _attr(c, "ToID")}
                    for c in el
                    if _local(c.tag) == "Connection"
                ],
            }

    # Insulation / tracing GenericAttributes on systems, segments, and components
    for loc_name in ("PipingNetworkSystem", "PipingNetworkSegment", "PipingComponent"):
        for el in _findall_local(root, loc_name):
            if _in_shape_catalogue(el, parents):
                continue
            ga = _collect_generic_attributes(el)
            if _ga_first(ga, "InsulationTypeAssignmentClass", "InsulationThickness", "InsulationType"):
                insulation += 1
            if _ga_first(ga, "HeatTracingTypeRepresentationAssignmentClass", "HeatTracingType", "TracingType"):
                tracing += 1

    for pipe in graph.pipelines.values():
        ga = (pipe.metadata or {}).get("generics") or {}
        if pipe.metadata.get("insulation") or _ga_first(
            ga, "InsulationTypeAssignmentClass", "InsulationThickness"
        ):
            pipe.metadata["insulation_type"] = pipe.metadata.get("insulation") or _ga_first(
                ga, "InsulationTypeAssignmentClass", "InsulationType"
            )
            pipe.metadata["insulation_thickness"] = _ga_first(ga, "InsulationThickness")
        if _ga_first(ga, "HeatTracingTypeRepresentationAssignmentClass", "HeatTracingType"):
            pipe.metadata["tracing"] = _ga_first(
                ga, "HeatTracingTypeRepresentationAssignmentClass", "HeatTracingType"
            )

    graph.metadata["insulation_count"] = insulation
    graph.metadata["tracing_count"] = tracing
    build_branch_topology(graph, root)


def build_branch_topology(graph: TopologyGraph, root: ET.Element) -> None:
    """Tees/crosses become branched-graph junctions; branch arms recorded."""
    connections: list[dict[str, str]] = []
    for conn in _findall_local(root, "Connection"):
        fid = _attr(conn, "FromID")
        tid = _attr(conn, "ToID")
        if not fid and not tid:
            continue
        connections.append(
            {
                "from": fid,
                "to": tid,
                "from_node": _attr(conn, "FromNode"),
                "to_node": _attr(conn, "ToNode"),
            }
        )

    fittings: list[tuple[str, str, dict[str, Any]]] = []
    for cid, rec in graph.piping_components.items():
        nrm = _norm(str(rec.get("component_class") or cid))
        if nrm in TEE_CLASSES or "PIPETEE" in nrm:
            fittings.append((cid, "tee", rec))
        elif nrm in CROSS_CLASSES or "PIPECROSS" in nrm:
            fittings.append((cid, "cross", rec))

    branch_arms = 0
    for cid, kind, rec in fittings:
        stubs: list[dict[str, Any]] = []
        nodes = list(rec.get("nodes") or [])
        process_nodes = [n for n in nodes if n.get("xyz") or n.get("index")]
        for i, node in enumerate(process_nodes, start=1):
            role = "run"
            if kind == "tee" and i >= 3:
                role = "branch"
            if kind == "cross" and i >= 3:
                role = "branch"
            connected: list[str] = []
            idx = str(node.get("index") or i)
            for edge in connections:
                if edge["from"] == cid and (not edge["from_node"] or edge["from_node"] == idx) and edge["to"]:
                    connected.append(edge["to"])
                if edge["to"] == cid and (not edge["to_node"] or edge["to_node"] == idx) and edge["from"]:
                    connected.append(edge["from"])
            stub = {
                "node": idx,
                "role": role,
                "xyz": node.get("xyz") or rec.get("xyz"),
                "connected_to": connected,
            }
            stubs.append(stub)
            if role == "branch" and connected:
                branch_arms += 1
        # Secondary segments whose from/to is this fitting also count as branch arms
        xyz = rec.get("xyz") or (stubs[0]["xyz"] if stubs else None)
        graph.branches[cid] = {
            "id": cid,
            "kind": kind,
            "xyz": xyz,
            "stubs": stubs,
            "degree": 3 if kind == "tee" else 4,
        }

    # Pipelines that touch a tee/cross inherit branch metadata
    for pipe in graph.pipelines.values():
        for end in (pipe.from_tag, pipe.to_tag):
            if end and end in graph.branches:
                br = graph.branches[end]
                pipe.metadata["branch_fitting"] = end
                pipe.metadata["branch_kind"] = br["kind"]
                # Secondary specialization or connection on a branch stub → branch route
                spec = str((pipe.metadata.get("generics") or {}).get(
                    "PrimarySecondaryPipingNetworkSegmentSpecialization"
                ) or "")
                stub_role = None
                for stub in br["stubs"]:
                    if pipe.from_tag in (stub.get("connected_to") or []) or pipe.to_tag in (
                        stub.get("connected_to") or []
                    ):
                        stub_role = stub.get("role")
                    if stub.get("role") == "branch" and (
                        pipe.from_tag == end or pipe.to_tag == end
                    ):
                        # prefer the stub whose node matches Connection on this segment
                        pass
                if "Secondary" in spec or stub_role == "branch" or (
                    pipe.from_tag == end or pipe.to_tag == end
                ):
                    if "Secondary" in spec:
                        pipe.metadata["branch_route"] = True
                        pipe.metadata["branch_start"] = end

    secondary_arms = sum(1 for p in graph.pipelines.values() if p.metadata.get("branch_route"))
    graph.metadata["branch_count"] = secondary_arms if secondary_arms else branch_arms
    graph.metadata["tee_count"] = sum(1 for b in graph.branches.values() if b["kind"] == "tee")
    graph.metadata["cross_count"] = sum(1 for b in graph.branches.values() if b["kind"] == "cross")
