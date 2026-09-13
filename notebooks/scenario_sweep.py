import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium", app_title="One shop, one knob at a time")


@app.cell
def _():
    from dataclasses import replace

    import marimo as mo

    return mo, replace


@app.cell
def _():
    from standardphysics_agents.evaluation import scenarios
    from standardphysics_agents.evaluation.configuration import setup
    from standardphysics_agents.evaluation.runner import action_name
    from standardphysics_agents.rules import load_ledger, load_pack

    return action_name, load_ledger, load_pack, scenarios, setup


@app.cell
def _():
    # The workspace tokens, from apps/web/src/app/(workspace)/globals.css. The
    # notebook is a separate runtime, so it restates them here and nowhere else
    # in this file.
    PALETTE = {
        "paper": "#f6f5f1",
        "sheet": "#fcfbf8",
        "rule": "#e3e0d8",
        "ink": "#1b1c1e",
        "muted": "#5d5e61",
        "faint": "#8a8a88",
        "accent": "#2f5e9e",
        "problem": "#c8372d",
        "pass": "#2e7d4f",
    }

    # Each knob that sets a dimension: what to call it, and the range a shop
    # could plausibly be in. The keys are the fields on `Knobs`.
    KNOBS = {
        "aisle_inches": ("Gap between the display cases", 24.0, 72.0, 0.5),
        "counter_inches": ("Counter height", 28.0, 52.0, 0.5),
        "door_inches": ("Front door opening", 26.0, 44.0, 0.5),
    }
    return KNOBS, PALETTE


@app.cell
def _(KNOBS):
    def bounds(knob):
        return KNOBS[knob][1], KNOBS[knob][2]

    def knob_label(knob):
        return KNOBS[knob][0]

    return bounds, knob_label


@app.cell
def _(mo):
    mo.md(
        """
        # One shop, one knob at a time

        Move a slider and the shop changes shape. The same checks the server
        runs read the new room, so a measurement that appears here is the
        measurement an owner would be shown.
        """
    )
    return


@app.cell
def _(KNOBS, mo, scenarios):
    routine = mo.ui.dropdown(
        options={each.name: each.id for each in scenarios.ROUTINES.values()},
        value="Order a drink",
        label="Routine",
    )
    aisle = mo.ui.slider(
        *KNOBS["aisle_inches"][1:],
        value=31.0,
        label="Gap between the display cases",
        show_value=True,
    )
    counter = mo.ui.slider(
        *KNOBS["counter_inches"][1:],
        value=47.0,
        label="Counter height",
        show_value=True,
    )
    door = mo.ui.slider(
        *KNOBS["door_inches"][1:],
        value=35.5,
        label="Front door opening",
        show_value=True,
    )
    seating = mo.ui.switch(value=True, label="Keep the seating by the counter")

    mo.vstack([routine, aisle, counter, door, seating], gap=0.75)
    return aisle, counter, door, routine, seating


@app.cell
def _(aisle, counter, door, routine, scenarios, seating):
    knobs = scenarios.Knobs(
        routine=routine.value,
        aisle_inches=aisle.value,
        counter_inches=counter.value,
        door_inches=door.value,
        counter_side_seating=seating.value,
    )
    return (knobs,)


@app.cell
def _(load_ledger, load_pack, mo):
    nothing_verified = not load_pack().enabled(load_ledger(), max_tier=1)
    preview = mo.ui.switch(
        value=nothing_verified,
        label="Read every rule as verified, so every check runs",
    )
    return nothing_verified, preview


@app.cell
def _(preview, setup):
    # The knobs are about measuring a room, so the fix search stays off.
    configuration = setup(preview_unverified=preview.value, run_fixes=False)
    return (configuration,)


@app.cell
def _(bounds, mo, replace, scenarios):
    def parked(knobs, knob):
        """The knobs with the swept one moved to the start of its range.

        The sweep replaces that knob at every reading, so its current value
        cannot change the answer. Parking it keeps the cache key still while
        the slider for it moves, which is what lets the marker follow the
        slider without measuring the room thirteen more times.
        """
        return replace(knobs, **{knob: bounds(knob)[0]})

    @mo.cache
    def reviewed(knobs, configuration):
        """One room through the evaluator.

        Cached, because a slider moves a lot and the geometry behind a given
        setting never changes.
        """
        return scenarios.run_knobs(knobs, configuration)

    @mo.cache
    def swept(knobs, knob, steps, configuration):
        lowest, highest = bounds(knob)
        widths = [
            lowest + (highest - lowest) * step / (steps - 1) for step in range(steps)
        ]
        return scenarios.sweep_knob(knobs, knob, widths, configuration)

    return parked, reviewed, swept


@app.cell
def _(configuration, knobs, reviewed):
    outcome = reviewed(knobs, configuration)
    return (outcome,)


@app.cell
def _(mo):
    mo.md("""## What the checks found""")
    return


@app.cell
def _(PALETTE, action_name, mo, outcome, scenarios):
    def share(score):
        return "nothing to score" if score is None else f"{score:.0%}"

    def next_step(outcome):
        return (action_name(outcome) or "nothing").replace("_", " ").lower()

    def figure_block(outcome):
        scored = scenarios.scores(outcome)
        return f"""
        <div style="display:flex;align-items:baseline;gap:2rem;flex-wrap:wrap">
          <div>
            <div style="font-size:3rem;line-height:1;font-variant-numeric:tabular-nums;
                        color:{PALETTE['ink']}">
              {scored['measurement_error_in'] or 0.0:.3f} in</div>
            <div style="font-size:0.875rem;color:{PALETTE['muted']};max-width:24rem;
                        margin-top:0.35rem">
              between the dimensions these sliders set and the dimensions the
              pipeline measured in the room they built.
            </div>
          </div>
          <dl style="margin:0;font-size:0.875rem;color:{PALETTE['muted']};
                     display:grid;grid-template-columns:auto auto;gap:0.3rem 1rem">
            <dt>Questions asked</dt>
            <dd style="margin:0;font-variant-numeric:tabular-nums;
                       color:{PALETTE['ink']}">{share(scored['question_recall'])}</dd>
            <dt>Counter and door found</dt>
            <dd style="margin:0;font-variant-numeric:tabular-nums;
                       color:{PALETTE['ink']}">{share(scored['label_accuracy'])}</dd>
            <dt>What the loop would do next</dt>
            <dd style="margin:0;color:{PALETTE['ink']}">{next_step(outcome)}</dd>
          </dl>
        </div>
        """

    mo.Html(figure_block(outcome))
    return figure_block, next_step, share


@app.cell
def _(PALETTE, mo, outcome):
    def finding_card(finding):
        return f"""
        <li style="padding:0.75rem 0.9rem;background:{PALETTE['sheet']};
                   border-radius:0.5rem;
                   box-shadow:inset 3px 0 0 {PALETTE['problem']};
                   margin-bottom:0.4rem;list-style:none">
          <div style="color:{PALETTE['ink']};font-weight:600">{finding.title}</div>
          <div style="color:{PALETTE['muted']};font-size:0.875rem;margin-top:0.2rem">
            {finding.detail}
          </div>
          <div style="color:{PALETTE['faint']};font-size:0.8125rem;margin-top:0.2rem">
            {finding.citation.display()}
          </div>
        </li>
        """

    def nothing_found(outcome):
        if outcome.result.findings:
            return "Every check that ran on this room passed."
        return "No checks are enabled, so nothing has been measured yet."

    def findings_list(outcome):
        problems = outcome.result.problems
        passed = [f for f in outcome.result.findings if f.outcome == "passes"]
        cards = "".join(finding_card(finding) for finding in problems) or (
            f'<p style="color:{PALETTE["muted"]};margin:0">{nothing_found(outcome)}</p>'
        )
        return f"""
        <ul style="padding:0;margin:0">{cards}</ul>
        <p style="color:{PALETTE['faint']};font-size:0.875rem;margin-top:0.6rem">
          {len(passed)} other measurements came back inside their limit.
        </p>
        """

    mo.Html(findings_list(outcome))
    return finding_card, findings_list, nothing_found


@app.cell
def _(mo):
    mo.md("""## Where it changes""")
    return


@app.cell
def _(KNOBS, knob_label, mo):
    swept_knob = mo.ui.dropdown(
        options={knob_label(knob): knob for knob in KNOBS},
        value="Gap between the display cases",
        label="Sweep",
    )
    steps = mo.ui.slider(
        5, 25, 1, value=13, label="Readings across the range", show_value=True
    )
    mo.hstack([swept_knob, steps], gap=2, justify="start")
    return steps, swept_knob


@app.cell
def _(configuration, knobs, parked, steps, swept, swept_knob):
    sweep = swept(
        parked(knobs, swept_knob.value),
        swept_knob.value,
        steps.value,
        configuration,
    )
    return (sweep,)


@app.cell
def _(scenarios):
    def spans(samples):
        """Merge consecutive readings that said the same thing.

        A verdict is only known at the settings the sweep visited, so a change
        is drawn at the midpoint between the two readings that bracket it.
        """
        runs = []
        for value, verdict in samples:
            if runs and runs[-1][2] == verdict:
                runs[-1][1] = value
            else:
                runs.append([value, value, verdict])
        return [
            (
                first if index == 0 else (runs[index - 1][1] + first) / 2,
                last if index == len(runs) - 1 else (last + runs[index + 1][0]) / 2,
                verdict,
            )
            for index, (first, last, verdict) in enumerate(runs)
        ]

    def read_sweep(sweep, knob):
        """Each check, and what it said at every setting the sweep visited.

        Checks that only ever asked a question are left out. Those are the
        things a scan cannot see, they are the same for every room, and a row
        that never changes is a row that says nothing here.
        """
        said = {}
        for moved, outcome in sweep:
            setting = getattr(moved, knob)
            for check, verdict in scenarios.verdicts(outcome).items():
                said.setdefault(check, []).append((setting, verdict))
        return {
            check: spans(samples)
            for check, samples in said.items()
            if {verdict for _, verdict in samples} - {"question"}
        }

    return read_sweep, spans


@app.cell
def _(load_pack):
    CHART = {
        "width": 720,
        "left": 320,
        "right": 706,
        "top": 48,
        "row": 27,
        "bar": 13,
    }

    TITLES = {rule.id: rule.title for rule in load_pack().rules}

    def rule_title(check):
        return TITLES.get(check, check.replace("_", " "))

    def geometry(count):
        """Where the rows, the baseline and the two label lines sit."""
        baseline = CHART["top"] + count * CHART["row"] + 6
        return {
            **CHART,
            "baseline": baseline,
            "ticks": baseline + 18,
            "caption": baseline + 37,
            "height": baseline + 46,
        }

    def scale(domain):
        lowest, highest = domain
        width = CHART["right"] - CHART["left"]
        return lambda value: CHART["left"] + width * (value - lowest) / (
            highest - lowest
        )

    return CHART, geometry, rule_title, scale


@app.cell
def _(PALETTE, geometry, rule_title, scale):
    def band(place, row, verdict, x0, x1):
        top = place["top"] + row * place["row"]
        width = max(x1 - x0 - 2, 1)
        if verdict == "problem":
            y = top + (place["row"] - place["bar"]) / 2
            return (
                f'<rect x="{x0 + 1:.1f}" y="{y:.1f}" width="{width:.1f}" '
                f'height="{place["bar"]}" rx="4" fill="{PALETTE["problem"]}" />'
            )
        colour = PALETTE["pass"] if verdict == "passes" else PALETTE["faint"]
        return (
            f'<rect x="{x0 + 1:.1f}" y="{top + place["row"] / 2 - 1.5:.1f}" '
            f'width="{width:.1f}" height="3" rx="1.5" fill="{colour}" />'
        )

    def row_label(place, index, check, demoted):
        y = place["top"] + index * place["row"] + place["row"] / 2 + 4
        colour = PALETTE["faint"] if demoted else PALETTE["ink"]
        return (
            f'<text x="0" y="{y:.1f}" font-size="13" fill="{colour}">'
            f"{rule_title(check)}</text>"
        )

    def tick_values(domain):
        lowest, highest = domain
        step = 6 if highest - lowest > 24 else 4
        first = step * (int(lowest) // step + 1)
        return [lowest, *range(first, int(highest), step), highest]

    def axis(place, domain, at, title):
        ticks = "".join(
            f'<text x="{at(value):.1f}" y="{place["ticks"]:.1f}" font-size="12" '
            f'fill="{PALETTE["faint"]}" text-anchor="middle" '
            f'style="font-variant-numeric:tabular-nums">{value:g}</text>'
            for value in tick_values(domain)
        )
        middle = (place["left"] + place["right"]) / 2
        return (
            f'<line x1="{place["left"]}" y1="{place["baseline"]:.1f}" '
            f'x2="{place["right"]}" y2="{place["baseline"]:.1f}" '
            f'stroke="{PALETTE["rule"]}" stroke-width="1" />{ticks}'
            f'<text x="{middle:.1f}" y="{place["caption"]:.1f}" font-size="12" '
            f'fill="{PALETTE["muted"]}" text-anchor="middle">{title}</text>'
        )

    return axis, band, row_label, tick_values


@app.cell
def _(PALETTE, axis, band, geometry, row_label, scale):
    def ordered(rows):
        """What changes first, then what is always wrong, then what is fine."""
        def rank(row):
            check, spans = row
            verdicts = {verdict for _, _, verdict in spans}
            return (len(spans) == 1, "problem" not in verdicts, check)

        return sorted(rows.items(), key=rank)

    def guide(place, value, at, colour, y, label, dashes):
        """A reference line, haloed in the page colour so it stays legible
        where it crosses a bar."""
        x = at(value)
        line = (
            f'<line x1="{x:.1f}" y1="{place["top"] - 6:.1f}" x2="{x:.1f}" '
            f'y2="{place["baseline"]:.1f}" stroke="%s" stroke-width="%s" %s />'
        )
        return (
            line % (PALETTE["paper"], "4", "")
            + line % (colour, "1.5", dashes)
            + f'<text x="{x:.1f}" y="{y:.1f}" font-size="12" '
            f'fill="{colour}" text-anchor="middle">{label}</text>'
        )

    def guides(place, at, here, required):
        drawn = guide(
            place, here, at, PALETTE["accent"], place["top"] - 14,
            f"{here:g} in now", 'stroke-dasharray="3 3"',
        )
        if required is None:
            return drawn
        return (
            guide(
                place, required, at, PALETTE["ink"], place["top"] - 30,
                f"{required:g} in asked for", "",
            )
            + drawn
        )

    def chart(rows, domain, here, required, title, description):
        placed = ordered(rows)
        place = geometry(len(placed))
        at = scale(domain)
        bands = "".join(
            band(place, index, verdict, at(x0), at(x1))
            for index, (_, spans) in enumerate(placed)
            for x0, x1, verdict in spans
        )
        labels = "".join(
            row_label(place, index, check, demoted(spans))
            for index, (check, spans) in enumerate(placed)
        )
        return (
            f'<svg viewBox="0 0 {place["width"]} {place["height"]:.0f}" '
            f'width="100%" role="img" aria-label="{description}" '
            f'style="max-width:{place["width"]}px;overflow:visible">'
            f"<title>{description}</title>{bands}{labels}"
            f"{guides(place, at, here, required if inside(required, domain) else None)}"
            f"{axis(place, domain, at, title)}</svg>"
        )

    def demoted(spans):
        return len(spans) == 1 and spans[0][2] != "problem"

    def inside(value, domain):
        return value is not None and domain[0] <= value <= domain[1]

    return chart, demoted, guide, guides, inside, ordered


@app.cell
def _(PALETTE):
    LEGEND = (
        ("Reported a problem", PALETTE["problem"], 6),
        ("Inside its limit", PALETTE["pass"], 3),
        ("Nothing to measure", PALETTE["faint"], 3),
    )

    def legend(shown):
        marks = "".join(
            f'<span style="display:inline-flex;align-items:center;gap:0.4rem">'
            f'<span style="width:18px;height:{height}px;border-radius:3px;'
            f'background:{colour}"></span>{name}</span>'
            for name, colour, height in LEGEND
            if colour in shown
        )
        return (
            f'<div style="display:flex;gap:1.5rem;font-size:0.875rem;'
            f'color:{PALETTE["muted"]};margin-bottom:0.5rem;flex-wrap:wrap">'
            f"{marks}</div>"
        )

    return (legend,)


@app.cell
def _(
    PALETTE,
    bounds,
    chart,
    knob_label,
    knobs,
    legend,
    mo,
    read_sweep,
    scenarios,
    sweep,
    swept_knob,
):
    def cited_inches(knob):
        """The number to draw the reference line at, when there is one.

        The line lands where the standard puts it rather than where a reading
        fell. It is only drawn when this knob is the thing its check measures:
        walking in from the street makes the doorway the pinch, so crossing
        403.5.1's 36 in on an aisle axis would change nothing and the line
        would be pointing at the wrong dimension.
        """
        pinned = scenarios.PINS[knob]
        if pinned not in scenarios.expected_inches(knobs):
            return None
        for _, outcome in sweep:
            for finding in outcome.result.findings:
                if finding.check_id == pinned and finding.required_inches:
                    return finding.required_inches
        return None

    def shown_colours(rows):
        verdicts = {v for spans in rows.values() for _, _, v in spans}
        return {
            PALETTE["problem"] if verdict == "problem" else
            PALETTE["pass"] if verdict == "passes" else PALETTE["faint"]
            for verdict in verdicts
        }

    def sweep_view():
        knob = swept_knob.value
        rows = read_sweep(sweep, knob)
        name = knob_label(knob).lower()
        return mo.vstack(
            [
                mo.md(
                    "Each row is a check. Its bar covers the settings it "
                    "reported a problem at."
                ),
                mo.Html(legend(shown_colours(rows))),
                mo.Html(
                    chart(
                        rows,
                        bounds(knob),
                        getattr(knobs, knob),
                        cited_inches(knob),
                        f"{knob_label(knob)} (inches)",
                        f"What each check said as the {name} changes.",
                    )
                ),
            ],
            gap=0.5,
        )

    sweep_view()
    return cited_inches, shown_colours, sweep_view


@app.cell
def _(mo):
    mo.md("""## What we could not answer""")
    return


@app.cell
def _(PALETTE, mo, nothing_verified, outcome, preview, rule_title, scenarios):
    def open_items(outcome):
        questions = "".join(
            f'<li style="margin-bottom:0.3rem">{finding.title}<span '
            f'style="color:{PALETTE["faint"]}"> — {finding.detail}</span></li>'
            for finding in outcome.result.questions
        )
        waiting = "".join(
            f'<li style="margin-bottom:0.3rem">{rule_title(check)}<span '
            f'style="color:{PALETTE["faint"]}"> — waiting on {reason}</span></li>'
            for check, reason in sorted(scenarios.held(outcome).items())
        )
        return f"""
        <div style="font-size:0.9375rem;color:{PALETTE['muted']}">
          <p style="color:{PALETTE['ink']};margin:0 0 0.4rem">
            Things a scan cannot see, which somebody has to answer.
          </p>
          <ul style="margin:0 0 1rem;padding-left:1.1rem">{questions}</ul>
          <p style="color:{PALETTE['ink']};margin:0 0 0.4rem">
            Rules this room did not settle.
          </p>
          <ul style="margin:0;padding-left:1.1rem">{waiting}</ul>
        </div>
        """

    reviewer_note = (
        mo.md(
            "Nobody has read a section on this machine yet, so these numbers "
            "come from thresholds no reviewer has confirmed. "
            '`standardphysics-agents rules review --by "<name>"` is where '
            "that happens."
        )
        if nothing_verified and preview.value
        else mo.md("")
    )

    mo.vstack([mo.Html(open_items(outcome)), preview, reviewer_note], gap=0.75)
    return open_items, reviewer_note


if __name__ == "__main__":
    app.run()
