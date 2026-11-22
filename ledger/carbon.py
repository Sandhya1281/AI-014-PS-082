# MEMBER 1 - carbon credits: issuance, 5% buffer pool, buffer release, reversal (BR-02, BR-10).

from decimal import Decimal, ROUND_FLOOR

from ledger import accounts, config, registry
from ledger.state import ZERO, category_of, check_month, to_units


def buffer_amount(credits):
    """5% of the credits, rounded DOWN to a whole number (our assumption A-02)."""
    five_percent = Decimal(credits) * config.BUFFER_RATE
    return int(five_percent.to_integral_value(rounding=ROUND_FLOOR))


def buffer_pool_total(state, gen_id):
    """Total buffer credits still withheld for this generator."""
    total = 0
    for rec in state["issuances"]:
        if rec["kind"] == "CARBON" and rec["generator"] == gen_id:
            total += rec["buffer_held"]
    return total


def issue_carbon(state, gen_id, month, tonnes, issue_id=None):
    if gen_id not in state["generators"]:
        raise ValueError(f"Unknown generator {gen_id}")
    month = check_month(month)
    credits = to_units(tonnes)                 # 1 credit per tonne, fraction dropped
    if credits == 0:
        raise ValueError("Less than one tonne verified, nothing to issue")

    buffer = buffer_amount(credits)
    to_generator = credits - buffer

    rec = registry.new_issuance(state, issue_id, "CARBON", gen_id, month, credits)
    rec["to_generator"] = to_generator
    rec["buffer_held"] = buffer
    registry.add_lot(state, gen_id, config.CARBON, month, to_generator)

    released = release_buffers(state, gen_id)
    return {"issuance": rec, "to_generator": to_generator, "buffer": buffer,
            "released": released}


def release_buffers(state, gen_id):
    """The buffer of an issuance is released when that issuance and the next two
    issuances of the same generator have all NOT been reversed (3 in a row)."""
    issues = []
    for rec in state["issuances"]:
        if rec["kind"] == "CARBON" and rec["generator"] == gen_id:
            issues.append(rec)

    needed = config.CLEAN_ISSUANCES_FOR_RELEASE
    released = 0
    for i in range(len(issues)):
        rec = issues[i]
        if rec["buffer_held"] == 0:
            continue
        window = issues[i:i + needed]
        if len(window) < needed:
            continue                           # not enough issuances yet
        reversed_found = False
        for r in window:
            if r["reversed"]:
                reversed_found = True
        if reversed_found:
            continue
        registry.add_lot(state, gen_id, config.CARBON, rec["month"], rec["buffer_held"])
        released += rec["buffer_held"]
        rec["buffer_held"] = 0
    return released


def reverse_issuance(state, issuance_id):
    """BR-10. Three steps:
       1) cancel the generator's untraded units
       2) use buffer pool credits (carbon only)
       3) whatever is left is owed in rupees at the last clearing price
    Units that were already retired or sold are NOT taken back."""
    rec = registry.find_issuance(state, issuance_id)
    if rec is None:
        raise ValueError(f"Unknown issuance {issuance_id}")
    if rec["reversed"]:
        raise ValueError(f"Issuance {issuance_id} already reversed")

    gen_id = rec["generator"]
    if rec["kind"] == "CARBON":
        category = config.CARBON
        price_key = "any"
    else:
        category = category_of(state["generators"][gen_id]["technology"])
        price_key = category

    # step 1: untraded units = what the generator still holds from this issuance
    lot = registry.find_lot(state, gen_id, category, rec["month"])
    in_lot = 0
    if lot is not None:
        in_lot = lot["qty"]
    free = registry.free_holdings(state, gen_id, category, None)
    untraded = min(rec["to_generator"], in_lot, free)
    if lot is not None:
        lot["qty"] -= untraded
        registry.drop_empty_lots(state)
    remaining = rec["qty"] - untraded

    # step 2: buffer pool (this issuance's own buffer first, then the others)
    buffer_used = 0
    if rec["kind"] == "CARBON":
        pool = [rec]
        for r in state["issuances"]:
            if r["kind"] == "CARBON" and r["generator"] == gen_id and r is not rec:
                pool.append(r)
        for r in pool:
            take = min(r["buffer_held"], remaining)
            r["buffer_held"] -= take
            remaining -= take
            buffer_used += take

    # step 3: the rest is owed in rupees
    deficit = remaining
    price = state["last_clearing_price"][price_key]
    if deficit == 0:
        amount = ZERO
    elif price is None:
        amount = None                          # no price yet: keep it as units (A-08)
    else:
        amount = deficit * price
    if deficit > 0:
        accounts.record_reversal_debt(state, gen_id, amount, deficit)

    rec["reversed"] = True
    shown_price = None
    if deficit > 0:
        shown_price = price
    result = {"issuance": issuance_id, "kind": rec["kind"], "generator": gen_id,
              "reversed_units": rec["qty"], "cancelled_untraded": untraded,
              "buffer_used": buffer_used, "deficit_units": deficit,
              "price": shown_price, "amount_owed": amount}
    state["reversals"].append(result)
    return result
