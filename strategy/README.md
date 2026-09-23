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
