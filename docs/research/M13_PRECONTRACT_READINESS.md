# M13 pre-contract readiness: DVG-versus-satellite differential evidence

**Readiness: READY FOR SYNTHETIC IMPLEMENTATION WITH DEFERRED REAL-DATA
DECISIONS.** M13 remains planned under the current [roadmap](../ROADMAP.md).
This review defines a conservative software boundary, not a biological
classifier, caller benchmark, or literature review.

## 1. Smallest useful baseline

Freeze an evidence dossier that imports the existing M5 caller record
unchanged and organizes it against a set of explicit alternative hypotheses:

- defective/defective-interfering genome or other helper-derived rearrangement;
- satellite or other subviral element;
- ordinary viral genome or fragment;
- host, microbial, mobile-element, vector, or reagent alternative;
- mixed infection, read chimera, amplification/assembly artifact; and
- unresolved or insufficiently assessed.

The initial baseline has no cross-caller vote, winner, calibrated score, or
biological class verdict. A completed M5 zero is one caller-scoped
no-evidence observation; it does not support a satellite hypothesis by itself.
A detected junction is not proof of interference or dependence.

See the [M5 contract](../M5_DVG_EVIDENCE.md),
[M13 design research](M13_DVG_DIFFERENTIAL_DESIGN_RESEARCH.md),
[resource/tool audit](M12_M16_RESOURCE_TOOL_AUDIT.md), and
[validation logistics](M12_M16_VALIDATION_LOGISTICS.md).

## 2. Contract proposal

### Inputs

- Required: immutable candidate ID, exact M5 caller run/event/accounting
  records, producer status/schema, read/reference identity and hashes, and
  method/settings provenance.
- Optional: M6 reconstruction/read-back; M7 exact recurrence with declared
  metadata; M8/M9 homology/protein observations; M10 architecture; M12
  read-origin/control dossier; a separately curated comparator manifest.
- External callers (DI-tector, VODKA2, DVGfinder) are **not** required inputs.
  Any future optional integration must be separately provisioned and carry
  its own source, terms, version, dependencies, inputs, and outputs. DVGfinder
  is not an independent third caller vote because it wraps other callers.

Optional evidence is either linked by immutable artifact identity or explicitly
absent. M13 must not silently rerun M5 or reinterpret an upstream result.

### Output

One M13 bundle contains:

- Candidate and input-manifest identity; M13 schema/implementation version.
- Caller-specific event rows preserving raw coordinates, orientation,
  junction, support counts, reference identity, and original caller status.
- Hypothesis-evidence rows with evidence for, against, shared across, or
  unassessed for each alternative. Any “event type” is explicitly tied to a
  caller/reference and a versioned normalization rule.
- Provenance links to all consumed upstream artifacts, exact reference and
  comparator snapshots, and source terms where relevant.
- A summary of conflicts, missing branches, and unresolved alternatives.

There is no single `DVG=true/false`, `satellite=true/false`, interference, or
helper-dependence output in this baseline.

### Typed states

Keep the M5 caller status as authoritative source data. M13 may add these
branch-level states without overwriting it:

- `NOT_EVALUATED` / optional source absent;
- `DEPENDENCY_UNAVAILABLE`, `FAILED`, `INTERRUPTED`;
- `INVALID`, `INCOMPLETE`, or `TRUNCATED` output/accounting;
- `COMPLETED_WITH_EVENTS`;
- `COMPLETED_NO_CALLER_SIGNAL_WITHIN_SCOPE`;
- `CONFLICTING` evidence and `UNRESOLVED` hypothesis.

The final two no-signal/conflict states are scoped dossier descriptions, not
class conclusions. Missing comparator evidence is `NOT_ASSESSED`. A completed
zero M5 record must never be changed to a biological negative or satellite
positive.

### Provenance, cache, and failure behavior

Bind M13 identity to the candidate/input digest, exact M5/M6/M7/M8/M9/M10/M12
records actually consumed, selected caller/source snapshots, declared
reference versions, event parser and coordinate-normalization version,
configuration, hypothesis/evidence schema, and output hashes. Changes local to
M13 invalidate M13 only. Do not rerun or invalidate M5–M12 for a dossier or
comparison; shared validator/cache semantics retain the existing scoped rule.

Fail closed on malformed event coordinates, incomplete expected/observed read
accounting, mismatched candidate/reference identity, or invalid provenance.
Preserve available rows when an optional branch fails, while marking that
branch failed or incomplete. Never turn tool absence into a completed zero.

## 3. Deterministic offline acceptance fixtures

1. Parse completed M5 event and zero-event fixtures; preserve their exact
   caller, reference, accounting, and status.
2. Use generated deletion-, copy-back-, and snap-back-like junction fixtures
   to test coordinate parsing and stated normalization mechanics only.
3. Give two caller-like fixtures matching-looking and conflicting events;
   ensure they remain distinct absent an explicitly frozen cross-caller
   identity rule.
4. Supply a M5 completed zero with no comparators; report one scoped M5
   observation and unresolved alternatives, never “satellite.”
5. Exercise malformed coordinates, reference mismatch, duplicate event IDs,
   corrupt hash, interrupted run, incomplete accounting, and truncated caller
   output.
6. Mark M6 read-back and M5 input as reused/shared evidence where applicable;
   do not count one source read/event more than once.
7. Missing M12/comparator/tool input produces an explicit unassessed branch
   and stable deterministic output.

These fixtures establish software mechanics, not caller sensitivity,
biological class, or interference.

## 4. Freeze blockers and other deferred decisions

The **M5-only descriptive dossier contract can freeze now**. Adopt the
following boundaries:

1. Preserve native caller event IDs and raw coordinates as the identity for the
   baseline.
2. Do not merge events across callers or declare cross-caller agreement until a
   cross-caller equivalence/coordinate-normalization contract is separately
   approved.
3. Keep alternative hypotheses and unresolved states; do not emit class,
   interference, or dependence verdicts.

| Decision | Effect |
| --- | --- |
| Cross-caller event equivalence, coordinate normalization, caller combination, and supported class vocabulary? | **Blocks contract freeze only for the optional multi-caller comparison branch.** Not needed for the M5-only dossier. |
| Which licensed/versioned external callers are provisioned? | **Blocks optional caller execution only.** Missing caller is unavailable/not assessed, not a negative. |
| Which comparator records and label tiers are authorized and curated? | **Blocks empirical benchmark claims and real-data comparison**, not the synthetic evidence matrix. |
| What source evidence warrants DVG/DI, satellite, or helper-derived attribution? | **Blocks biological classification claims.** It does not block recording observations. |
| What experiment demonstrates interference or dependence? | **Blocks those biological claims only.** A computational junction is insufficient. |

**Milestone disposition:** `READY FOR SYNTHETIC IMPLEMENTATION WITH DEFERRED
REAL-DATA DECISIONS`. The core M5-only interface can be frozen with the
boundaries above; do not make external callers or curated comparators core
requirements.

## 5. M1–M10 compatibility and boundaries

M13 consumes typed M5 output; it does not alter the M5 ViReMa adapter, thresholds,
status semantics, or accounting. M6 read-back is contextual and reuses
assembly-eligible reads. M7 recurrence is exact recurrence over declared
metadata, not class truth. M8/M9 matches and M10 architecture are separate
method-scoped evidence. No M1–M10 upstream change is required. The
[implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md) states when
optional M12 context and later integrations can be connected.
