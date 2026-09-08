# Hydrotest packs (B22)

## ASME B31.3 paragraph 345.4.2

Hydrostatic test pressure (metallic piping):

\[
P_T = 1.5 \times P \times \frac{S_T}{S}
\]

- \(P\) — internal design pressure
- \(S_T\) — allowable stress at test temperature (B31.3 Appendix A **Table A-1**, A106 Gr.B)
- \(S\) — allowable stress at design temperature (same table)
- \(P_T\) shall not exceed any component rating

Citation: ASME B31.3 Process Piping, paragraph **345.4.2**.

## ASME B16.5 Table 2-1.1 (Group 1.1) cap

Flange working pressure (bar) vs temperature and class. ThreadForge uses
Table 2-1.1 Group 1.1 (A105 / A106-B / A53-B). The hydrostatic \(P_T\) is
capped at the class rating at **test** temperature.

Flange class is declared (`flange_class` / `rating`) or inferred as the
lowest class whose Table 2-1.1 rating at design temperature ≥ design \(P\).

## Test medium

B31.3 **345.4** is a hydrostatic (liquid) test. The service table maps
PROCESS / LPG / C01 FluidCodes (`MNb`, `MNc`, `WKa`, …) to **water**.

## Vents / drains

High-point vents and low-point drains are the unique vertices at global
maximum / minimum Z on the pack route polyline. C01 uses documented
plant-metre profiles in `hydrotest.C01_PLANT_PROFILE_M` (not P&ID drawing XY).
