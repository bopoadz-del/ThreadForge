"""Proteus/DEXPI-shaped XML parser + synthetic fixture loader.

Parses a simplified DEXPI/Proteus-like XML into TopologyGraph entities.

Supported element families (best-effort, attribute-tolerant):
  Sheet / Drawing, Equipment / ProcessEquipment, Nozzle,
  PipingNetworkSegment / PipeLine / Line (+ Component children),
  Instrument / InstrumentationFunction / ProcessInstrumentFunction,
  BatteryLimit / PlantAreaBoundary, DesignVolume / Volume, System.

WALL — Full DEXPI XSD certification, Proteus schema namespaces, component
catalogues, insulation specs, and vendor-specific attribute dictionaries
are NOT implemented (see WALLS.md).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional, Union

from threadforge.graph import TopologyGraph
from threadforge.models import (
    BatteryLimit,
    DesignVolume,
    Discipline,
    EngineeringAttributes,
    Equipment,
    FromTo,
    IdentityTaxonomy,
    Instrument,
    Nozzle,
    Pipeline,
    Sheet,
    System,
    Tag,
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"

# Documented coverage gaps (also mirrored in WALLS.md)
DEXPI_COVERAGE_GAPS = [
    "Vendor ComponentClass URI dictionaries (AVEVA/Hexagon/Autodesk extensions)",
    "PipingComponent catalogue (full elbow/tee/reducer geometry params)",
    "ActuatingFunction / SignalConveyingFunction (full control-loop semantics)",
    "PropertyBreak / SpecBreak with full material class refs",
    "LabeledComposition / ProcessStream fluid properties",
    "Vendor proprietary extensions (AVEVA / Hexagon / Autodesk)",
]
# Closed vs prior gap list: public XSD 4.1(+4.1.1 RC1) vendored + validate_xsd;
# GenericAttributes mapped (LineNumber/DN/PipingClass/FluidCode/pressure/material/insulation/TagName);
# OffPageConnector / P02 OPC cross-sheet joins; Insulation* GenericAttributes read.


def _text(el: Optional[ET.Element], default: str = "") -> str:
    if el is None or el.text is None:
        return default
    return el.text.strip()


def _attr(el: ET.Element, name: str, default: str = "") -> str:
    return el.attrib.get(name, default)


def _opt_float(el: ET.Element, *names: str) -> Optional[float]:
    for name in names:
        raw = _attr(el, name)
        if raw not in ("", None):
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def _discipline(raw: str) -> Discipline:
    mapping = {
        "PIP": Discipline.PIP,
        "EQ": Discipline.EQP,
        "EQP": Discipline.EQP,
        "INS": Discipline.INS,
        "ELE": Discipline.ELE,
        "TEL": Discipline.TEL,
        "STR": Discipline.STR,
        "CIV": Discipline.CIV,
    }
    return mapping.get((raw or "PIP").upper(), Discipline.PIP)


def _local(tag: str) -> str:
    """Strip XML namespace if present."""
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _findall_local(root: ET.Element, name: str) -> list[ET.Element]:
    """Find all elements by local name (namespace-tolerant)."""
    return [el for el in root.iter() if _local(el.tag) == name]


def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _collect_generic_attributes(el: ET.Element) -> dict[str, str]:
    """Collect GenericAttribute Name→Value from el and direct GenericAttributes children."""
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
            # also nested GenericAttributes block
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


def _map_bore_from_generics(generics: dict[str, str]) -> Optional[str]:
    """DN / NominalDiameter GenericAttributes → bore string (e.g. DN80 or 80)."""
    rep = _ga_first(
        generics,
        "NominalDiameterRepresentationAssignmentClass",
        "NominalDiameter",
    )
    if rep:
        return rep.replace(" ", "")
    num = _ga_first(generics, "NominalDiameterNumericalValueRepresentationAssignmentClass")
    typ = _ga_first(generics, "NominalDiameterTypeRepresentationAssignmentClass") or "DN"
    if num:
        return f"{typ}{num}" if typ.upper() == "DN" else num
    return None


def _map_line_number(generics: dict[str, str], fallback: str) -> str:
    return (
        _ga_first(generics, "LineNumberAssignmentClass", "LineNumber", "SegmentNumberAssignmentClass")
        or fallback
    )


def _apply_tagname(generics: dict[str, str], fallback: str) -> str:
    tag = _ga_first(generics, "TagNameAssignmentClass", "TagName")
    if tag:
        return tag
    prefix = _ga_first(generics, "TagNamePrefixAssignmentClass") or ""
    seq = _ga_first(generics, "TagNameSequenceNumberAssignmentClass") or ""
    suffix = _ga_first(generics, "TagNameSuffixAssignmentClass") or ""
    composed = f"{prefix}{seq}{suffix}"
    return composed or fallback




def _process_node_generics(nz_el: ET.Element) -> dict[str, str]:
    """GenericAttributes on ConnectionPoints/Node[@Type=process]."""
    out: dict[str, str] = {}
    for cp in nz_el:
        if _local(cp.tag) != "ConnectionPoints":
            continue
        for node in cp:
            if _local(node.tag) != "Node":
                continue
            if (_attr(node, "Type") or "").lower() != "process":
                continue
            out.update(_collect_generic_attributes(node))
    return out


def _nozzle_drawing_xy(nz_el: ET.Element) -> Optional[tuple[float, float]]:
    """Position/Location X,Y → drawing coords only (never plant XYZ)."""
    for pos in nz_el:
        if _local(pos.tag) != "Position":
            continue
        for loc in pos:
            if _local(loc.tag) != "Location":
                continue
            x = _opt_float(loc, "X", "x")
            y = _opt_float(loc, "Y", "y")
            if x is not None and y is not None:
                return (x, y)
    return None


def _nozzle_tag_and_size(
    nz_el: ET.Element,
    nz_ga: dict[str, str],
    parent_eq_tag: str,
    nid: str,
) -> tuple[str, Optional[str]]:
    """Tag from TagName+SubTagName when present, else parent-NozzleNumber|ID; size from process node DN."""
    process_ga = _process_node_generics(nz_el)
    size = _map_bore_from_generics(process_ga) or _map_bore_from_generics(nz_ga) or _attr(nz_el, "Size") or None
    tag_name = _ga_first(nz_ga, "TagNameAssignmentClass", "TagName")
    sub = _ga_first(nz_ga, "SubTagNameAssignmentClass", "SubTagName")
    if tag_name and sub:
        tag = f"{tag_name}-{sub}"
    elif tag_name:
        tag = tag_name
    elif sub and parent_eq_tag:
        tag = f"{parent_eq_tag}-{sub}"
    else:
        num = (
            _ga_first(nz_ga, "NozzleNumberAssignmentClass", "NozzleNumber")
            or _attr(nz_el, "NozzleNumber")
            or _attr(nz_el, "Name")
            or nid
        )
        tag = f"{parent_eq_tag}-{num}" if parent_eq_tag else str(num)
    return tag, size


def _association_targets(el: ET.Element) -> list[str]:
    out: list[str] = []
    for child in el:
        if _local(child.tag) == "Association":
            item = _attr(child, "ItemID") or _attr(child, "ItemId")
            if item:
                out.append(item)
    return out

def parse_dexpi_xml(source: Union[str, Path, bytes]) -> TopologyGraph:
    """Parse DEXPI/Proteus-shaped XML into a TopologyGraph."""
    if isinstance(source, bytes):
        root = ET.fromstring(source)
    else:
        path = Path(source)
        tree = ET.parse(path)
        root = tree.getroot()

    graph = TopologyGraph()
    parents = _parent_map(root)
    graph.metadata["source_format"] = _local(root.tag)
    # SchemaVersion from PlantInformation when present
    schema_version = None
    for pi in _findall_local(root, "PlantInformation"):
        schema_version = _attr(pi, "SchemaVersion") or _attr(pi, "schemaVersion") or schema_version
    graph.metadata["schema_version"] = schema_version
    graph.metadata["plant"] = _attr(root, "Name", _attr(root, "name", "plant"))
    graph.metadata["units"] = _attr(root, "Units") or _attr(root, "units") or "unspecified"
    graph.metadata["dexpi_coverage_gaps"] = list(DEXPI_COVERAGE_GAPS)

    # Sheets / Drawings (multi-sheet)
    sheet_els = _findall_local(root, "Sheet") + _findall_local(root, "Drawing")
    # Deduplicate by identity while preserving order
    seen_sheet_ids: set[str] = set()
    ordered_sheets: list[ET.Element] = []
    for sheet_el in sheet_els:
        sid = _attr(sheet_el, "ID") or _attr(sheet_el, "id") or ""
        key = sid or id(sheet_el)
        if key in seen_sheet_ids:
            continue
        seen_sheet_ids.add(str(key))
        ordered_sheets.append(sheet_el)

    total = len(ordered_sheets) or 1
    for i, sheet_el in enumerate(ordered_sheets, start=1):
        sid = _attr(sheet_el, "ID") or _attr(sheet_el, "id") or f"SHEET-{i:03d}"
        name = _attr(sheet_el, "Name") or _attr(sheet_el, "name") or f"Sheet {i}"
        notes = [_text(n) for n in sheet_el if _local(n.tag) == "Note" and _text(n)]
        legend = {
            _attr(el, "Key"): _attr(el, "Value")
            for el in sheet_el
            if _local(el.tag) == "LegendItem"
        }
        layers = [
            _attr(el, "Name") or _text(el)
            for el in sheet_el
            if _local(el.tag) == "Layer"
        ]
        graph.add_sheet(
            Sheet(
                id=sid,
                name=name,
                index=int(_attr(sheet_el, "Index") or i),
                total=total,
                notes=notes,
                legend=legend,
                layers=[x for x in layers if x],
            )
        )

    # Equipment + ProcessEquipment
    eq_els = _findall_local(root, "Equipment") + _findall_local(root, "ProcessEquipment")
    for eq_el in eq_els:
        eid = _attr(eq_el, "ID") or _attr(eq_el, "TagName")
        eq_ga = _collect_generic_attributes(eq_el)
        tag_name = _apply_tagname(eq_ga, _attr(eq_el, "TagName") or _attr(eq_el, "Name") or eid or "")
        if not eid:
            continue
        sheet_id = _attr(eq_el, "SheetID") or None
        disc = _discipline(_attr(eq_el, "Discipline", "EQP"))
        identity = IdentityTaxonomy(
            std_name=_attr(eq_el, "StdName") or tag_name,
            primary_code=_attr(eq_el, "PrimaryCode") or tag_name,
            ccs_base=_attr(eq_el, "CCSBase") or None,
            ccs_type_code=_attr(eq_el, "CCSTypeCode") or None,
            sequence=_attr(eq_el, "Sequence") or None,
        )
        desc = _attr(eq_el, "Description") or _text(
            next((c for c in eq_el if _local(c.tag) == "Description"), None)
        )
        eng = EngineeringAttributes(
            component_class=_attr(eq_el, "ComponentClass") or "EQ",
            equipment_description=desc or None,
            service=_attr(eq_el, "Service") or None,
        )
        bounds = None
        geom = next(
            (c for c in eq_el if _local(c.tag) in ("Extent", "Bounds")),
            None,
        )
        if geom is not None:
            bounds = {
                "xmin": float(_attr(geom, "Xmin", "0")),
                "ymin": float(_attr(geom, "Ymin", "0")),
                "xmax": float(_attr(geom, "Xmax", "0")),
                "ymax": float(_attr(geom, "Ymax", "0")),
            }
        asset_3d = _attr(eq_el, "Asset3D") or _attr(eq_el, "ModelRef") or None
        volume_id = _attr(eq_el, "VolumeID") or None

        tag = Tag(
            id=eid,
            name=tag_name,
            discipline=disc,
            sheet_id=sheet_id,
            identity=identity,
            engineering=eng,
            volume_id=volume_id or None,
            asset_3d_ref=asset_3d,
            geometry_bounds=bounds,
            metadata={"generics": eq_ga},
        )
        graph.add_tag(tag)

        nozzle_ids: list[str] = []
        for nz_el in (c for c in eq_el if _local(c.tag) == "Nozzle"):
            nid = _attr(nz_el, "ID") or f"{eid}-N{_attr(nz_el, 'Name', 'X')}"
            nz_ga = _collect_generic_attributes(nz_el)
            nz_tag, nz_size = _nozzle_tag_and_size(nz_el, nz_ga, tag_name, nid)
            # Plant XYZ only from explicit nozzle attributes — NEVER from drawing Location
            nz = Nozzle(
                id=nid,
                tag=nz_tag,
                equipment_id=eid,
                size=nz_size,
                rating=_attr(nz_el, "Rating") or None,
                facing=_attr(nz_el, "Facing") or None,
                orientation=_attr(nz_el, "Orientation") or None,
                x=_opt_float(nz_el, "X", "x"),
                y=_opt_float(nz_el, "Y", "y"),
                z=_opt_float(nz_el, "Z", "z"),
                drawing_xy=_nozzle_drawing_xy(nz_el),
            )
            graph.add_nozzle(nz)
            locs = _association_targets(nz_el)
            if locs:
                graph.metadata.setdefault("nozzle_located_in", {})[nid] = locs[0]
            nozzle_ids.append(nid)
            if nid not in graph.tags:
                graph.add_tag(
                    Tag(
                        id=nid,
                        name=nz.tag,
                        discipline=Discipline.PIP,
                        sheet_id=sheet_id,
                        volume_id=volume_id or None,
                        metadata={
                            "role": "nozzle",
                            "equipment_id": eid,
                            "xyz": [nz.x, nz.y, nz.z],
                        },
                    )
                )

        graph.add_equipment(
            Equipment(
                id=eid,
                tag=tag_name,
                description=eng.equipment_description,
                identity=identity,
                engineering=eng,
                nozzles=nozzle_ids,
                asset_3d_ref=asset_3d,
                volume_id=volume_id or None,
                sheet_id=sheet_id,
            )
        )

    # Orphan / ShapeCatalogue nozzles — still parented (equipment_id from ancestor or catalogue)
    for nz_el in _findall_local(root, "Nozzle"):
        nid = _attr(nz_el, "ID")
        if not nid or nid in graph.nozzles:
            continue
        # Walk parents for Equipment or ShapeCatalogue
        cur = parents.get(nz_el)
        eq_id = "ShapeCatalogue"
        while cur is not None:
            loc = _local(cur.tag)
            if loc in ("Equipment", "ProcessEquipment"):
                eq_id = _attr(cur, "ID") or eq_id
                break
            if loc == "ShapeCatalogue":
                eq_id = "ShapeCatalogue"
                break
            cur = parents.get(cur)
        nz_ga = _collect_generic_attributes(nz_el)
        parent_tag = graph.equipment[eq_id].tag if eq_id in graph.equipment else ""
        nz_tag, nz_size = _nozzle_tag_and_size(nz_el, nz_ga, parent_tag, nid)
        nz = Nozzle(
            id=nid,
            tag=nz_tag,
            equipment_id=eq_id,
            size=nz_size,
            x=_opt_float(nz_el, "X", "x"),
            y=_opt_float(nz_el, "Y", "y"),
            z=_opt_float(nz_el, "Z", "z"),
            drawing_xy=_nozzle_drawing_xy(nz_el),
        )
        graph.add_nozzle(nz)
        # Do not invent a ShapeCatalogue Equipment node — keep equipment count = XML Equipment.
        if eq_id in graph.equipment and nid not in graph.equipment[eq_id].nozzles:
            graph.equipment[eq_id].nozzles.append(nid)

    # PipingNetworkSystem → inherit LineNumber / bore / class / fluid onto child segments
    system_attrs: dict[str, dict[str, str]] = {}
    for sys_el in _findall_local(root, "PipingNetworkSystem"):
        sid = _attr(sys_el, "ID") or ""
        sga = _collect_generic_attributes(sys_el)
        system_attrs[sid] = sga
        for seg in (c for c in sys_el if _local(c.tag) == "PipingNetworkSegment"):
            seg_id = _attr(seg, "ID")
            if seg_id:
                system_attrs[seg_id] = {**sga, **_collect_generic_attributes(seg)}

    # Off-page connectors as tags (OPC cross-sheet)
    for opc_name in (
        "OffPageConnector",
        "PipeOffPageConnector",
        "FlowInPipeOffPageConnector",
        "FlowOutPipeOffPageConnector",
    ):
        for opc_el in _findall_local(root, opc_name):
            oid = _attr(opc_el, "ID")
            if not oid or oid in graph.tags:
                continue
            opc_ga = _collect_generic_attributes(opc_el)
            graph.add_tag(
                Tag(
                    id=oid,
                    name=_apply_tagname(opc_ga, _attr(opc_el, "TagName") or oid),
                    discipline=Discipline.PIP,
                    engineering=EngineeringAttributes(
                        component_class=_attr(opc_el, "ComponentClass") or opc_name
                    ),
                    metadata={"role": "off_page_connector", "generics": opc_ga},
                )
            )

    # Piping / lines — PipingNetworkSegment, PipeLine, Line
    line_names = ("PipingNetworkSegment", "PipeLine", "Line")
    seen_lines: set[str] = set()
    for lname in line_names:
        for line_el in _findall_local(root, lname):
            lid = _attr(line_el, "ID") or _attr(line_el, "LineNumber")
            if not lid or lid in seen_lines:
                continue
            seen_lines.add(lid)
            # GenericAttributes (DEXPI) — segment + inherited PipingNetworkSystem
            generics = dict(system_attrs.get(lid) or {})
            generics.update(_collect_generic_attributes(line_el))
            line_number = _map_line_number(
                generics,
                _attr(line_el, "LineNumber") or _attr(line_el, "Name") or lid,
            )
            from_tag = _attr(line_el, "From") or _attr(line_el, "FromID") or None
            to_tag = _attr(line_el, "To") or _attr(line_el, "ToID") or None
            # Connection FromID/ToID children
            for conn in (ch for ch in line_el if _local(ch.tag) == "Connection"):
                from_tag = from_tag or _attr(conn, "FromID") or None
                to_tag = to_tag or _attr(conn, "ToID") or None
            components = [
                _attr(c, "ID") or _attr(c, "Tag")
                for c in line_el
                if _local(c.tag) in ("Component", "PipingComponent")
                and (_attr(c, "ID") or _attr(c, "Tag"))
            ]
            for c in (ch for ch in line_el if _local(ch.tag) in ("Component", "PipingComponent")):
                cid = _attr(c, "ID") or _attr(c, "Tag")
                if not cid:
                    continue
                ctype = _attr(c, "Type") or _attr(c, "ComponentClass") or "PIPE"
                if cid not in graph.tags:
                    graph.add_tag(
                        Tag(
                            id=cid,
                            name=_attr(c, "Tag") or cid,
                            discipline=Discipline.PIP,
                            engineering=EngineeringAttributes(
                                component_class=ctype,
                                equipment_description=ctype,
                                service=_attr(line_el, "Service") or None,
                            ),
                            volume_id=_attr(line_el, "VolumeID") or None,
                            metadata={"line_id": lid, "component_type": ctype},
                        )
                    )

            bore = (
                _attr(line_el, "NominalBore")
                or _attr(line_el, "NominalDiameter")
                or _attr(line_el, "NB")
                or _map_bore_from_generics(generics)
            )
            piping_class = (
                _attr(line_el, "Spec")
                or _attr(line_el, "PipingClass")
                or _ga_first(generics, "PipingClassCodeAssignmentClass", "PipingClass")
            )
            fluid = _attr(line_el, "Service") or _ga_first(generics, "FluidCodeAssignmentClass", "FluidCode")
            material = (
                _attr(line_el, "Material")
                or _ga_first(generics, "MaterialOfConstructionCodeAssignmentClass", "Material")
            )
            design_p = _ga_first(
                generics,
                "UpperLimitDesignPressure",
                "LowerLimitDesignPressure",
                "DesignPressure",
            )
            insulation = _ga_first(generics, "InsulationTypeAssignmentClass", "InsulationThickness")
            pipe = Pipeline(
                id=lid,
                line_number=line_number,
                from_tag=from_tag or None,
                to_tag=to_tag or None,
                nominal_bore=bore,
                service=fluid,
                material=material,
                sheet_id=_attr(line_el, "SheetID") or None,
                component_tags=components,
                metadata={
                    "spec": piping_class,
                    "PipingClass": piping_class,
                    "FluidCode": _ga_first(generics, "FluidCodeAssignmentClass", "FluidCode"),
                    "element": lname,
                    "DesignPressure": design_p,
                    "insulation": insulation,
                    "generics": generics,
                },
            )
            graph.add_pipeline(pipe)

            if lid not in graph.tags:
                graph.add_tag(
                    Tag(
                        id=lid,
                        name=line_number,
                        discipline=Discipline.PIP,
                        sheet_id=pipe.sheet_id,
                        engineering=EngineeringAttributes(
                            component_class="LINE",
                            service=pipe.service,
                        ),
                        volume_id=_attr(line_el, "VolumeID") or None,
                        metadata={"role": "pipeline", "spec": pipe.metadata.get("spec")},
                    )
                )

            if from_tag and to_tag:
                matched = from_tag in graph.tags and to_tag in graph.tags
                graph.add_from_to(
                    FromTo(
                        id=f"FT-{lid}",
                        from_id=from_tag,
                        to_id=to_tag,
                        via_line=lid,
                        connection_type="pipe",
                        matched=matched,
                    )
                )

    # Instruments — Instrument, InstrumentationFunction, ProcessInstrumentFunction
    inst_names = ("Instrument", "InstrumentationFunction", "ProcessInstrumentFunction", "ProcessInstrumentationFunction")
    seen_inst: set[str] = set()
    for iname in inst_names:
        for inst_el in _findall_local(root, iname):
            iid = _attr(inst_el, "ID") or _attr(inst_el, "TagName")
            if not iid or iid in seen_inst:
                continue
            seen_inst.add(iid)
            inst_ga = _collect_generic_attributes(inst_el)
            tag_name = _apply_tagname(
                inst_ga, _attr(inst_el, "TagName") or _attr(inst_el, "Name") or iid
            )
            connected = _attr(inst_el, "ConnectedTo") or None
            inst = Instrument(
                id=iid,
                tag=tag_name,
                instrument_type=_attr(inst_el, "Type") or None,
                measured_variable=_attr(inst_el, "MeasuredVariable") or None,
                connected_to=connected,
                sheet_id=_attr(inst_el, "SheetID") or None,
                discipline=Discipline.INS,
            )
            graph.add_instrument(inst)
            if iid not in graph.tags:
                graph.add_tag(
                    Tag(
                        id=iid,
                        name=tag_name,
                        discipline=Discipline.INS,
                        sheet_id=inst.sheet_id,
                        engineering=EngineeringAttributes(
                            component_class=inst.instrument_type or "INS",
                        ),
                        metadata={
                            "connected_to": connected,
                            "element": iname,
                        },
                    )
                )
            if connected:
                graph.add_from_to(
                    FromTo(
                        id=f"FT-INS-{iid}",
                        from_id=iid,
                        to_id=connected,
                        connection_type="instrument",
                        matched=connected in graph.tags,
                    )
                )

    # Top-level / OPC Connection edges (cross-sheet joins)
    for conn in _findall_local(root, "Connection"):
        fid = _attr(conn, "FromID")
        tid = _attr(conn, "ToID")
        if not fid or not tid:
            continue
        cid = f"FT-CONN-{fid}-{tid}"
        if cid in graph.from_tos:
            continue
        graph.add_from_to(
            FromTo(
                id=cid,
                from_id=fid,
                to_id=tid,
                connection_type="connection",
                matched=(fid in graph.tags or fid in graph.nozzles)
                and (tid in graph.tags or tid in graph.nozzles),
            )
        )
    for ref_el in _findall_local(root, "PipeOffPageConnectorReference") + _findall_local(
        root, "OffPageConnectorReference"
    ):
        rid = _attr(ref_el, "ID")
        # Number / referenced connector link via GenericAttributes or attributes
        ref_ga = _collect_generic_attributes(ref_el)
        target = (
            _attr(ref_el, "ReferencedConnectorID")
            or _ga_first(ref_ga, "ReferencedConnectorNumberAssignmentClass", "Number")
        )
        if rid and rid not in graph.tags:
            graph.add_tag(
                Tag(
                    id=rid,
                    name=_apply_tagname(ref_ga, rid),
                    discipline=Discipline.PIP,
                    engineering=EngineeringAttributes(
                        component_class=_attr(ref_el, "ComponentClass") or "OffPageConnectorReference"
                    ),
                    metadata={"role": "opc_reference", "target": target, "generics": ref_ga},
                )
            )

    # Battery limits
    for bl_name in ("BatteryLimit", "PlantAreaBoundary"):
        for bl_el in _findall_local(root, bl_name):
            bid = _attr(bl_el, "ID") or f"BL-{_attr(bl_el, 'TagID')}"
            if bid in graph.battery_limits:
                continue
            tag_id = _attr(bl_el, "TagID") or _attr(bl_el, "Tag") or bid
            graph.add_battery_limit(
                BatteryLimit(
                    id=bid,
                    tag_id=tag_id,
                    description=_attr(bl_el, "Description") or _text(bl_el),
                    side=_attr(bl_el, "Side") or None,
                )
            )

    # Design volumes
    for vol_name in ("DesignVolume", "Volume"):
        for vol_el in _findall_local(root, vol_name):
            vid = _attr(vol_el, "ID")
            if not vid or vid in graph.volumes:
                continue
            graph.add_volume(
                DesignVolume(
                    id=vid,
                    name=_attr(vol_el, "Name") or vid,
                    xmin=float(_attr(vol_el, "Xmin", "0")),
                    ymin=float(_attr(vol_el, "Ymin", "0")),
                    zmin=float(_attr(vol_el, "Zmin", "0")),
                    xmax=float(_attr(vol_el, "Xmax", "10")),
                    ymax=float(_attr(vol_el, "Ymax", "10")),
                    zmax=float(_attr(vol_el, "Zmax", "10")),
                    color=_attr(vol_el, "Color") or None,
                    site=_attr(vol_el, "Site") or None,
                    plot_plan_ref=_attr(vol_el, "PlotPlan") or None,
                )
            )

    # Systems
    for sys_el in _findall_local(root, "System"):
        sid = _attr(sys_el, "ID")
        if not sid:
            continue
        boundary = [
            _attr(t, "ID") or _text(t)
            for t in sys_el
            if _local(t.tag) == "BoundaryTag" and (_attr(t, "ID") or _text(t))
        ]
        graph.add_system(
            System(
                id=sid,
                name=_attr(sys_el, "Name") or sid,
                boundary_tags=boundary,
                service=_attr(sys_el, "Service") or None,
            )
        )

    # DesignPressure on pipelines from segment GAs or connected equipment UpperLimitDesignPressure
    eq_pressure: dict[str, float] = {}
    for eid, eq in graph.equipment.items():
        tag_opt = graph.tags.get(eid)
        ga = ((tag_opt.metadata or {}).get("generics") if tag_opt else {}) or {}
        raw = ga.get("UpperLimitDesignPressure") or ga.get("DesignPressure")
        if raw not in (None, ""):
            try:
                eq_pressure[eid] = float(raw)
            except (TypeError, ValueError):
                pass
    for pipe in graph.pipelines.values():
        ga = (pipe.metadata or {}).get("generics") or {}
        raw = pipe.metadata.get("DesignPressure") or ga.get("UpperLimitDesignPressure") or ga.get("DesignPressure")
        if raw not in (None, ""):
            try:
                pipe.metadata["DesignPressure"] = float(raw)
                continue
            except (TypeError, ValueError):
                pass
        # from connected equipment via nozzle endpoints
        located = graph.metadata.get("nozzle_located_in") or {}
        for endpoint in (pipe.from_tag, pipe.to_tag):
            if not endpoint:
                continue
            nz_opt = graph.nozzles.get(endpoint)
            if nz_opt is not None and nz_opt.equipment_id in eq_pressure:
                pipe.metadata["DesignPressure"] = eq_pressure[nz_opt.equipment_id]
                break
            loc_opt = located.get(endpoint)
            loc = str(loc_opt) if loc_opt else ""
            if loc and loc in eq_pressure:
                pipe.metadata["DesignPressure"] = eq_pressure[loc]
                break
            if endpoint in eq_pressure:
                pipe.metadata["DesignPressure"] = eq_pressure[endpoint]
                break

    # Synthesize systems when none present (for test packs): one per FluidCode
    if not graph.systems:
        by_fluid: dict[str, list[str]] = {}
        for pipe in graph.pipelines.values():
            fluid = pipe.service or (pipe.metadata or {}).get("FluidCode") or "UNCLASSIFIED"
            by_fluid.setdefault(str(fluid), []).append(pipe.id)
        for fluid, lids in by_fluid.items():
            boundary_tags: list[str] = []
            for lid in lids:
                pipe = graph.pipelines[lid]
                if pipe.from_tag:
                    boundary_tags.append(pipe.from_tag)
                if pipe.to_tag:
                    boundary_tags.append(pipe.to_tag)
            sid = f"SYS-{fluid}"
            graph.add_system(
                System(
                    id=sid,
                    name=f"Fluid {fluid}",
                    boundary_tags=sorted(set(boundary_tags)),
                    service=fluid,
                )
            )

    graph.metadata["sheet_ids"] = list(graph.sheets.keys())
    graph.metadata["multi_sheet"] = len(graph.sheets) > 1
    return graph


def load_fixture(name: str = "sample_pid.xml") -> TopologyGraph:
    """Load a fixture XML from fixtures/, fixtures/public/, or dexpi13/pids/."""
    candidates = [
        FIXTURES_DIR / name,
        FIXTURES_DIR / "public" / name,
        FIXTURES_DIR / "public" / "dexpi13" / "pids" / name,
        FIXTURES_DIR / "public" / "dexpi13" / name,
    ]
    for path in candidates:
        if path.exists():
            return parse_dexpi_xml(path)
    raise FileNotFoundError(f"Fixture not found: {name} (searched {candidates})")




def _opc_join_key(tag: Tag) -> Optional[str]:
    """CrossPageConnection / connector number / TagName for OPC pairing."""
    meta = tag.metadata or {}
    ga = meta.get("generics") or {}
    for k in (
        "CrossPageConnectionAssignmentClass",
        "CrossPageConnection",
        "PipeConnectorNumberAssignmentClass",
        "Number",
        "TagNameAssignmentClass",
        "TagName",
    ):
        v = ga.get(k)
        if v:
            return str(v)
    # fall back to tag.name when it looks like a shared connector label
    if tag.name and not tag.name.startswith("Flow"):
        return str(tag.name)
    return None


def join_opc_across_graphs(graph: TopologyGraph) -> int:
    """Join FlowOutPipeOffPageConnector ↔ FlowInPipeOffPageConnector by key.

    Returns number of new FromTo edges created.
    """
    outs: dict[str, list[str]] = {}
    inns: dict[str, list[str]] = {}
    for tid, tag in graph.tags.items():
        cls = (tag.engineering.component_class or "") if tag.engineering else ""
        role = (tag.metadata or {}).get("role")
        if role != "off_page_connector" and "OffPage" not in cls:
            continue
        key = _opc_join_key(tag)
        if not key:
            continue
        if "FlowOut" in cls or "FlowOut" in tid:
            outs.setdefault(key, []).append(tid)
        elif "FlowIn" in cls or "FlowIn" in tid:
            inns.setdefault(key, []).append(tid)
    joins = 0
    for key, out_ids in outs.items():
        in_ids = inns.get(key) or []
        for oid in out_ids:
            for iid in in_ids:
                cid = f"FT-OPC-{oid}-{iid}"
                if cid in graph.from_tos:
                    continue
                # only count cross-file (different source_xml) when annotated
                out_sheet = (graph.tags[oid].metadata or {}).get("source_xml")
                in_sheet = (graph.tags[iid].metadata or {}).get("source_xml")
                cross = bool(out_sheet and in_sheet and out_sheet != in_sheet)
                if not cross and out_sheet is None and in_sheet is None:
                    # still join unmatched pairs within multi-load without per-tag source
                    cross = True
                if not cross:
                    continue
                graph.add_from_to(
                    FromTo(
                        id=cid,
                        from_id=oid,
                        to_id=iid,
                        connection_type="opc_cross_page",
                        matched=True,
                        metadata={"opc_cross_file": True, "join_key": key},
                    )
                )
                joins += 1
    graph.metadata["opc_join_count"] = joins
    return joins


def load_fixtures_multi(paths: list[Union[str, Path]]) -> TopologyGraph:
    """Parse multiple Proteus XML files into one graph; join OPCs across files."""
    merged: Optional[TopologyGraph] = None
    path_list = [Path(p) for p in paths]
    for path in path_list:
        g = parse_dexpi_xml(path)
        # annotate OPC tags with source file
        for tag in g.tags.values():
            if (tag.metadata or {}).get("role") == "off_page_connector":
                tag.metadata["source_xml"] = path.name
        if merged is None:
            merged = g
            continue
        # merge entities (IDs assumed unique across sheets)
        for sid, sheet in g.sheets.items():
            sheet.source_xml = path.name
            merged.add_sheet(sheet)
        for tid, tag in g.tags.items():
            if tid not in merged.tags:
                merged.add_tag(tag)
        for eid, eq in g.equipment.items():
            if eid not in merged.equipment:
                merged.add_equipment(eq)
        for nid, nz in g.nozzles.items():
            if nid not in merged.nozzles:
                merged.add_nozzle(nz)
        for lid, pipe in g.pipelines.items():
            if lid not in merged.pipelines:
                merged.add_pipeline(pipe)
        for iid, inst in g.instruments.items():
            if iid not in merged.instruments:
                merged.instruments[iid] = inst
        for fid, ft in g.from_tos.items():
            if fid not in merged.from_tos:
                merged.add_from_to(ft)
    if merged is None:
        raise FileNotFoundError("load_fixtures_multi: no paths")
    join_opc_across_graphs(merged)
    merged.metadata["source_files"] = [p.name for p in path_list]
    merged.metadata["multi_sheet"] = True
    return merged

def default_fixture_path() -> Path:
    return FIXTURES_DIR / "sample_pid.xml"


def coverage_report() -> dict[str, Any]:
    """Return what we parse vs known DEXPI gaps."""
    supported = [
            "Sheet", "Drawing",
            "Equipment", "ProcessEquipment", "Nozzle",
            "PipingNetworkSegment", "PipeLine", "Line", "Component", "PipingComponent",
            "Connection", "GenericAttributes", "PipingNetworkSystem",
            "OffPageConnector", "PipeOffPageConnector", "PipeOffPageConnectorReference",
            "Instrument", "InstrumentationFunction", "ProcessInstrumentFunction",
            "ProcessInstrumentationFunction",
            "BatteryLimit", "PlantAreaBoundary",
            "DesignVolume", "Volume",
            "System", "BoundaryTag",
        ]
    return {
        "supported_elements": supported,
        "gaps": list(DEXPI_COVERAGE_GAPS),
        "wall": "Vendor DEXPI extensions only — public XSD validation when vendored; see WALLS.md",
        "gap_count": len(DEXPI_COVERAGE_GAPS),
    }


KNOWN_XSD_DELTAS = {
    "4.1_vs_4.1.1_RC1": [
        "4.1.1 RC1 adds/relaxes selected Instrumentation and OPC attribute particles vs 4.1",
        "TrainingTestCases C01 declares Proteus 4.1-compatible content; prefer SchemaVersion match",
    ],
}


def _select_xsd(schema_version: Optional[str] = None) -> Optional[Path]:
    public = FIXTURES_DIR / "public" / "dexpi13" / "xsd"
    if not public.exists():
        public = FIXTURES_DIR / "public"
    candidates = list(public.glob("**/*.xsd"))
    if not candidates:
        return None
    if schema_version and "4.1.1" in schema_version:
        for c in candidates:
            if "4.1.1" in c.name:
                return c
    for c in candidates:
        if c.name.endswith("4.1.xsd") and "4.1.1" not in c.name:
            return c
    return sorted(candidates, key=lambda p: p.name)[0]


def validate_xsd(path: Union[str, Path], xsd_path: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    """Validate XML against a Proteus/DEXPI XSD if vendored.

    SchemaVersion ≥ 4.1.1: try **xmlschema first** (lxml UPA-broken on RC1).
    Else: lxml first, then xmlschema.
    """
    path = Path(path)
    schema_version = None
    try:
        root = ET.parse(path).getroot()
        for pi in _findall_local(root, "PlantInformation"):
            schema_version = _attr(pi, "SchemaVersion") or schema_version
    except Exception:  # noqa: BLE001
        pass
    if xsd_path is None:
        chosen = _select_xsd(schema_version)
        if chosen is None:
            return {
                "ok": False,
                "status": "no_xsd_vendored",
                "message": "No XSD under fixtures/public/dexpi13 — see SOURCES.md / make fetch-fixtures",
            }
        xsd_path = chosen
    xsd_path = Path(xsd_path)

    prefer_xmlschema = bool(schema_version and _schema_version_at_least(schema_version, "4.1.1"))
    # When validating explicitly against 4.1 while document is 4.1.1, surface known deltas.
    xsd_is_41 = "4.1.1" not in xsd_path.name and xsd_path.name.endswith("4.1.xsd")
    known_list = list(KNOWN_XSD_DELTAS["4.1_vs_4.1.1_RC1"])

    def _run_xmlschema() -> dict[str, Any]:
        import xmlschema

        xs = xmlschema.XMLSchema(str(xsd_path), validation="lax")
        errors = list(xs.iter_errors(str(path)))
        ok = len(errors) == 0
        result: dict[str, Any] = {
            "ok": ok,
            "status": "validated" if ok else "invalid",
            "xsd": str(xsd_path),
            "schema_version": schema_version,
            "engine": "xmlschema",
            "known_deltas": known_list if (not ok and xsd_is_41) else (KNOWN_XSD_DELTAS if not ok else []),
            "errors": [str(e) for e in errors[:20]],
        }
        if not ok and xsd_is_41:
            result["known_deltas"] = known_list
        return result

    def _run_lxml() -> dict[str, Any]:
        from lxml import etree

        schema = etree.XMLSchema(etree.parse(str(xsd_path)))
        doc = etree.parse(str(path))
        ok = bool(schema.validate(doc))
        result = {
            "ok": ok,
            "status": "validated" if ok else "invalid",
            "xsd": str(xsd_path),
            "schema_version": schema_version,
            "engine": "lxml",
            "known_deltas": known_list if (not ok and xsd_is_41) else (KNOWN_XSD_DELTAS if not ok else []),
            "errors": [str(e) for e in schema.error_log][:20] if not ok else [],
        }
        if not ok and xsd_is_41:
            result["known_deltas"] = known_list
        return result

    engines = [_run_xmlschema, _run_lxml] if prefer_xmlschema else [_run_lxml, _run_xmlschema]
    lxml_err: Optional[str] = None
    xmlschema_err: Optional[str] = None
    last: Optional[dict[str, Any]] = None
    for eng in engines:
        try:
            last = eng()
            # Prefer a decisive validated/invalid over UPA blow-ups
            if last.get("status") in ("validated", "invalid"):
                return last
        except ImportError as exc:
            msg = str(exc)
            if "xmlschema" in eng.__name__ or "xmlschema" in msg.lower():
                xmlschema_err = "xmlschema not installed"
            else:
                lxml_err = "lxml not installed"
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "xmlschema" in eng.__name__ or eng is _run_xmlschema:
                xmlschema_err = msg
            else:
                lxml_err = msg
            if any(s in msg for s in ("not determinist", "Unique Particle Attribution", "UPA")):
                continue

    combined = (lxml_err or "") + "\n" + (xmlschema_err or "")
    if any(s in combined for s in ("not determinist", "Unique Particle Attribution", "UPA")):
        return {
            "ok": False,
            "status": "xsd_non_deterministic",
            "xsd": str(xsd_path),
            "schema_version": schema_version,
            "known_deltas": known_list,
            "message": (
                "Vendored Proteus XSD hits UPA/non-deterministic content model under "
                "lxml/xmlschema; schema is present for SchemaVersion gating."
            ),
            "lxml_error": lxml_err,
            "xmlschema_error": xmlschema_err,
        }
    if (lxml_err == "lxml not installed") and (xmlschema_err == "xmlschema not installed"):
        return {
            "ok": False,
            "status": "lxml_missing",
            "message": "pip install threadforge[xsd] (lxml + xmlschema)",
            "lxml_error": lxml_err,
        }
    if last is not None:
        return last
    return {
        "ok": False,
        "status": "error",
        "xsd": str(xsd_path),
        "message": xmlschema_err or lxml_err,
        "lxml_error": lxml_err,
        "xmlschema_error": xmlschema_err,
    }


def _schema_version_at_least(version: str, minimum: str) -> bool:
    """Compare dotted SchemaVersion strings (non-numeric suffixes ignored per segment)."""

    def parts(v: str) -> list[int]:
        out: list[int] = []
        for p in v.replace("_", ".").split("."):
            digits = "".join(ch for ch in p if ch.isdigit())
            if digits:
                out.append(int(digits))
            elif out:
                break
        return out

    return parts(version) >= parts(minimum)
