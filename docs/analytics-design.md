# Advanced Analytics Design

The current `QueryConfig` handles structured data retrieval well — fields, filters, joins, aggregation. But advanced analytics (turnover rates, YoY growth, period comparisons) require **math between query results**, which is a fundamentally different operation.

This doc evaluates three approaches and recommends a phased strategy.

## The problem

A question like *"What is the turnover rate in Dec 2025?"* needs:

```
Turnover Rate = (Employees who separated in Dec 2025) / (Average headcount in Dec 2025) × 100
```

This requires two separate data pulls and a division between them. `QueryConfig` can express each pull individually, but has no way to combine them.

Other examples that hit the same wall:

| Question | Why QueryConfig can't handle it alone |
|---|---|
| What is the turnover rate in Dec 2025? | Division of two aggregates |
| How does overtime compare to last month? | Two time-period queries + difference |
| What % of employees are in each department? | Count per group / total count |
| Year-over-year salary growth by department? | Two year queries + percentage change |
| Which departments exceed the company average salary? | Subquery for avg + filter against it |

---

## Option 1: Extend QueryConfig with `derived_metrics`

Add a `derived_metrics` section that does post-aggregation math, referencing aggregation aliases.

```json
{
  "aggregation": {
    "functions": [
      {"alias": "Separations", "field_name": "TermDate", "dataSource": "...", "operator": "COUNT"},
      {"alias": "Headcount", "field_name": "*", "dataSource": "...", "operator": "COUNT"}
    ],
    "group_by": []
  },
  "derived_metrics": [
    {"alias": "TurnoverRate", "expression": "Separations / Headcount * 100", "references": ["Separations", "Headcount"]}
  ]
}
```

**Pros:**
- Single query in, single result out — downstream system stays simple
- Small, contained addition to the existing format
- The LLM already knows QueryConfig — one new section is easy to learn
- Validation can check that `references` match actual aggregation aliases
- Covers most common analytics: ratios, percentages, growth rates

**Cons:**
- Has limits — can't easily express multi-period comparisons (YoY needs two separate date-filtered queries)
- If the downstream system translates to SQL, `derived_metrics` maps cleanly; if it's a limited API, it may not

**What it handles well:**

| Question | How |
|---|---|
| What % of employees are in each department? | `COUNT(*)` per group + `derived_metrics` dividing by total |
| Turnover rate | `COUNT` with filter (CASE WHEN) + `COUNT(*)` + division |
| Average salary vs company average | Aggregation + derived metric for difference |

---

## Option 2: Free-text expressions

Give `calculated_fields.expression` full power and let the LLM write SQL-like logic.

```json
{
  "calculated_fields": [{
    "alias": "TurnoverRate",
    "expression": "COUNT(CASE WHEN TermDate BETWEEN '2025-12-01' AND '2025-12-31' THEN 1 END) / COUNT(*) * 100",
    "dataSources": ["EmployeeInformation"]
  }]
}
```

**Pros:**
- Infinitely flexible, no format changes needed
- Works today without any code changes

**Cons:**
- Validator is blind — can't check field names, types, or logic inside the expression
- Errors only surface at runtime in the downstream system
- Defeats the purpose of having a structured, validated format

---

## Option 3: Two-layer system (`AnalyticsPlan`)

Keep `QueryConfig` focused on data retrieval. Add an `AnalyticsPlan` layer that orchestrates multiple queries and computes derived results.

```
User: "What is the turnover rate in Dec 2025?"
         │
         ▼
┌─────────────────────────────────┐
│  AnalyticsPlan                  │
│                                 │
│  queries:                       │
│    separations:                 │
│      QueryConfig (COUNT where   │
│      TermDate in Dec 2025)      │
│    headcount:                   │
│      QueryConfig (COUNT where   │
│      active in Dec 2025)        │
│                                 │
│  computation:                   │
│    formula: "separations /      │
│              headcount * 100"   │
│    label: "Turnover Rate (%)"   │
└─────────────────────────────────┘
```

### Example output

```json
{
  "type": "analytics",
  "queries": {
    "separations": {
      "fields": [{"field_name": "EmployeeCode", "dataSource": "EmployeeInformation"}],
      "filters": {
        "logicType": "AND",
        "conditions": [
          {"logicType": "CONDITION", "field_name": "TerminationDate", "dataSource": "EmployeeInformation", "operator": "BETWEEN", "value": "2025-12-01", "value_end": "2025-12-31"}
        ]
      },
      "aggregation": {
        "functions": [{"alias": "SeparationCount", "field_name": "*", "dataSource": "EmployeeInformation", "operator": "COUNT"}],
        "group_by": []
      }
    },
    "headcount": {
      "fields": [{"field_name": "EmployeeCode", "dataSource": "EmployeeInformation"}],
      "filters": {
        "logicType": "AND",
        "conditions": [
          {"logicType": "CONDITION", "field_name": "HireDate", "dataSource": "EmployeeInformation", "operator": "<=", "value": "2025-12-31"}
        ]
      },
      "aggregation": {
        "functions": [{"alias": "HeadCount", "field_name": "*", "dataSource": "EmployeeInformation", "operator": "COUNT"}],
        "group_by": []
      }
    }
  },
  "computation": {
    "steps": [
      {"alias": "TurnoverRate", "formula": "SeparationCount / HeadCount * 100", "format": "percentage", "label": "Turnover Rate"}
    ]
  }
}
```

### More examples

**YoY salary growth by department:**
```json
{
  "type": "analytics",
  "queries": {
    "salary_2024": {
      "aggregation": {
        "functions": [{"alias": "AvgSalary2024", "field_name": "AnnualSalary", "dataSource": "PayInformation", "operator": "AVG"}],
        "group_by": [{"field": "Department", "dataSource": "EmployeeInformation"}]
      },
      "filters": {"logicType": "AND", "conditions": [
        {"logicType": "CONDITION", "field_name": "HireDate", "dataSource": "EmployeeInformation", "function": "YEAR", "operator": "<=", "value": 2024}
      ]}
    },
    "salary_2025": {
      "aggregation": {
        "functions": [{"alias": "AvgSalary2025", "field_name": "AnnualSalary", "dataSource": "PayInformation", "operator": "AVG"}],
        "group_by": [{"field": "Department", "dataSource": "EmployeeInformation"}]
      },
      "filters": {"logicType": "AND", "conditions": [
        {"logicType": "CONDITION", "field_name": "HireDate", "dataSource": "EmployeeInformation", "function": "YEAR", "operator": "<=", "value": 2025}
      ]}
    }
  },
  "computation": {
    "join_on": ["Department"],
    "steps": [
      {"alias": "Growth", "formula": "(AvgSalary2025 - AvgSalary2024) / AvgSalary2024 * 100", "format": "percentage", "label": "YoY Salary Growth"}
    ]
  }
}
```

**Department headcount as % of total:**
```json
{
  "type": "analytics",
  "queries": {
    "by_dept": {
      "fields": [{"field_name": "Department", "dataSource": "EmployeeInformation"}],
      "aggregation": {
        "functions": [{"alias": "DeptCount", "field_name": "*", "dataSource": "EmployeeInformation", "operator": "COUNT"}],
        "group_by": [{"field": "Department", "dataSource": "EmployeeInformation"}]
      }
    },
    "total": {
      "aggregation": {
        "functions": [{"alias": "TotalCount", "field_name": "*", "dataSource": "EmployeeInformation", "operator": "COUNT"}],
        "group_by": []
      }
    }
  },
  "computation": {
    "steps": [
      {"alias": "Percentage", "formula": "DeptCount / TotalCount * 100", "format": "percentage", "label": "% of Total"}
    ]
  }
}
```

**Pros:**
- Each `QueryConfig` is independently validated with the existing logic
- Any new analytic pattern is just a new combination of queries + formulas — no format changes
- Each data query and computation step is explicit and inspectable

**Cons:**
- LLM generates a more complex structure (multiple queries + formulas) — more room for error
- Downstream system needs a new execution mode: run N queries, combine results, apply formulas
- Needs its own formula validation layer on top of query validation
- For simple analytics (% of total), generating 2 queries is overkill when one SQL with a window function handles it

---

## Recommendation: start with Option 1, graduate to Option 3

Option 3 is the cleanest architecture, but it's overengineered if most analytics are simple ratios and percentages. The practical path:

### Phase 1: `derived_metrics` (Option 1)

Add `derived_metrics` to `QueryConfig`. This is a small change that covers the majority of analytics questions:

```json
"derived_metrics": [
  {"alias": "TurnoverRate", "expression": "Separations / Headcount * 100", "references": ["Separations", "Headcount"]}
]
```

- References point to `aggregation.functions` aliases — fully validatable
- Downstream system translates to a single SQL query (or equivalent)
- The LLM learns one new section, not a whole new format

**Handles:** ratios, percentages, differences between aggregates, anything expressible in a single query.

| Component | Change |
|---|---|
| `dataclass.py` | Add `DerivedMetric` model, add `derived_metrics` field to `QueryConfig` |
| `query_generator.py` | Validate that `references` match aggregation aliases |
| `prompt.py` | Add rules + examples for `derived_metrics` |
| Downstream system | Translate `derived_metrics` to SQL expressions over the aggregation results |

### Phase 2: `AnalyticsPlan` (Option 3) — only if needed

If you hit questions that genuinely can't be a single query — typically multi-period comparisons where each period needs different filters:

- YoY growth (two separate date-filtered queries + comparison)
- Period-over-period trends (this month vs last month)
- Cross-module analytics that need separate query contexts

Then add `AnalyticsPlan` as a separate output type alongside `QueryConfig`. Each inner query gets full validation. The LLM decides which format based on whether the question needs multiple data pulls.

### Decision trigger for Phase 2

Move to Phase 2 when you see the LLM consistently trying to hack multi-period logic into a single `QueryConfig` and failing validation — that's the signal that `derived_metrics` isn't enough.

### Summary

| Phase | What it adds | When to adopt |
|---|---|---|
| **Phase 1** | `derived_metrics` in QueryConfig | Now — covers ratios, %, differences |
| **Phase 2** | `AnalyticsPlan` (multi-query + computation) | When single-query analytics hit a wall (multi-period, cross-context) |
