# Decision Log

Type: ASSUMPTION = our proposal where the brief is silent or ambiguous (confirm with the faculty
or the official sample data); DECISION = a design choice that does not change a business rule.
Nothing here is an official fact.

| ID | Type | Topic | Decision | Where |
|---|---|---|---|---|
| A-01 | ASSUMPTION | Vintage and deadlines | Vintage = generation month. The six-month application window ends on the last day of the sixth month after it (March 2025 generation: last day 30 Sep 2025). Expiry = last day of (vintage month + 36 months); a trade on that day is valid. | registry.issue_rec, expiry_date |
| A-02 | ASSUMPTION | Buffer rounding | 5% buffer is rounded DOWN to whole credits (39 credits -> buffer 1). Generator receives credits minus buffer. | carbon.buffer_amount |
| A-03 | ASSUMPTION | Buffer release | Buffer of an issuance is released when that issuance and the next two carbon issuances of the same generator are all unreversed. Released credits go to the generator's holdings. | carbon.release_buffers |
| A-04 | ASSUMPTION | Carbon credits | Carbon credits are held in the registry but not traded in sessions and do not expire (the brief gives a price band and expiry only for RECs). | orders (categories), registry.is_expired |
| A-05 | ASSUMPTION | "Before 31 March" | Retirements dated on or before 31 March count for the year ending that 31 March. Compliance year is named by the year it ends (FY2026 = 1 Apr 2025 to 31 Mar 2026). | state.fiscal_year |
| A-06 | ASSUMPTION | RPO targets | Solar 10% and non-solar 15% of annual consumption are fixed constants. The entity's own "RPO target percentage" is stored but not used for the targets. Target units are rounded UP to a whole certificate. | compliance.targets |
| A-07 | ASSUMPTION | Carry-forward | "Once" = once per entity. In the year it is used, every category with at least 90% retired and a shortfall is carried and added to the next year's target. A carried shortfall cannot be carried again. | compliance.close_year |
| A-08 | ASSUMPTION | Reversal price | REC reversal uses the last clearing price of its category; carbon reversal uses the most recent clearing price of any market. If no price exists, the deficit is recorded as unpriced units and no rupee amount is invented. Reversal applies to both REC and carbon issuances. | carbon.reverse_issuance |
| A-09 | ASSUMPTION | Clearing price | For each order price p: demand(p) = buy quantity at or above p, supply(p) = sell quantity at or below p. Price = the lowest p that maximises min(demand, supply). When cumulative buy equals cumulative sell at several prices, the lowest wins (edge case 1). | auction.find_clearing |
| A-10 | ASSUMPTION | Residual units | After rounding down the pro-rata share at the marginal price, residual units stay unfilled. So that certificates delivered equal certificates received, the opposite side is trimmed from its lowest-priority orders. | auction.balance |
| A-11 | ASSUMPTION | Forbearance | Order prices are in band at entry, so the cap is a safety path: if a clearing price above 3000 ever arises, price = 3000, all sells at or below 3000 clear, buys are pro-rated by quantity. | auction.clear_at_forbearance |
| A-12 | DECISION | Priority | Equal prices are ordered by entry sequence; pro-rata applies only to the marginal price level. Solar and non-solar are cleared as separate markets in one session. | auction.sort_buys, sort_sells |
| A-13 | ASSUMPTION | Fees | Each fee component is rounded to paise (half up). GST is charged to each party on its own fees. T+1 means the next calendar day. Fees apply per fill. | accounts.calculate_fees |
| A-14 | ASSUMPTION | Fee shortfall | Cash never goes negative. If available funds cannot pay a fee, the unpaid amount is kept as `fee_due` and collected from the next available funds. Fees are debited before seller proceeds are credited. | accounts.settle_due |
| A-15 | ASSUMPTION | Margin | Margin = quantity x limit price. On fill the buyer pays the clearing price; the remainder of the margin is released. | accounts.convert_margin |
| A-16 | ASSUMPTION | Audit age | "Accredited for less than one year" = fewer than 365 days between accreditation and the application date. A rejected application is not queued; apply again after setting the audit flag. | registry.issue_rec |
| A-17 | DECISION | Rejected orders | Rule violations at entry are stored with status `rejected` and a reason (nothing blocked); malformed input raises an error. | orders.place_order |
| D-18 | DECISION | Code style | Plain functions and dictionaries, one shared state dict, Decimal for money, int for certificates. No classes, so each function can be explained and changed live. | all |
| D-19 | DECISION | Input format | Our own `COMMAND key=value` format because official files were not available. Only parser.py (parse_line, run_command) needs to change. | parser.py |
| D-20 | DECISION | Expiry with open sell orders | Expiry refuses to remove an expiring lot when an open sell order for that owner/category exists in an open session. Close or cancel the session, then retry expiry. This preserves certificates needed by a trade valid on its session date. | registry.expire_lots |
