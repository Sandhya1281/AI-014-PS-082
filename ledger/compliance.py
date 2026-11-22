# MEMBER 1 - retirement, RPO targets, penalties, carry-forward (BR-03, BR-09).
#
# A compliance year runs 1 April to 31 March and is named by the year it ends in
# (FY2026 = 1 April 2025 to 31 March 2026).

from decimal import Decimal, ROUND_CEILING

from ledger import config, registry
from ledger.state import fiscal_year


def target_units(consumption_mwh, rate):
    """Target = consumption x RPO %, rounded UP to a whole certificate (assumption A-06)."""
    return int((consumption_mwh * rate).to_integral_value(rounding=ROUND_CEILING))


def carry_in(state, entity_id, fy):
    """Shortfall carried into this year from last year's close."""
    last_year = state["compliance"].get(fy - 1)
    if last_year is None or entity_id not in last_year:
        return {config.SOLAR: 0, config.NONSOLAR: 0}
    return last_year[entity_id]["carry_out"]


def targets(state, entity_id, fy):
    """Solar and non-solar target for this year (including carried shortfall)."""
    ent = state["entities"][entity_id]
    carried = carry_in(state, entity_id, fy)
    solar = target_units(ent["consumption_mwh"], config.SOLAR_RPO) + carried[config.SOLAR]
    nonsolar = target_units(ent["consumption_mwh"], config.NONSOLAR_RPO) + carried[config.NONSOLAR]
    return {config.SOLAR: solar, config.NONSOLAR: nonsolar}


def retired_toward(state, entity_id, fy, target_category):
    """Units retired by this entity in this year that count toward the given target."""
    total = 0
    for r in state["retirements"]:
        if r["entity"] == entity_id and r["fy"] == fy and r["against"] == target_category:
            total += r["qty"]
    return total


def retire(state, entity_id, category, qty, on_date, against=None):
    """Retire certificates of 'category' toward the 'against' target (default: same one).
    BR-03: non-solar can never count for solar.
           solar can count for non-solar only after the solar target is fully met."""
    if entity_id not in state["entities"]:
        raise ValueError(f"Unknown entity {entity_id}")
    if category not in config.REC_CATEGORIES:
        raise ValueError(f"Cannot retire category '{category}' against RPO")
    if against is None:
        against = category
    if against not in config.REC_CATEGORIES:
        raise ValueError(f"Invalid RPO target '{against}'")
    qty = int(qty)
    if qty <= 0:
        raise ValueError("Retirement quantity must be positive")

    fy = fiscal_year(on_date)

    if category == config.NONSOLAR and against == config.SOLAR:
        raise ValueError("BR-03: Non-Solar REC can never satisfy a solar shortfall")

    if category == config.SOLAR and against == config.NONSOLAR:
        solar_target = targets(state, entity_id, fy)[config.SOLAR]
        solar_done = retired_toward(state, entity_id, fy, config.SOLAR)
        if solar_done < solar_target:
            raise ValueError("BR-03: Solar REC can satisfy non-solar shortfall only after "
                             "the solar target is fully met")

    free = registry.free_holdings(state, entity_id, category, on_date)
    if qty > free:
        raise ValueError(f"Cannot retire {qty}: only {free} unexpired, unencumbered {category} held")

    registry.take_fifo(state, entity_id, category, qty, on_date)
    record = {"entity": entity_id, "category": category, "against": against,
              "qty": qty, "date": on_date, "fy": fy}
    state["retirements"].append(record)
    return record


def close_year(state, fy):
    """Work out shortfall, carry-forward and penalty for every entity. Once per year."""
    if fy in state["compliance"]:
        raise ValueError(f"Compliance year {fy} already closed")

    results = {}
    for ent_id in sorted(state["entities"]):
        ent = state["entities"][ent_id]
        target_by_cat = targets(state, ent_id, fy)
        can_carry = not ent["carry_forward_used"]      # carry-forward is allowed only once

        result = {"entity": ent_id, "fy": fy,
                  "carry_out": {config.SOLAR: 0, config.NONSOLAR: 0}}
        penalty_units_total = 0

        for cat in config.REC_CATEGORIES:
            target = target_by_cat[cat]
            retired = retired_toward(state, ent_id, fy, cat)
            shortfall = max(0, target - retired)

            # retired at least 90% of the target? (exactly 90% counts)
            reached_90 = target > 0 and Decimal(retired) >= Decimal(target) * config.CARRY_FORWARD_MIN

            carried = 0
            if shortfall > 0 and can_carry and reached_90:
                carried = shortfall
                result["carry_out"][cat] = carried

            penalty_units = shortfall - carried
            penalty_units_total += penalty_units
            result[cat] = {"target": target, "retired": retired, "shortfall": shortfall,
                           "carried": carried, "penalty_units": penalty_units}

        if result["carry_out"][config.SOLAR] > 0 or result["carry_out"][config.NONSOLAR] > 0:
            ent["carry_forward_used"] = True

        result["penalty"] = penalty_units_total * config.FORBEARANCE_PRICE
        results[ent_id] = result

    state["compliance"][fy] = results
    return results
