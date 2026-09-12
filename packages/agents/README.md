# Lane C — rules, checks, the router and the gate

What counts as a problem, and what the loop does next.

```bash
python -m pip install -e packages/agents
python -m pytest packages/agents -q
```

## The shape of it

```
rules/          the thresholds, and the ledger that decides which ones run
checks/         one module per section, each answering one geometric question
copy.py         every sentence the owner reads
findings.py     a measurement becomes a problem, a pass or a request
assess.py       one pass over a shop
router/         the closed action set, validated before it authorizes anything
fix/            proposals that move furniture and keep the inventory
evaluation/     the labelled dataset, the scorers and the acceptance gate
```

## Two rules the code enforces on itself

**No check runs until a person has read its section.** `rules/data/verification.json`
records who read what. An entry binds the rule id, the section, the threshold and
the unit together, so editing a threshold invalidates its verification and the
check switches itself off. There is no edit an agent can make that both moves a
number and keeps the check running.

```bash
python -m standardphysics_agents.cli rules show route_clear_width
python -m standardphysics_agents.cli rules verify route_clear_width --by "your name"
```

**Thresholds live in the rule pack and nowhere else.** A check reads the number
off its rule. It never compares against a literal, and it never takes a
provider's word for whether something passed.

## Swapping the measurements

Every check talks to `MeasurementProvider`. The constructor argument is the only
thing that changes between the fixture shop and a real scan.

```python
from standardphysics_agents import assess
from standardphysics_fixtures import FixtureMeasurements, build_graph, build_scenario
from standardphysics_pipeline import PipelineMeasurements

result = assess(build_graph(), build_scenario(), PipelineMeasurements())
for finding in result.problems:
    print(finding.title, "-", finding.detail)
```

`result.unevaluated` lists rules held but not answered, with what each is
waiting on. It goes to the team, never to the owner: a rule we could not answer
must not look like a clean pass.

## Tracing

`weave.init()` happens once, through `init_tracing()`. Every check and every
agent call carries `@traced`, which costs one attribute read when Weave is not
configured, because the tests run in CI and CI has no keys.
