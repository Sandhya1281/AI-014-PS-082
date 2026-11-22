# MEMBER 1 - registry: generators, entities, REC issuance, lots, expiry, FIFO.
#
# A "lot" is one batch of certificates held by one owner:
#   {"id", "owner", "category", "vintage" (like "2025-03"), "qty"}
# If the same owner already has a lot with the same category and vintage, we add to it.

from ledger import config
from ledger.state import category_of, check_month, vintage_end_plus, to_decimal, to_units


# ---------- registration ----------

def register_generator(state, gen_id, technology, capacity_mw, accredited_on, audited=False):
    if gen_id in state["generators"]:
        raise ValueError(f"Generator {gen_id} already registered")
    technology = technology.lower()
    if technology not in config.VALID_TECHNOLOGIES:
        raise ValueError(f"Invalid technology '{technology}' (use solar, wind or biomass)")
    capacity = to_decimal(capacity_mw, "capacity")
    if capacity <= 0:
        raise ValueError("Capacity must be positive")

    gen = {"id": gen_id, "technology": technology, "capacity_mw": capacity,
           "accredited_on": accredited_on, "audited": bool(audited)}
    state["generators"][gen_id] = gen
    return gen


def register_entity(state, ent_id, consumption_mwh, rpo_percent=None):
    if ent_id in state["entities"]:
        raise ValueError(f"Entity {ent_id} already registered")
    consumption = to_decimal(consumption_mwh, "consumption")
    if consumption <= 0:
        raise ValueError("Annual consumption must be positive")

    rpo = None
    if rpo_percent is not None:
        rpo = to_decimal(rpo_percent, "rpo")
    ent = {"id": ent_id, "consumption_mwh": consumption, "rpo_percent": rpo,
           "carry_forward_used": False}
    state["entities"][ent_id] = ent
    return ent


def set_audit_flag(state, gen_id, flag):
    if gen_id not in state["generators"]:
        raise ValueError(f"Unknown generator {gen_id}")
    state["generators"][gen_id]["audited"] = bool(flag)


# ---------- issuance records ----------

def find_issuance(state, issue_id):
    for rec in state["issuances"]:
        if rec["id"] == issue_id:
            return rec
    return None


def new_issuance(state, issue_id, kind, gen_id, month, qty):
    if issue_id is None:
        issue_id = "I" + str(state["next_issuance_id"])
    state["next_issuance_id"] += 1
    if find_issuance(state, issue_id) is not None:
        raise ValueError(f"Issuance {issue_id} already exists")
    rec = {"id": issue_id, "kind": kind, "generator": gen_id, "month": month,
           "qty": qty, "to_generator": qty, "buffer_held": 0, "reversed": False}
    state["issuances"].append(rec)
    return rec


def issue_rec(state, gen_id, month, mwh, applied_on, issue_id=None):
    """BR-01. Returns a dict with a "status": ISSUED, LAPSED, AUDIT_REQUIRED or ZERO_UNITS."""
    if gen_id not in state["generators"]:
        raise ValueError(f"Unknown generator {gen_id}")
    gen = state["generators"][gen_id]
    month = check_month(month)
    units = to_units(mwh)                      # 1 REC per whole MWh, fraction is dropped

    # must apply within 6 months after the generation month
    deadline = vintage_end_plus(month, config.ISSUANCE_WINDOW_MONTHS)
    if applied_on > deadline:
        return {"status": "LAPSED", "units": units, "issuance": None,
                "message": f"applied {applied_on}, deadline was {deadline}; units lapse"}

    # a generator accredited for less than a year needs its audit flag
    age_days = (applied_on - gen["accredited_on"]).days
    if age_days < config.AUDIT_FREE_DAYS and not gen["audited"]:
        return {"status": "AUDIT_REQUIRED", "units": units, "issuance": None,
                "message": "accredited less than one year and audit flag not set"}

    if units == 0:
        return {"status": "ZERO_UNITS", "units": 0, "issuance": None,
                "message": "less than 1 MWh, nothing to issue"}

    rec = new_issuance(state, issue_id, "REC", gen_id, month, units)
    category = category_of(gen["technology"])
    add_lot(state, gen_id, category, month, units)
    return {"status": "ISSUED", "units": units, "issuance": rec, "message": ""}


# ---------- lots ----------

def find_lot(state, owner, category, vintage):
    for lot in state["lots"]:
        if lot["owner"] == owner and lot["category"] == category and lot["vintage"] == vintage:
            return lot
    return None


def add_lot(state, owner, category, vintage, qty):
    if qty <= 0:
        return
    lot = find_lot(state, owner, category, vintage)
    if lot is not None:
        lot["qty"] += qty
        return
    new_lot = {"id": state["next_lot_id"], "owner": owner, "category": category,
               "vintage": vintage, "qty": qty}
    state["next_lot_id"] += 1
    state["lots"].append(new_lot)


def drop_empty_lots(state):
    kept = []
    for lot in state["lots"]:
        if lot["qty"] > 0:
            kept.append(lot)
    state["lots"] = kept


# ---------- expiry (BR-04) ----------

def expiry_date(vintage):
    """Last valid day = end of the vintage month + 36 months."""
    return vintage_end_plus(vintage, config.EXPIRY_MONTHS)


def is_expired(lot, on_date):
    """Valid ON the expiry date, expired from the next day. Carbon credits never expire."""
    if on_date is None:
        return False
    if lot["category"] == config.CARBON:
        return False
    return on_date > expiry_date(lot["vintage"])


def expire_lots(state, on_date):
    """Remove expired lots, unless an open sell order could need one.

    A session's trade date determines whether a certificate is valid. Keeping a
    potentially committed lot until its session closes avoids deleting it before
    the auction can transfer it (BR-04, BR-11).
    """
    for order in state["orders"].values():
        if order["status"] != "open" or order["side"] != "sell":
            continue
        session = state["sessions"].get(order["session"])
        if session is None or session["status"] != "open":
            continue
        for lot in state["lots"]:
            if lot["owner"] == order["member"] and lot["category"] == order["category"]:
                if is_expired(lot, on_date):
                    raise ValueError(
                        f"Cannot expire {lot['category']} lots for {order['member']} "
                        f"while sell order {order['id']} is open; close or cancel the session first"
                    )

    removed = []
    kept = []
    for lot in state["lots"]:
        if is_expired(lot, on_date):
            removed.append(lot)
        else:
            kept.append(lot)
    state["lots"] = kept
    return removed


# ---------- holdings ----------

def holdings(state, owner, category, on_date):
    """How many unexpired certificates the owner has (on_date=None means ignore expiry)."""
    total = 0
    for lot in state["lots"]:
        if lot["owner"] == owner and lot["category"] == category:
            if not is_expired(lot, on_date):
                total += lot["qty"]
    return total


def open_sell_qty(state, owner, category):
    """Units already offered in this owner's open sell orders."""
    total = 0
    for order in state["orders"].values():
        if order["status"] == "open" and order["side"] == "sell":
            if order["member"] == owner and order["category"] == category:
                total += order["qty"]
    return total


def free_holdings(state, owner, category, on_date):
    """Unencumbered holdings = holdings minus units in open sell orders (BR-11)."""
    return holdings(state, owner, category, on_date) - open_sell_qty(state, owner, category)


# ---------- FIFO (BR-04) ----------

def take_fifo(state, owner, category, qty, on_date):
    """Remove qty certificates from the owner, oldest vintage first.
    Returns a list like [("2024-01", 10), ("2025-02", 5)]."""
    if qty > holdings(state, owner, category, on_date):
        raise ValueError(f"{owner} does not hold {qty} unexpired {category} certificates")

    # collect the owner's usable lots and sort them: oldest vintage first
    lots = []
    for lot in state["lots"]:
        if lot["owner"] == owner and lot["category"] == category:
            if not is_expired(lot, on_date):
                lots.append(lot)
    lots.sort(key=lambda lot: (lot["vintage"], lot["id"]))

    taken = []
    still_needed = qty
    for lot in lots:
        if still_needed == 0:
            break
        take = min(lot["qty"], still_needed)
        lot["qty"] -= take
        still_needed -= take
        taken.append((lot["vintage"], take))
    drop_empty_lots(state)
    return taken


def transfer_fifo(state, seller, buyer, category, qty, trade_date):
    """Move qty certificates from seller to buyer, oldest first. Vintage stays the same."""
    taken = take_fifo(state, seller, category, qty, trade_date)
    for vintage, amount in taken:
        add_lot(state, buyer, category, vintage, amount)
    return taken
