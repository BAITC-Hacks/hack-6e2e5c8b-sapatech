# T-10 — Focused confirmation of noisy pilots

Date: 2026-09-23. Branch: `feat/T-10-robust-strategy`.
Baseline: `ca44f89`; candidate is delivered on this feature branch.
After validation and the T-11 audit, the user explicitly authorized commit/push
to the existing private team repository. Merge, public visibility, platform
submission and team scheduler changes are outside this delivery.

## Change and rationale

The original strategy could select a campaign because it won a comparison of
many noisy one-off pilots. It also treated uncertainty in transfer from push
to another channel as independent in every repeated pilot. This let repeated
push measurements incorrectly reduce uncertainty about an unmeasured channel.

The candidate makes two changes in `strategy/core.py`:

1. Pool observations within each source channel, weighted by actual sample
   size, before applying the channel multiplier and transfer uncertainty.
   Repeated direct measurements reduce sampling noise; shared transfer error
   remains. Pooling also avoids different answers when a mixed-sign set of
   observations is split differently before positive-effect saturation.
2. Prioritize confirmation after eight pilots, and stop sampling a candidate
   once it has at least 800 observed contacts. Four full samples halve the
   sampling standard error relative to one 200-contact pilot. This is a stop
   threshold: the last request can cross 800 for smaller actual sample sizes.
   Global contact, budget, pilot-size, deadline and final-reserve checks apply.

Candidate generation, historical prior, half-standard-error portfolio penalty,
agent orchestration, dependencies and public contract v1 are unchanged.
There are no seed-specific or tariff-specific decision rules.

## Experiment selection

Before reading experiment results, two variants were declared in T-10:
`confirm` (the two changes above) and `regularized` (same changes plus a
stronger historical prior, equivalent in precision to one 200-contact pilot).
Only seeds 0–19 were used for this choice. All evaluations used the supplied
official evaluator unchanged, with public data and public pilot responses.
The agent never receives evaluator internals or hidden effect tables.

| Seeds 0–19 | Baseline | Confirm, selected | Regularized, rejected |
|---|---:|---:|---:|
| Mean net ARPU gain | 466,343.93 | 589,588.16 | 393,953.58 |
| Worst net gain | -282,662.44 | -70,361.89 | -122,229.90 |
| Losing runs | 4/20 | 1/20 | 2/20 |

`regularized` was rejected because mean net gain declined. These development
results are used for selection, not presented as independent validation.

Before evaluating seeds 100–199, the selected code was frozen with
`strategy/core.py` SHA-256:
`b4f7126c4c1c2c7de17871c639306452a54b893e3d9fbf5685789b00deff37c3`.
This is the frozen Windows file-byte hash. Git stores LF line endings;
the committed source and the frozen source normalized to LF both have SHA-256
`07d7e0849d31ae5adb27485e710e41e09405042ede1561b0740471084379ad1b`.
The delivery check verified equality after line-ending normalization.
No strategy edits were made after the holdout began. The declared acceptance
gate requires improved mean net, no increase in losing runs, no worse minimum,
and valid raw outputs, resource accounting, runtime and strategy diagnostics.

## Independent validation

**Accepted on the declared gate.** Both revisions completed 100/100 seeds
100–199, with zero raw, resource or diagnostic errors and no fallback use.

| Holdout seeds 100–199 | Baseline `ca44f89` | Frozen candidate |
|---|---:|---:|
| Mean net ARPU gain | 286,700.61 | 629,492.15 |
| Median net gain | 228,119.90 | 640,489.07 |
| Worst net gain | -742,519.79 | -389,787.24 |
| Profitable runs | 73/100 | 95/100 |
| Losing runs | 27/100 | 5/100 |
| 10th percentile net | -265,957.52 | 49,707.55 |
| Mean of worst ten runs | -391,362.30 | -51,920.25 |

Mean paired improvement is **342,791.54** (119.6% of baseline mean). The
candidate wins 76/100 paired seeds and loses 24/100; improvement is not
universal. Full evaluator runtime during concurrent blocks averages 6.29 s
for baseline and 6.44 s for candidate, maximum 8.02 s across both. These are
concurrent-machine measurements, not standalone speed benchmarks.

Compact per-seed results, source/input hashes and import-path evidence:
[`T-10-evidence.json`](T-10-evidence.json). Every seed 100–199 occurs exactly
once per revision. No unsuccessful seed is omitted. Both revisions respected
the 100,000 budget, 15,000 contact, 20 pilot and 1–10 final-campaign limits.
An independent read-only audit recomputed the statistics and checked every
merged row against its original block, the compact evidence against the full
report, and the current branch's source against the frozen candidate hash.

`evals/compare_isolated.py` launches two separate Python interpreters with
isolated imports, separate package/data directories and no inherited API
credentials. It records import paths, process IDs, source and input hashes,
checks identical official/data inputs and unchanged snapshots, and audits
raw campaigns and public pilots before official sanitation/scoring. The
old `compare_agents.py` is not used for the independent comparison because
switching paths in one interpreter could retain a cached `strategy` module.

The first full comparison failed during JSON export because a zero-cost
campaign can have infinite official ROI. The exporter now preserves nonfinite
ancillary values as explicit strings while still rejecting nonfinite net
gain/resources. A regression covers both cases. The same frozen strategy was
rerun on all 100 seeds in four concurrent paired blocks of 25; rows were merged
in seed order before applying the original gate to the full 100-seed group.
Each worker also uses a private empty bytecode-cache prefix, and both parent
and workers verify that harness/validator hashes stay unchanged.

Local environment: Windows, Python 3.12.14, pandas 3.0.1, numpy 2.3.5.
Snapshots and full local logs are in ignored `jobs/t10/`. Compact aggregate
and per-seed evidence is retained with this report, without raw datasets.

## Reproduction

The exact local experiment snapshots are `jobs/t10/baseline` (baseline code)
and `jobs/t10/confirm` (frozen candidate). Each contains its own copy of the
same official participant package and data. Those organizer files are ignored
by Git and must be installed locally for a fresh reproduction. Recover baseline
sources from `ca44f89`; copy current `agent.py` and `strategy/` for the candidate.
Do not copy candidate strategy into the baseline snapshot.

```powershell
python -m unittest scripts.test_agent strategy.tests.test_core strategy.tests.test_robustness evals.test_contract_checks evals.test_compare_isolated -v
python evals/compare_isolated.py --baseline-dir jobs/t10/baseline --candidate-dir jobs/t10/confirm --seeds 100:200 --output jobs/t10/holdout.json
python evals/check_agent.py --agent agent.py --package . --feedback-check
python local_eval.py
python make_submission.py
```

Range stops are exclusive. CLI exit code zero means a valid experiment;
`paired.meets_acceptance` determines whether the candidate meets the gate.
On this machine the WindowsApps `python` alias was unusable; commands used
the bundled Python executable returned by Codex workspace dependencies.

## Other checks and limitations

- **54/54 tests pass**: original 35, nine strategy regressions and ten
  harness regressions. New tests cover partition-invariant evidence,
  shared transfer error, contradictory direct-channel feedback, confirmation,
  small cohorts and resource limits.
- Fixed positive versus negative public pilot feedback changes final campaigns;
  both raw plans validate without errors.
- Two official `make_submission.py` runs in an isolated candidate copy produce
  identical bytes, seven campaigns, Windows SHA-256
  `152a422dd76a8ece8f17c12395dca6034fa69f827e5f2b77482cf9765b61ee1b`.
  After CRLF-to-LF normalization the hash is
  `290f30c0fddac57c737210051afc1ebde2c964a97900cf9d8f57ea5ce25bad15`.
  After acceptance, two additional official generations in the branch root
  matched each other and that isolated CSV byte for byte. Root `submission.csv`
  now contains these seven campaigns.
- Submission seed 42 is positive but regresses: baseline +327,917.04,
  candidate +253,391.73 (11,558 total contacts, 99,998 cost, 20 pilots).
  The change is evaluated across seeds, not selected for
  the submission seed. Improvement on every run is not claimed.
- New seeds vary pilot sampling/noise for the same synthetic effects; they do
  not supply independent hidden business scenarios. Hidden judging differs.
- Cross-channel transfer, historical causality and unknown pilot overlap remain
  approximations. Paid channels still lack direct pilot confirmation. The
  strategy does not guarantee positive profit.

## Handoff

Strategy and evaluation changes cross the earlier owner boundary and are
explicitly scoped in T-10 for this user request. Preserve earlier authorship.
The user subsequently authorized commit/push. Evaluation tooling and strategy
are separate `[T-10]` commits; the audit is a separate `[T-11]` commit. The
integrator should review the branch and evidence before merging or submitting.
Local main remains `ca44f89`; remote main was `da9193b` at the delivery check,
with README-only changes since the evaluation baseline. It was not merged or
rebased into this frozen candidate. Include updated `submission.csv` with the strategy
if this candidate is adopted; the previous CSV belongs to the baseline.
