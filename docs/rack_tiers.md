# Pipe-rack tier table

A* prefers these elevations when `graph.metadata["rack"]["enforce"]` is set.
Assignment (service → tier) is always recorded on every route as `rack_tier`.

Source: typical EPC / PIP rack practice — process on the upper tier, utilities
in the middle, gravity drains on the lowest tier.

| Service class | Example services | Tier | Default Z (m) |
|---|---|---|---|
| process | PROCESS, FEED, GAS, HC, OIL, PROD, PRODUCTION, HYDROCARBON | `high` | 10.0 |
| utility | UTILITY, CW, CWS, CWR, IA, N2, STEAM, HS, LS, PW, WW, AIR | `mid` | 7.0 |
| drain | DRAIN, SEWER, VENT, OD, CD, CLOSED_DRAIN | `low` | 4.0 |

Implemented in `threadforge.rack.SERVICE_TIER_TABLE` / `assign_rack_tier`.
A rack volume may override elevations via `graph.metadata["rack"]["tiers"]`.

Lines that share a tier must still clear each other’s capsules (prior-route
obstacles in `collect_obstacles`).
