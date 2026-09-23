# T-04: deterministic campaign core

Public exports (contract v1):

```python
from strategy import build_candidates, choose_pilot, select_campaigns
```

All three functions are synchronous and pure: DataFrames, dictionaries and lists
in; ordinary dictionaries/lists out. No environment object, file access, network,
randomness, additional dependencies or persistent state. Requires pandas/numpy.

## Integration

The official environment attribute is **`env.customer_profile`**, although the
introductory paragraph of contract v1 says `env.profile`. Pass
`env.customer_profile`, `env.tariffs` and `env.channels` without renaming columns.
Load `data/change_tariff.csv` outside this package, or pass an empty DataFrame.

1. Build candidates once.
2. Pass current resources and observations into `choose_pilot`.
3. If it returns a request, execute `env.run_pilot(**pilot["request"])` and append
   `{**pilot, "result": result}` on success. Refresh resources on every call.
4. Stop on `None`, then pass refreshed resources to `select_campaigns`.

`strategy/tests/official_smoke.py` contains a test-only example adapter. The
integrator owns the production timer, bounded error handling and root `agent.py`.
The production adapter should stop/recover after bounded failed pilot attempts;
failed attempts are not successful observations and do not update the posterior.

## Statistical assumptions

- Candidates cover current tariff × ARPU segment × every different valid target.
  Unknown/missing ARPU segments also get a current-tariff-only candidate because
  the official filter language cannot address missing values directly.
- Historical ARPU before the transition must be finite and positive; after ARPU
  must be finite and nonnegative. Ratios are clipped to [-1, 2], summarized by
  their median, and shrunk by `n / (n + 20)`. These are robustness choices, not
  estimates of causal conversion. Historical segment boundaries follow the
  public participant guide: <1000, 1000–5000, >5000.
- Segment-specific history backs off to the same tariff-pair history. Missing
  history gives an exactly zero prior. `history_count` describes the historical
  rows actually used; no joining history IDs to audience IDs is attempted.
- The campaign-effect prior is deliberately weak: 10% of the historical change
  ratio times channel multiplier, with standard deviation 0.15. This conversion
  discount is an explicit heuristic, not identified by the historical sample.
- Pilots update mean/variance by precision weighting using actual sample size
  and the publicly documented per-customer noise 0.804. Same-channel observed
  ratios are **not multiplied again**.
- Cross-channel transfer scales by the multiplier ratio, caps positive scaling
  at 1.5 and adds uncertainty. Unknown conversion saturation makes this an
  approximation; direct paid-channel experimentation is not implemented yet.
- Research uses the cheapest channel, an optimistic confidence score and a
  penalty for repeatedly exploring the same cohort. Positive uncertain cells
  can receive repeats; clearly negative cells and cells with 600 observed
  contacts stop. After ten pilots, promising sampled candidates have priority
  for confirmation up to 400 observed contacts, reducing winner selection bias.
  Samples request 200 contacts, reduced to available audience/resources, never
  requested below 10.
- Research reserves 70% of initial available contacts (up to 10,000) for the
  final plan and stops with 20 seconds left. If only paid channels are supplied,
  a single pilot may use at most 10% of remaining budget. No fixed mock winners
  or seed-specific constants are used.

## Portfolio and limits

Greedy marginal net gain uses a half-standard-deviation conservative effect,
actual channel cost, ID_NUMBER order, per-campaign cap, and remaining money and
contacts. Each step recomputes reach after previous campaigns. Overlapping
final campaigns contribute only improvement over the best previous effect,
while every repeated contact still costs money and contact capacity.

Pilot IDs are unknown. Estimated pilot coverage is the union probability of
uniform samples in each candidate cohort; its estimated best effect is treated
conservatively when deciding whether a repeat contact adds value. This is an
approximation, especially with overlapping pilot cohorts and negative pilots.
The policy never claims to know which individual customers were piloted.

The first feasible campaign is returned even when every conservative estimate
is negative; it is the least harmful by estimated marginal net gain. Further
campaigns require positive marginal gain. If resources are already exhausted,
a syntactically valid declaration is returned, but cannot execute any contacts.
Empty audiences/candidates or zero campaign limits raise a clear error because
no meaningful nonempty plan can be built in those cases.

Scorer truncation to remaining money/contacts is simulated explicitly, including
the 5000-customer cap. No unsupported `n_customers` or `explicit_ids` is added to
the final campaign. This does not promise all matching customers will be reached.

## Checks

```bash
python -m unittest discover -s strategy/tests -v
```

Optional official-package integration, without changing root `agent.py` or
copying organizer data into Git:

```bash
cd /path/to/extracted/participant/package
PYTHONPATH=/path/to/repository python /path/to/repository/strategy/tests/official_smoke.py --runs 10
```

The harness validates the raw returned campaigns, calls the unmodified official
evaluator, checks resources and runtime, and repeats the last seed to compare
both decisions and public observations. Mock performance is not hidden-judge
performance. Submission generation and independent evaluation belong to T-03
and T-05; the core does not write submission files.

## Robustness check (T-04 phase 2, 2026-09-23)

The integrated baseline is commit `cca147b`; its portfolio score remains
`mean - 0.5 * error`. On public pilot observations in the local evaluator,
20 push pilots often cover 13–15 distinct candidate cells. In the losing runs
examined (seeds 2, 11, 12, 16), observed lift ratios include both positive and
negative values of roughly 0.1 or less. With the public per-customer noise
standard deviation of 0.804, a 200-contact pilot has a sampling standard error
of about 0.057. Selecting the best of many noisy estimates can therefore favor
an apparent winner. Confirmation pilots reduce this risk but do not eliminate
model error or overlapping-cohort dependence. Pilots are on push, while some
final campaigns use paid channels; multiplier-based transfer is unvalidated by
direct paid-channel observations. Historical tariff changes are observational,
so their weak prior cannot establish a causal campaign effect. The reported
posterior error covers the assumed sampling model, not these additional risks.

Exactly one experimental change was evaluated in a temporary copy: increase
the portfolio penalty from `0.5 * error` to `1.0 * error` in
`select_campaigns`. Baseline and variant used identical seeds in each block;
seeds 10–19 were held out until after the 0–9 comparison. Numbers are local
official-evaluator results, not hidden-judge estimates. Cost is mean total
spend, runtime is mean strategy time per run, and violations count failures of
the raw-output, budget, contact, pilot-count and runtime checks in the test
adapter.

| Seeds | Policy | Mean net gain | Median | Minimum | Negative runs | Mean cost | Mean runtime | Violations |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0–9 | Baseline | 533,014.48 | 575,915.02 | -282,662.44 | 1/10 | 99,823.00 | 1.652 s | 0 |
| 0–9 | 1.0-error penalty | 213,588.40 | 232,166.97 | -100,343.86 | 1/10 | 22,230.80 | 1.616 s | 0 |
| 10–19 | Baseline | 399,673.39 | 256,420.23 | -63,864.92 | 3/10 | 94,983.20 | 1.526 s | 0 |
| 10–19 | 1.0-error penalty | 254,842.76 | 334,970.10 | -156,762.94 | 3/10 | 54,799.40 | 1.553 s | 0 |

The variant won only 1/10 paired seeds in the first block and 3/10 in the
holdout. It spent less but also lost 319,426.08 and 144,830.62 in mean net
gain respectively; negative-run counts did not improve. In the holdout its
worst result was worse. **Rejected: keep the original algorithm unchanged.**
Twenty pilots ran on every seed. All 14 unit tests passed; repeating seeds 9
and 19 produced identical campaigns, public observations and net gain.

To reproduce, run the unit command above and the official smoke harness with
`--runs 10` and `--runs 20` from an extracted participant package; use rows
10–19 of the latter for the holdout and note that the harness repeats its last
seed. For the comparison, copy `strategy/` to a temporary directory, change
only the one `ratio = mean - 0.5 * error` line to `1.0 * error`, and run the
same commands with that copy on `PYTHONPATH`. The experiment used Python 3.9,
pandas 2.3.3 and numpy 2.0.2. Do not interpret these 20 synthetic seeds as a
confidence interval or a guarantee of positive returns.
