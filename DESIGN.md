# DESIGN - AI-014-PS-082 Renewable Energy Certificate and Carbon Credit Trading Ledger

Team AI-014, Problem Statement PS-082, Domain: Energy - Carbon Markets, Difficulty: High. Python 3.10+.
Diagrams are Mermaid; sources are in `docs/diagrams/` and are copied below.

## 1. Project overview
A command-file-driven registry and settlement engine for a carbon exchange. It registers generators
and obligated entities, issues RECs and carbon credits, runs uniform-price double auctions for
RECs, moves certificates FIFO, charges fees through member accounts, retires certificates against
Renewable Purchase Obligations (RPO), and prints registry, session and compliance reports.

## 2. Problem statement
Build a backend that processes a command file and applies 11 business rules (BR-01 to BR-11)
correctly, including eight mandatory edge cases. It must reproduce expected results for four
sample trading sessions and handle two hidden sessions.

## 3. Scope
In scope: registration, REC and carbon issuance, buffer pool, trading sessions, clearing, FIFO
transfer, fees and T+1 settlement, retirement, compliance and penalties, expiry, reversal, reports.
Out of scope: user interface, web service, database, authentication, real payment integration,
carbon credit trading (assumption A-04).

## 4. Functional requirements
1. Register generators (technology, capacity MW, accreditation date) and entities (annual MWh, RPO).
2. Issue RECs from metered generation (BR-01) and carbon credits from verified reductions (BR-02).
3. Accept buy and sell orders in sessions with validation (BR-06, BR-08, BR-11).
4. Clear a uniform-price double auction under floor and forbearance prices (BR-05, BR-06).
5. Transfer certificates FIFO by vintage (BR-04).
6. Charge fees and settle funds through member accounts (BR-07, BR-08).
7. Retire certificates against RPO and compute compliance, shortfall penalties and carry-forward (BR-03, BR-09).
8. Expire certificates by vintage (BR-04). Reverse failed issuances (BR-10).
9. Print registry state, session results and compliance reports.

## 5. Non-functional requirements
- Correctness first: Decimal for money, integers for certificates, deterministic clearing.
- Simplicity: plain functions and dictionaries, small modules, one shared state dictionary.
- Testability: whole suite runs with one command; pure functions where possible.
- Portability: Python standard library only.
- Clear error messages: every rejection names its business rule.

## 6. Glossary
| Term | Meaning |
|---|---|
| REC | Renewable Energy Certificate, one per whole MWh of metered generation |
| Carbon credit | One per tonne CO2e of verified reduction |
| Buffer pool | 5% of each carbon issuance withheld until released |
| Vintage | Generation month of a certificate ('YYYY-MM') |
| RPO | Renewable Purchase Obligation: share of consumption to be met with RECs |
| Obligated entity | Consumer with an RPO target |
| Floor / forbearance price | Minimum (1000) / maximum (3000) rupees per REC |
| Uniform-price auction | All trades in a market clear at one price |
| Marginal price | Price level where supply and demand meet and orders are only partly filled |
| Pro-rata | Sharing a quantity in proportion to order sizes |
| Margin | Funds blocked to back a buy order |
| Encumbered | Held in an open sell order |
| T+1 | Settlement one day after the trade |
| Unencumbered holdings | Unexpired holdings not in open sell orders |
| Reversal | Cancelling an issuance after failed verification |

## 7. Entity descriptions
| Entity (state key) | Fields |
|---|---|
| Generator (`generators`) | id, technology, capacity_mw, accredited_on, audited |
| Entity (`entities`) | id, consumption_mwh, rpo_percent, carry_forward_used |
| Issuance (`issuances`) | id, kind (REC or CARBON), generator, month, qty, to_generator, buffer_held, reversed |
| Lot (`lots`) | id, owner, category (solar, nonsolar, carbon), vintage, qty |
| Account (`accounts`) | cash, blocked, fee_due, reversal_owed, unpriced_units |
| Session (`sessions`) | id, date, status, results |
| Order (`orders`) | id, session, member, side, category, qty, price, seq, status, margin, filled, reason |
| Settlement (`settlements`) | id, order, member, side, qty, price, value, settle_date, settled, fees |
| Retirement (`retirements`) | entity, category, against, qty, date, fy |
| Compliance result (`compliance`) | entity, fy, per-category target/retired/shortfall/carried, carry_out, penalty |
| Reversal (`reversals`) | issuance, reversed_units, cancelled_untraded, buffer_used, deficit_units, amount_owed |

## 8. Entity relationships
```mermaid
erDiagram
    GENERATOR ||--o{ ISSUANCE : has
    ISSUANCE ||--o{ LOT : creates
    MEMBER ||--o{ LOT : owns
    MEMBER ||--|| ACCOUNT : has
    ENTITY ||--o{ RETIREMENT : makes
    ENTITY ||--o{ COMPLIANCE_RESULT : receives
    SESSION ||--o{ ORDER : contains
    MEMBER ||--o{ ORDER : places
    ORDER ||--o| SETTLEMENT : produces
    ISSUANCE ||--o| REVERSAL : may_have
    GENERATOR {
        string id PK
        string technology
        decimal capacity_mw
        date accredited_on
        bool audited
    }
    ENTITY {
        string id PK
        decimal consumption_mwh
        bool carry_forward_used
    }
    ISSUANCE {
        string id PK
        string kind
        string generator FK
        string month
        int qty
        int buffer_held
        bool reversed
    }
    LOT {
        int id PK
        string owner FK
        string category
        string vintage
        int qty
    }
    ACCOUNT {
        string member PK
        decimal cash
        decimal blocked
        decimal fee_due
    }
    SESSION {
        string id PK
        date date
        string status
    }
    ORDER {
        string id PK
        string session FK
        string member FK
        string side
        string category
        int qty
        decimal price
        string status
    }
    SETTLEMENT {
        int id PK
        string order FK
        date settle_date
        decimal value
        bool settled
    }
    RETIREMENT {
        string entity FK
        string category
        string against
        int qty
        int fy
    }
    COMPLIANCE_RESULT {
        string entity FK
        int fy
        decimal penalty
    }
    REVERSAL {
        string issuance FK
        int cancelled_untraded
        int buffer_used
        int deficit_units
        decimal amount_owed
    }
```

A member is any id with an account: generators, entities, or other participants.

## 9. System architecture
```mermaid
flowchart TD
    CF["Command file"] --> MAIN["main.py"]
    MAIN --> PARSER["parser.py (shared)"]
    PARSER --> REP["reports.py (shared)"]
    subgraph M1["Member 1 - Registry and Compliance"]
        REG["registry.py"]
        CARB["carbon.py"]
        COMP["compliance.py"]
    end
    subgraph M2["Member 2 - Trading and Finance"]
        ORD["orders.py"]
        AUC["auction.py"]
        ACC["accounts.py"]
    end
    PARSER --> REG
    PARSER --> CARB
    PARSER --> COMP
    PARSER --> ORD
    PARSER --> AUC
    PARSER --> ACC
    CARB --> REG
    CARB --> ACC
    COMP --> REG
    ORD --> REG
    ORD --> ACC
    AUC --> REG
    AUC --> ACC
    STATE[("state dict - state.py")]
    CFG["config.py constants"]
    REG --- STATE
    ACC --- STATE
    ORD --- STATE
    AUC --- STATE
    CARB --- STATE
    COMP --- STATE
    REP --> OUT["Printed output"]
```

`parser.py` turns each command line into a call to one module. All modules share one state
dictionary created by `state.new_state()`.

## 10. UML class diagram
The code uses plain dictionaries, so the "classes" below document the record fields. Behaviour
lives in module functions (see Module_Ownership.md).

```mermaid
classDiagram
    %% Records are plain Python dicts; shown as classes to document their fields.
    class Generator {
        id
        technology
        capacity_mw
        accredited_on
        audited
    }
    class Entity {
        id
        consumption_mwh
        rpo_percent
        carry_forward_used
    }
    class Issuance {
        id
        kind REC or CARBON
        generator
        month
        qty
        to_generator
        buffer_held
        reversed
    }
    class Lot {
        id
        owner
        category
        vintage
        qty
    }
    class Account {
        cash
        blocked
        fee_due
        reversal_owed
        unpriced_units
    }
    class Session {
        id
        date
        status
        results
    }
    class Order {
        id
        session
        member
        side
        category
        qty
        price
        seq
        status
        margin
        filled
        reason
    }
    class Settlement {
        id
        order
        member
        side
        qty
        price
        value
        settle_date
        settled
        fees
    }
    class Retirement {
        entity
        category
        against
        qty
        date
        fy
    }
    class ComplianceResult {
        entity
        fy
        solar
        nonsolar
        carry_out
        penalty
    }
    Generator "1" --> "*" Issuance : issued for
    Issuance "1" --> "*" Lot : creates
    Generator "1" --> "0..1" Account : member id
    Entity "1" --> "0..1" Account : member id
    Account "1" --> "*" Lot : owns
    Session "1" --> "*" Order : contains
    Order "1" --> "0..1" Settlement : fill
    Entity "1" --> "*" Retirement : retires
    Entity "1" --> "*" ComplianceResult : assessed
```

## 11. State diagram and workflows

### Certificate lifecycle
```mermaid
stateDiagram-v2
    [*] --> Held : REC issued or bought
    Held --> Listed : sell order open (units counted as encumbered)
    Listed --> Held : order cancelled or unfilled
    Listed --> Transferred : order filled, FIFO transfer
    Transferred --> Held : buyer now holds the units
    Held --> Retired : RETIRE against RPO target
    Held --> Expired : after expiry day (36 months after vintage month end)
    Retired --> [*]
    Expired --> [*]
    Held --> Cancelled : issuance reversed, untraded units cancelled
    Cancelled --> [*]
```

### REC issuance (BR-01)
```mermaid
flowchart TD
    A["ISSUE_REC generator month mwh applied"] --> B{"Generator registered?"}
    B -- no --> X["Error: unknown generator"]
    B -- yes --> C["units = floor of MWh"]
    C --> D{"applied date after end of month + 6 months?"}
    D -- yes --> L["LAPSED - no units issued"]
    D -- no --> E{"accredited under 365 days and audit flag not set?"}
    E -- yes --> AU["AUDIT_REQUIRED - nothing issued"]
    E -- no --> F{"units = 0?"}
    F -- yes --> Z["ZERO_UNITS"]
    F -- no --> G["Create issuance record kind REC"]
    G --> H["add_lot: category from technology, vintage = generation month"]
    H --> I["ISSUED"]
```

### Carbon buffer (BR-02)
```mermaid
flowchart TD
    A["ISSUE_CARBON generator month tonnes"] --> B["credits = floor of tonnes"]
    B --> C["buffer = floor of 5 percent of credits"]
    C --> D["Generator lot gets credits minus buffer"]
    C --> E["Issuance buffer_held = buffer (buffer pool)"]
    D --> F["release_buffers for this generator"]
    E --> F
    F --> G{"For each carbon issuance i: issuances i, i+1, i+2 exist and none reversed?"}
    G -- yes --> H["Move buffer_held of issuance i into generator lot"]
    G -- no --> I["Buffer stays in pool"]
    J["Reversal of an issuance"] -. blocks release .-> G
```

### Auction trading (BR-05, BR-06, BR-07, BR-08)
```mermaid
flowchart TD
    A["SESSION_CLOSE"] --> B["For each market: solar, then nonsolar"]
    B --> C["Collect open orders, split buys and sells"]
    C --> D["Sort buys price descending, sells price ascending, ties by entry sequence"]
    D --> E["For every order price p: demand = buys at or above p, supply = sells at or below p, volume = min"]
    E --> F{"Any volume above 0?"}
    F -- no --> N["No trade: all orders unfilled, margins released"]
    F -- yes --> G["Clearing price = lowest p with the largest volume"]
    G --> H{"Price above forbearance 3000?"}
    H -- yes --> FB["Price = 3000, sells at or below 3000 clear, buys pro-rated"]
    H -- no --> I["Fill price levels in order; marginal level shared pro-rata, rounded down"]
    I --> J["Trim the larger side so buy fills equal sell fills"]
    FB --> K
    J --> K["Pair buys with sells, FIFO transfer of certificates"]
    K --> L["Buyers: margin converted to settlement, unfilled margin released"]
    L --> M["Create settlement records, settle date = trade date + 1"]
```

### FIFO transfer (BR-04)
```mermaid
flowchart TD
    A["transfer_fifo seller buyer category qty trade_date"] --> B["List seller lots of category that are not expired on trade_date"]
    B --> C{"Total units at least qty?"}
    C -- no --> X["Error: seller does not hold qty unexpired certificates"]
    C -- yes --> D["Sort lots by vintage ascending, then lot id"]
    D --> E["Take from oldest lot until qty is met"]
    E --> F["Remove empty lots"]
    F --> G["Add same vintage and quantity to buyer lots (merge if lot exists)"]
```

### Retirement and compliance (BR-03, BR-09)
```mermaid
flowchart TD
    A["RETIRE entity category qty date against"] --> B{"Non-solar certificate against solar target?"}
    B -- yes --> R1["Rejected BR-03"]
    B -- no --> C{"Solar certificate against non-solar target?"}
    C -- yes --> D{"Solar retired against solar target at least solar target?"}
    D -- no --> R2["Rejected BR-03"]
    D -- yes --> E
    C -- no --> E{"qty within free unexpired holdings?"}
    E -- no --> R3["Rejected"]
    E -- yes --> F["Remove certificates FIFO and record retirement with fiscal year"]
    F --> G["CLOSE_YEAR fy"]
    G --> H["target = ceil of consumption x RPO, plus carry-in"]
    H --> I["shortfall = target minus retired toward that target"]
    I --> J{"shortfall above 0, retired at least 90 percent of target, carry-forward not yet used?"}
    J -- yes --> K["Carry shortfall to next year, no penalty"]
    J -- no --> L["Penalty = shortfall x 3000"]
```

### Carbon reversal (BR-10)
```mermaid
flowchart TD
    A["REVERSE issuance"] --> B{"Exists and not already reversed?"}
    B -- no --> X["Error"]
    B -- yes --> C["Step 1: cancel generator's untraded units of that vintage and category"]
    C --> D{"Carbon issuance?"}
    D -- yes --> E["Step 2: use buffer pool credits, own buffer first"]
    D -- no --> F["No buffer for RECs"]
    E --> G{"Deficit remaining?"}
    F --> G
    G -- no --> H["Done, nothing owed"]
    G -- yes --> I{"Last clearing price exists?"}
    I -- yes --> J["Step 3: generator owes deficit x last clearing price"]
    I -- no --> K["Record unpriced deficit units"]
    C -.-> L["Retired or sold units are never clawed back"]
```

### Trade sequence
```mermaid
sequenceDiagram
    participant P as parser.py
    participant O as orders.py
    participant A as accounts.py
    participant R as registry.py
    participant U as auction.py
    P->>O: BUY / SELL place_order
    O->>R: free_holdings (sell orders)
    O->>A: block_margin (buy orders)
    O-->>P: order open or rejected
    P->>U: SESSION_CLOSE close_session
    U->>U: clear_market per category
    U->>R: transfer_fifo seller to buyer
    U->>A: convert_margin and add_settlement
    P->>A: SETTLE date (T+1)
    A->>A: debit fees first
    A->>A: credit seller proceeds, then collect dues
```

## 12. Business-rule register
See `Business_Rule_Register.md` for the full table (rule, code, owner, tests).

## 13. Module ownership
See `Module_Ownership.md`. Member 1: registry.py, carbon.py, compliance.py. Member 2: orders.py,
auction.py, accounts.py. Shared: config, state, parser, reports, main, edge-case tests.

## 14. Assumptions
Proposed, not official: see `Decision_Log.md` entries A-01 to A-17 (vintage and deadlines, buffer
rounding and release, carbon not traded, 31 March handling, RPO constants and rounding,
carry-forward once, reversal price source, clearing rule, residual trimming, forbearance guard,
fee rounding, fee shortfall, margin, audit age).

## 15. Design decisions
- One shared state dictionary instead of objects: simple to inspect and explain.
- `auction.clear_market` is a pure function; `apply_market` applies results: easy to test.
- Pairing of buyers to sellers in priority order only decides who delivers to whom; the price is
  the same for everyone.
- Encumbrance is derived from open sell orders, not stored in lots, so there is one source of truth.
- Money never goes negative: unpaid fees are tracked as `fee_due`.

## 16. Testing approach
Unit tests per module, a pure-function auction test set, a file for the eight mandatory edge
cases, an end-to-end run of the demo command file, and a check that every BR-ID has a test.
See `Test_Plan.md`. Run: `python -m unittest discover -s tests -t .`
