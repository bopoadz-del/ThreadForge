# ThreadForge architecture

AUTO-GENERATED DAG by `scripts/gen_docs.py`.

<svg xmlns="http://www.w3.org/2000/svg" width="760" height="220" viewBox="0 0 760 220">
<rect width="100%" height="100%" fill="#f8fafc"/>
<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#64748b"/></marker></defs>
<line data-edge="ingest-topo" x1="110" y1="58" x2="220" y2="58" stroke="#64748b" stroke-width="1.5" marker-end="url(#arr)"/>
<line data-edge="topo-route" x1="290" y1="58" x2="400" y2="58" stroke="#64748b" stroke-width="1.5" marker-end="url(#arr)"/>
<line data-edge="route-clash" x1="470" y1="58" x2="580" y2="58" stroke="#64748b" stroke-width="1.5" marker-end="url(#arr)"/>
<line data-edge="route-pcf" x1="470" y1="58" x2="40" y2="158" stroke="#64748b" stroke-width="1.5" marker-end="url(#arr)"/>
<line data-edge="route-iso" x1="470" y1="58" x2="220" y2="158" stroke="#64748b" stroke-width="1.5" marker-end="url(#arr)"/>
<line data-edge="topo-awp" x1="290" y1="58" x2="400" y2="158" stroke="#64748b" stroke-width="1.5" marker-end="url(#arr)"/>
<line data-edge="pcf-http" x1="110" y1="158" x2="580" y2="158" stroke="#64748b" stroke-width="1.5" marker-end="url(#arr)"/>
<line data-edge="iso-http" x1="290" y1="158" x2="580" y2="158" stroke="#64748b" stroke-width="1.5" marker-end="url(#arr)"/>
<line data-edge="awp-http" x1="470" y1="158" x2="580" y2="158" stroke="#64748b" stroke-width="1.5" marker-end="url(#arr)"/>
<rect id="node-ingest" x="40" y="40" width="140" height="36" rx="6" fill="#1e293b" stroke="#38bdf8"/>
<text x="110" y="63" text-anchor="middle" fill="#f8fafc" font-family="monospace" font-size="11">DEXPI ingest</text>
<rect id="node-topo" x="220" y="40" width="140" height="36" rx="6" fill="#1e293b" stroke="#38bdf8"/>
<text x="290" y="63" text-anchor="middle" fill="#f8fafc" font-family="monospace" font-size="11">Topology</text>
<rect id="node-route" x="400" y="40" width="140" height="36" rx="6" fill="#1e293b" stroke="#38bdf8"/>
<text x="470" y="63" text-anchor="middle" fill="#f8fafc" font-family="monospace" font-size="11">A* routes</text>
<rect id="node-clash" x="580" y="40" width="140" height="36" rx="6" fill="#1e293b" stroke="#38bdf8"/>
<text x="650" y="63" text-anchor="middle" fill="#f8fafc" font-family="monospace" font-size="11">Clash</text>
<rect id="node-pcf" x="40" y="140" width="140" height="36" rx="6" fill="#1e293b" stroke="#38bdf8"/>
<text x="110" y="163" text-anchor="middle" fill="#f8fafc" font-family="monospace" font-size="11">PCF</text>
<rect id="node-iso" x="220" y="140" width="140" height="36" rx="6" fill="#1e293b" stroke="#38bdf8"/>
<text x="290" y="163" text-anchor="middle" fill="#f8fafc" font-family="monospace" font-size="11">Iso/GA</text>
<rect id="node-awp" x="400" y="140" width="140" height="36" rx="6" fill="#1e293b" stroke="#38bdf8"/>
<text x="470" y="163" text-anchor="middle" fill="#f8fafc" font-family="monospace" font-size="11">AWP/4D</text>
<rect id="node-http" x="580" y="140" width="140" height="36" rx="6" fill="#1e293b" stroke="#38bdf8"/>
<text x="650" y="163" text-anchor="middle" fill="#f8fafc" font-family="monospace" font-size="11">HTTP/MCP</text>
</svg>
