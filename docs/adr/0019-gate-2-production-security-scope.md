# Define Gate 2 as release security and offline runtime

Accepted October 22, 2026.

Gate 2 closes on complete, successful evidence matching the release candidate's
identity, security findings, offline runtime compatibility and execution
safeguards. CRITICAL and untreated HIGH findings block. A temporary HIGH
treatment needs Nathan's approval for the exact finding, evidence, artifact
scope and expiry, plus support from enforced policy; approval does not override
a failing security job. The current web audit's no-HIGH-exceptions guard stays
in force. Complete matching evidence closes Gate 2 without another manual
sign-off, subject to any required HIGH-treatment approval. Existing CI jobs,
audit policy and security enforcement remain unchanged.

Browser functionality and accessibility belong to Gates 11/12. Historical
Firefox, WebKit, fixed-size Linux matrix and exhaustive source/input/visual
diagnostics are follow-up unless they establish release security impact. Any
such security impact returns to Gate 2. Moving requirements does not mark them
passed or waive required launch acceptance. Gate 2 closure does not authorize
public launch or advance another gate.

Earlier evidence can be reused only when its inputs and coverage apply to the
candidate. Record source, lockfiles, patch and tested image identities and
relevant runtime versions. Later build/cutover gates bind the actual artifact
or repeat applicable checks; matching source alone does not identify arbitrary
rebuilds. Metadata and synthetic fixtures do not prove hosted compatibility,
and a boundary snapshot does not prove continuous isolation.
