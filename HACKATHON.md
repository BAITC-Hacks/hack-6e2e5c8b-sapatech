# HackAlem AI project status

Last updated: 2026-09-23

## Current decision

- **Status:** baseline 4272a07 published in main and preserved. Operator started T-08/T-09/T-10 after audit T-07; CONTROL revision3, manual coordination, no schedules. Delivery deadline 17:00 UTC+05; freeze 16:30. README/reproducibility take priority; replace strategy only after independent acceptance. Not submitted to the platform.
- **Track:** 04 Telecommunications.
- **Case owner:** Beeline.
- **Official case:** Beeline Tariff Marketing Campaigns Case.
- **Project name:** Tariff Marketing Campaign Agent.
- **Primary user:** marketing analyst planning next month's tariff campaigns.
- **Problem:** campaigns selected without reliable target-population evidence can waste contact budget or reduce ARPU through downsell.
- **One-sentence value:** use historical behavior and noisy pilot feedback to produce a reproducible campaign plan that maximizes net ARPU gain within fixed budget, contact, and pilot limits.

The case package contains synthetic data only. It does not represent real Beeline customers, tariffs, revenue, or business performance.

## Success definition

The submitted solution is a Python agent with the exact public contract below:

```python
class Agent:
    def act(self, env) -> list[dict]:
        ...
```

The agent must inspect the provided audience and tariff data, call `env.run_pilot(...)` at least once, use the observed pilot results, and return between 1 and 10 valid final campaigns. The strategy must remain within all resource limits and must generate a reproducible `submission.csv`.

The business objective is:

```text
net result = ARPU gain for unique subscribers - communication cost
```

The no-action baseline in the supplied package is `150,641,084`, calculated as the sum of `predicted_arpu`. Pilot contacts and final campaign contacts both consume budget and contact capacity.

## Official constraints

### Campaign limits

| Constraint | Limit |
|---|---:|
| Final campaigns | 1-10 |
| Subscribers per campaign | 5,000 maximum |
| Total contacts, including pilots | 15,000 maximum |
| Total communication budget, including pilots | 100,000 units |
| Pilots | 20 maximum |
| Customers per pilot | 10-200 |
| Subscriber scoring | Each subscriber counts once, using their best applicable campaign |

### Channels

| Channel | Cost per contact | Effect multiplier |
|---|---:|---:|
| `push` | 0 | 0.50 |
| `sms` | 4 | 0.65 |
| `digital_ads` | 22 | 0.85 |
| `call` | 160 | 1.20 |

### Runtime and robustness

- The case specification sets a hard maximum of 10 minutes, including model calls.
- The starter `agent_template.py` asks the agent to work offline and finish within 5 minutes.
- Until organizers clarify the difference, design for the stricter target: complete within 5 minutes and never exceed 10 minutes.
- External model calls must be wrapped in error handling and have a deterministic local fallback.
- Hidden judging effects differ from the mock environment. Do not tune constants to the mock effects.
- Do not inspect environment internals through `__closure__`, `gc`, organizer files, or similar bypasses. The result will be invalidated.
- Do not hardcode secret values or expected hidden outcomes.

## Mandatory acceptance criteria

- [x] Root-level `agent.py` defines `Agent.act(env)` and imports without errors.
- [x] `python local_eval.py` completes successfully.
- [x] The agent conducts at least one pilot through `env.run_pilot(...)`.
- [x] Pilot observations affect the final campaign choice.
- [x] The returned list contains 1-10 campaigns using valid tariffs and channels.
- [x] No campaign is rejected by the evaluator sanitizer.
- [x] Budget, contact, pilot, and per-campaign limits are respected.
- [x] `python make_submission.py` creates a reproducible `submission.csv`.
- [x] `python local_eval.py --runs 10` shows the strategy's variance across seeds.
- [x] The repository contains clear launch, validation, data, and limitation documentation.

Acceptance evidence is recorded in coordination/RECEIPTS.md and the T-04/T-05
reports. Final CSV matches the previously verified seed42 hash. This is technical
readiness, not a claim of hidden-score performance or platform acceptance.

## Output schema

Every campaign requires `target_tariff` and `channel`. Filters are optional.

```json
{
  "campaign_name": "premium_upsell",
  "filter_arpu_segment": "HIGH",
  "filter_data_segment": "HEAVY",
  "filter_call_segment": null,
  "filter_current_tariff": "tariff_4;tariff_8",
  "target_tariff": "tariff_10",
  "channel": "sms"
}
```

Supported audience dimensions include ARPU segment, data-use segment, call-use segment, and current tariff. The target tariff must be one of the 21 supplied tariff codes.

## Supplied data

The participant package is currently stored locally outside the repository as:

```text
~/Downloads/beeline_case_participants (1).zip
```

| File | Purpose |
|---|---|
| `customer_profile.csv` | Target audience: 23,441 subscribers, segments, behavior, current tariff, and `predicted_arpu` |
| `data/change_tariff.csv` | 14,823 data rows in the supplied local archive, with ARPU before and after |
| `data/traffic.csv` | Monthly minutes, SMS, data traffic, and device behavior |
| `data/arpu_monthly.csv` | Monthly subscriber revenue |
| `data/dict_tariff.csv` | Parameters of 21 synthetic tariffs |
| `tariff_dictionary.csv` | Tariff descriptions |
| `feature_dictionary.csv` | Column descriptions |
| `environment.py` | Official environment interface |
| `mock_environment.py` | Local noisy pilot environment |
| `scoring_core.py` | Scoring and campaign sanitation used by local evaluation |
| `local_eval.py` | One-run and multi-seed local evaluation |
| `make_submission.py` | Reproducible `submission.csv` generator using seed 42 |
| `agent_template.py` | Intentionally weak baseline agent |

The ready-made table `current tariff -> target tariff -> expected lift` is intentionally absent. Candidate quality must be estimated from historical data and then validated using pilots.

### Data handling

- Keep organizer-provided datasets local unless the organizers explicitly confirm that they may be committed to the private team repository.
- Do not upload the participant archive or raw datasets to public services.
- Never send real personal, confidential, or production data to external AI services.
- Delete temporary keys, tokens, and organizer-provided local copies after the event when required by the organizer instructions.

## Primary demo flow

```text
customer_profile + historical tariff changes
-> Agent.act(env)
-> build and rank candidate segment/tariff hypotheses
-> allocate limited pilot contacts
-> observe noisy lift ratios
-> update confidence and expected net value
-> choose channel and final campaigns
-> evaluator sanitizes and scores campaigns
-> submission.csv and human-readable run report
```

The demo should show one clean execution, the pilot history, remaining budget and contacts, the returned campaign list, and the resulting net ARPU gain. A second command should show stability across ten seeds.

## Planned strategy

This is the implementation hypothesis, not a claim that it is already built.

1. **Historical prior:** aggregate `change_tariff.csv` and supporting usage/ARPU data by current tariff, candidate target tariff, and available audience segments.
2. **Candidate generation:** exclude same-tariff transitions, tiny or invalid cohorts, and candidates whose reachable audience cannot justify contact cost.
3. **Initial exploration:** pilot a diverse shortlist instead of repeatedly testing near-identical cells.
4. **Uncertainty handling:** compare candidates using both observed lift and reliability; small positive pilots should not automatically beat better-supported results.
5. **Adaptive allocation:** spend additional pilots where more evidence can change the final decision; stop testing clearly poor or sufficiently understood candidates.
6. **Channel selection:** evaluate expected net gain after channel cost and multiplier rather than using one channel for every segment.
7. **Final portfolio:** select up to 10 non-duplicative campaigns while checking remaining budget, total contacts, cohort size, and subscriber overlap.
8. **Fallback:** if an optional LLM or external service fails, complete the run using the deterministic statistical strategy.
9. **Reproducibility:** seed any internal randomness from the submission seed or another documented deterministic source.

An OpenAI model may help summarize evidence or propose candidate hypotheses, but the scoring core, limits, budget checks, and fallback must remain deterministic and testable. Managed Agents infrastructure is optional; the official judging interface is `Agent.act(env)`.

## Explicit non-goals for the first working version

- No dashboard or web UI before the official evaluator path works.
- No direct integration with Beeline production systems.
- No use of real subscriber data.
- No campaign execution or external messages.
- No environment introspection or hidden-effect extraction.
- No model training that prevents a clean local run on an ordinary laptop.
- No tuning solely for one mock seed.

## Evaluation

The case defines a direct performance objective, net ARPU gain, and also publishes the following jury rubric:

| Criterion | Weight |
|---|---:|
| Task fit and working end-to-end scenario | 25 |
| Technical implementation and agentic architecture | 25 |
| README and reproducibility | 25 |
| Practical value | 15 |
| Development potential and originality | 10 |
| **Total** | **100** |

The exact relationship between the numeric net-result ranking and the 100-point jury rubric is not stated in the supplied materials and must be clarified with the mentor.

## Team ownership

Each participant needs attributable commits and task evidence. Internal interfaces are fixed in `docs/contracts.md` (ADR-003).

| Role | Name | Primary responsibility |
|---|---|---|
| A - product lead and integrator | Нурсултан | `agent.py`, public env calls, setup, integration, final submission; T-03 |
| B - strategy core owner | Бауыржан | `strategy/`: candidates, adaptive pilot policy, uncertainty and budget-aware portfolio; T-04 |
| C - evaluation and delivery owner | Ерлан | `evals/`, multi-seed evaluation, reproducibility checks, README and demo evidence; T-05 |

Do not squash all work into one participant's commit. Work on separate task branches and preserve each participant's contribution history.

## Local setup and measured baseline

Python 3.12.14, pandas 3.0.1 and numpy 2.3.5 were used on Windows.
Install the official ZIP locally; the installer preserves bytes and refuses to
overwrite differing files. Official code and data are ignored by Git.

```powershell
python -m pip install -r requirements.txt
python scripts/prepare_case.py "C:/path/to/beeline_case_participants.zip"
python scripts/prepare_case.py "C:/path/to/beeline_case_participants.zip" --baseline
Push-Location jobs/template_baseline
python local_eval.py
python local_eval.py --runs 10
python make_submission.py
Pop-Location
```

Measured unchanged template on 2026-09-23: seed 42 net **-1,035,279**, six
pilots and two final campaigns, command wall time 0.89 seconds. Seeds 0–9:
median **-357,948**, minimum **-1,019,431**, maximum **-76,493**, 0/10 positive.
The evaluator ran successfully; its FAIL label reflects negative business gain.
Two CSV generations had identical SHA256
`613d7c12899e1f42b70a7def168fdacb01a3bccf75c21539ce549be36d529420`.
Local logs: `jobs/t03-baseline/` (ignored). These are mock baseline results,
not a prediction of hidden judging quality.

## Agent validation commands

Run after local package installation. Do not copy agent_template.py over agent.py.
Until strategy/ is available, agent.py explicitly uses the official template;
this is a temporary baseline, not the finished strategy. Inspect Agent.diagnostics
for mode, errors, pilot observations, final costs and runtime.

```powershell
python -m unittest discover -s scripts -p test_agent.py -v
python local_eval.py
python local_eval.py --runs 10
python make_submission.py
```

T-03 validation: 11 focused orchestration tests pass. Wrapper runs seeds 0–9
under 0.28 seconds per evaluation in the current environment; seed 3 needs
pilot recovery because the official template returns no final campaigns.
Seed-42 CSV remains byte-identical to the template baseline. No final submission
is committed until the real strategy is integrated and checked. A cooperative
270-second timer stops new pilots with 15 seconds reserved for selection;
it cannot interrupt a hanging synchronous strategy function (ADR-004).

### Integrated checkpoint, 14:18 UTC+05

The paragraph above describes the temporary template stage. The current agent
uses the real strategy from Бауыржан `cca147b`; Ерлан's checks through `810e672`
are merged with their authorship preserved. Current focused test counts:
12 orchestration tests, 14 strategy tests and 8 evaluator tests passed.

Integrated seeds 0–9: mean net **+533,014.48**, median **+575,915.02**,
minimum **-282,662.44**, maximum **+943,807.80**, 9/10 positive. Measured full
evaluation runtime 3.67 s average / 3.88 s maximum on this Windows environment.
Seed 42: **+327,917.04**, 15,000 total contacts, 99,998 cost, 20 pilots and
10 final campaigns; diagnostics mode=strategy, no fallback/errors.
Two official CSV generations, also repeated in a disposable package without an
API key, matched SHA256 `bdcc64500857306de26e459acd4bc266da0e9a696b2a1ab3c416163517a7c91c`.
The candidate CSV is preserved locally in `jobs/t03-integrated/submission-seed42.csv`.

Update after checkpoint: T-05 cap fix 6065943 and independent report 5029ae3
are integrated. Eight checker tests and the feedback comparison passed; legal
caps are warnings. Short actual pilot sizes (1–9) and final README evidence
remain assigned to Ерлан in mailbox ER-001 revision 2. Windows CSV normalized
from CRLF to LF exactly matches Ерлан's macOS SHA256; no algorithm divergence
was found in these artifacts. Evidence is in coordination/RECEIPTS.md.
Бауыржан's 799de27 documents a rejected robustness experiment; core unchanged.
Final acceptance and submission are not yet claimed. Team exchange and stop
procedure are documented in coordination/MAILBOX.md.

Do not commit API keys, `.env`, the participant ZIP, or organizer datasets.

## Required configuration

The deterministic baseline requires no API credentials. If an OpenAI call is added, read the key only from the environment:

| Variable | Required | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | Optional | OpenAI model call inside an experimental agent path |

The agent must still complete successfully when the optional API call fails.

## Repository and event rules

- Use the private team repository issued by the hackathon platform as the source of truth.
- Build the submitted project during the hackathon window.
- Every participant must make a personal, attributable contribution.
- Use only the official event network; personal Wi-Fi hotspots and modems are prohibited unless organizers approve an exception.
- Do not scan, intercept, fuzz, brute-force, stress, attack, or bypass limits on event infrastructure or other teams' resources.
- Keep the repository restricted to the team and organizers.
- Do not place passwords, API keys, tokens, confidential data, or real `.env` values in Git, presentations, or chats.
- Review dependencies and AI-generated code before submission.
- Report exposed credentials, unintended cross-team access, suspicious activity, or discovered vulnerabilities to the organizers; do not exploit or publish them.
- Attendance rules include a 60-minute total personal-break limit and mandatory presence during the final hour.

## Integration state

- **Official repository:** `BAITC-Hacks/hack-6e2e5c8b-sapatech`
- **Stable branch:** `main`
- **Official initial commit:** `e1a99ae3d47398c67fdc9c4849e983e487a4fb71`
- **Current phase:** technical implementation complete; collecting STOP confirmations
- **Working now:** integrated strategy, pilot orchestration and independent verification
- **Implementation handoff:** see `PLAN.md` and named instructions in `coordination/people/`; Бауыржан can start from first T-02 commit `580f1eb`.
- **Pending dependencies:** three final STOP reports and scheduler-deletion confirmations. Technical reviews and final artifact checks are complete. Platform submission requires a separate operator instruction.

## Current priorities

1. Start the named owners on T-03/T-04/T-05 using the shared contract. Бауыржан receives T-04 first.
2. Confirm with the mentor whether raw case data may be stored in the private repository and clarify the 5/9-hour and 5/10-minute inconsistencies.
3. Prepare a local-only starter workspace and run the unchanged template as a baseline.
4. Implement a deterministic history-informed candidate generator.
5. Add adaptive pilots, uncertainty-aware ranking, channel economics, and hard resource guardrails.
6. Validate one run, ten-seed stability, and reproducible submission generation before adding optional LLM behavior.

## Required submission artifacts

- `agent.py`
- `submission.csv`, reproducible through `python make_submission.py`
- `requirements.txt` when third-party packages beyond the supplied environment are needed
- Repository README with architecture, setup, verification, data sources, integrations, and known limitations
- Latest code pushed to the official team GitHub repository
- Project name and description submitted on the track page before the deadline

## Demo checklist

- [ ] Clean setup command tested on a fresh environment.
- [ ] `local_eval.py` completes without rejected campaigns or limit violations.
- [ ] Pilot evidence visibly changes the final decision.
- [ ] Ten-seed result distribution recorded.
- [ ] `submission.csv` regenerated and compared with the expected deterministic output.
- [ ] Failure of any optional model call handled without terminating the run.
- [ ] Repository checked for credentials and organizer data before push.
- [ ] Each participant's commits and task evidence are visible.
- [ ] Five-minute live demo rehearsed.
- [ ] Backup terminal output and submission artifact saved locally.

## Open clarifications

1. Participant instructions state a five-hour build window, while the Beeline case headline says nine hours. Plan for five hours until the organizer confirms otherwise.
2. The case specification permits up to ten minutes of agent runtime, while `agent_template.py` asks for five minutes. Target five minutes and treat ten minutes as an absolute ceiling.
3. The materials do not state how numeric net ARPU ranking combines with the published 100-point jury rubric.
4. Confirm whether organizer datasets may be committed to the private team repository; keep them local until explicit approval.
