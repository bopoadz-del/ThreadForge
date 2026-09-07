# C08 cross-page OPC fixtures

Upstream TrainingTestCases **C08 Two connected P&IDs (Covestro)** ships PDF/XLS only
(no Proteus XML in dexpi 1.3). Verified via GitLab API recursive tree.

These two sheets reuse the public **C01** `FlowOutPipeOffPageConnector-1` /
`FlowInPipeOffPageConnector-1` element XML (CC-BY-4.0) with a shared
`CrossPageConnectionAssignmentClass=C08-JOIN-001` so ThreadForge can pin
cross-file OPC → FromTo joins without inventing plant topology.

Not a stand-in claiming to be Covestro UER drawings — capability fixture only.
