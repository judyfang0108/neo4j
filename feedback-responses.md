# QueryConfig Feedback Responses

Responses to the feedback on the QueryConfig design. Each answer notes whether the current model handles it, needs a change, or is a future consideration.

> **Note:** Since this feedback was written, `show` has been removed from all models. `fields` is now the SELECT list directly — only fields you want in the output go in `fields`. `calculated_fields`, `aggregation.functions`, and `subqueries` are always included in the output.

---

## High-Level General Questions

### Q1. Self-join (data source joined with itself)

> Do you think there would ever be a case where we join a data source with itself?

**Yes, it's a valid SQL pattern.** Examples:

- Comparing an employee's record across two time periods (same data source, different date filters)
- Finding employees who share the same manager (`EmpInfo AS E1 JOIN EmpInfo AS E2 ON E1.ManagerCode = E2.EmpCode`)
- Hierarchical queries (org chart traversal)

**Current model does NOT support this.** `JoinConfig` uses `left_data_source` / `right_data_source` as plain strings — if both are `"EmpInfo"`, there's no way to distinguish them.

**To support it, we'd need:**

1. A data-source-level alias (e.g., `from` block or alias on the join):

```json
{
  "joins": [{
    "left_data_source": "EmpInfo",
    "left_alias": "E1",
    "right_data_source": "EmpInfo",
    "right_alias": "E2",
    "left_field": "ManagerCode",
    "right_field": "EmpCode",
    "join_type": "INNER"
  }]
}
```

2. All downstream references (`fields`, `filters`, `group_by`) would need to use the alias (`E1`, `E2`) instead of the raw data source name.

**Recommendation:** Defer unless there's a known use case in the current CRS data. Self-joins are uncommon in HR reporting. If needed later, it's an additive change (add optional `left_alias` / `right_alias` to `JoinConfig`).

---

### Q2. Alias propagation across the query

> Whenever an alias is specified, will that alias be used for the duration of the rest of the query?

**Currently: no.** Aliases are output labels only. Everything else (`filters`, `joins`, `group_by`, `calculated_fields`) references the original `field_name` + `dataSource`.

| Section | References by |
|---|---|
| `fields` | `field_name` + `dataSource` (alias is output label) |
| `filters` | `field_name` + `dataSource` |
| `joins` | `left_field` / `right_field` + data source |
| `group_by` | `field` (field name) |
| `order_by` | `field` (can use alias OR field name) |
| `having` | `aggregation_alias` (references aggregation function alias) |

**`order_by` is the one exception** — it can reference an alias (e.g., `"field": "TotalAmount"` referencing an aggregation alias). This is consistent with SQL where `ORDER BY` can use column aliases but `WHERE` and `GROUP BY` cannot (in most SQL dialects).

**Recommendation:** Keep the current behavior. It matches standard SQL semantics and avoids confusion about alias scope. Calculated field expressions should reference `DataSource.FieldName`, not aliases.

---

### Q3. Field ambiguity in group_by

> If we select EmployeeCode from two different data sources, join them, but do not alias — group_by takes a simple string, so it could be ambiguous.

**This is a real gap.** Currently `GroupByField` is:

```python
class GroupByField(BaseModel):
    field: str                          # just the field name
    function: Optional[DateFunction]    # YEAR, MONTH, DAY
```

If both `EmpInfo.EmployeeCode` and `Checks.EmployeeCode` exist, `{"field": "EmployeeCode"}` is ambiguous.

**Fix:** Add `dataSource` to `GroupByField`:

```python
class GroupByField(BaseModel):
    field: str
    dataSource: Optional[str] = None    # disambiguate when needed
    function: Optional[DateFunction] = None
```

Optional so it doesn't break simple cases where the field name is unique. The validator can enforce it when the field name exists in multiple data sources used in the query.

**Recommendation: Fix this.** It's a small change and prevents a real ambiguity bug.

---

### Q4. Where does `function` go? Function vs. calculated_fields vs. expression

> How many places do we plan on adding "function" to? What is the motivation of field-level function vs. calculated_fields?

**Currently `function` appears on:**

| Model | Purpose | Example |
|---|---|---|
| `FieldConfig` | Date-part in SELECT | `SELECT YEAR(HireDate) AS HireYear` |
| `FilterCondition` | Date-part in WHERE | `WHERE YEAR(PayDate) = 2025` |
| `AggregationFunction` | Date-part inside aggregate | `COUNT(DISTINCT YEAR(HireDate))` |
| `GroupByField` | Date-part in GROUP BY | `GROUP BY YEAR(HireDate)` |

**Why `function` on fields instead of using `calculated_fields`?**

- `function` is a **tight, structured wrapper** — the system knows exactly what operation is happening (extract year from a date). This makes validation easy (we can check the field is actually a date type).
- `calculated_fields` is a **freeform expression string** — `"expression": "Salary * 12"`. The system can't validate or optimize it, it's opaque.
- Date-part extraction is so common in reporting queries that it deserves first-class support rather than being buried in freeform expressions.

**Could calculated_fields involve functions too?**

Yes. A calculated field expression could be `"YEAR(HireDate) - YEAR(StartDate)"` to compute tenure. The difference:

- `function` on a field = single date-part extraction, structured, validatable
- `calculated_fields` = arbitrary expression, freeform, opaque to the system

**Could we use `expression` everywhere instead of `function`?**

We could, but we'd lose validation. With `function: "YEAR"` on a FieldConfig, the system can verify the field is a date type. With `expression: "YEAR(HireDate)"`, it's just a string.

**Recommendation:** Keep `function` for the common structured cases (date-part extraction). Use `calculated_fields` for arbitrary math/string expressions. If CRS adds many more built-in functions (see Q5), consider expanding the `function` type or adding a structured expression model.

---

### Q5. Expanding functions — expression vs. function for complex cases

> We plan on adding several more functions to CRS. Would we ever want complex expressions? We have metadata (descriptions, parameter definitions, examples) for these functions.

Looking at the screenshot, CRS has functions across categories:

| Category | Functions |
|---|---|
| Date | DATE, DATEVALUE, DAY, DAYS, HOUR, MINUTE, MONTH, NOW, SECOND, TIME, TODAY, YEAR |
| Logical | AND, IF, IFERROR, IFS, NOT, OR, XOR |
| Math | ABS, FLOOR, INT, LN, MOD, POWER, ROUND, ROUNDDOWN, ROUNDUP, SIGN, SQRT |
| Statistical | MAX, MIN |
| Text | CONCAT, FIND, LEFT, LEN, LOWER, MID, REPLACE, REPT, RIGHT, TEXTJOIN, TRIM, UPPER |

**This is much broader than our current `YEAR | MONTH | DAY`.** Two approaches:

**Option A: Expand `function` to support all CRS functions**

Add a structured function call model:

```json
{
  "field_name": "HireDate",
  "dataSource": "EmpInfo",
  "function": {
    "name": "DAYS",
    "parameters": {"start_date": "HireDate", "end_date": "TODAY()"}
  }
}
```

Pros: Structured, validatable, can use CRS metadata for parameter validation.
Cons: Complex model, deeply nested JSON.

**Option B: Use `expression` (calculated_fields) for complex cases**

Keep `function` for simple date-part extraction. Use calculated_fields for anything more complex:

```json
{
  "calculated_fields": [
    {"alias": "Tenure", "expression": "DAYS(TODAY(), HireDate)", "dataSources": ["EmpInfo"]}
  ]
}
```

Pros: Simple model, flexible.
Cons: No validation of function names, parameters, or types.

**Option C: Hybrid — structured function model as a separate concept**

Add a `FunctionCall` model that can be used in expressions:

```json
{
  "calculated_fields": [
    {
      "alias": "Tenure",
      "function": {"name": "DAYS", "params": ["TODAY()", "EmpInfo.HireDate"]},
      "dataSources": ["EmpInfo"]
    }
  ]
}
```

**Recommendation:** For now, keep `function` as `YEAR | MONTH | DAY` for the common case. Use `calculated_fields` with freeform expressions for everything else. When CRS releases the full function library, revisit with Option C — a structured `FunctionCall` model that can be validated against the CRS function metadata (name, parameter count, types). The function metadata in the screenshot (descriptions, parameter definitions) maps naturally to a validation schema.

---

## Section-Specific Questions

### QA1. Is the alias for disambiguation?

> Is the goal of alias to be used for stuff like join, making sure things are unambiguous?

**Partially.** The alias serves two purposes:

1. **Output column naming** — `SELECT EmpInfo.EmployeeName AS FullName` gives a cleaner column name in the result
2. **Reference in ORDER BY / HAVING** — `ORDER BY FullName` or `HAVING TotalAmount > 5000`

It is **not** currently used for disambiguation in joins, filters, or group_by — those always use `field_name` + `dataSource` which is already unambiguous (the pair uniquely identifies a field).

If you have `EmployeeName` from two data sources, they'd be:

```json
{
  "fields": [
    {"field_name": "EmployeeName", "dataSource": "EmpInfo", "alias": "EmpInfoName"},
    {"field_name": "EmployeeName", "dataSource": "CheckRecords", "alias": "CheckRecordName"}
  ]
}
```

The aliases make the output columns distinguishable. Filters/joins still use `field_name` + `dataSource` directly.

---

### QA2. Is the alias used by the frontend or just internal?

> Is the alias going to be used directly by the frontend or is it just for our internal query purposes?

**Both, depending on context:**

- The alias becomes the column header in the result set. If the frontend displays query results, it would show the alias as the column name.
- Internally, `order_by` and `having` can reference aliases.

If the frontend has its own column naming/display logic, the alias can be ignored for display purposes and treated as internal-only. This is a frontend integration decision.

---

### QB1. Expression format in calculated_fields

> If there are multiple data sources, do we always assume `DataSource.FieldName` format? What if a data source had an alias?

**Current design: expressions always use `DataSource.FieldName` (original names, not aliases).**

For the example given:

```json
{
  "fields": [
    {"field_name": "Amount", "dataSource": "Gross", "alias": "GrossAmount"},
    {"field_name": "Amount", "dataSource": "Deductions", "alias": "DeductionsAmount"}
  ],
  "calculated_fields": [
    {"alias": "NetPay", "expression": "Gross.Amount - Deductions.Amount", "dataSources": ["Gross", "Deductions"]}
  ]
}
```

The expression uses `Gross.Amount` and `Deductions.Amount` — the original `dataSource` + `field_name`, **not** the field aliases.

**Why not use aliases?**

- Aliases are optional — if no alias is set, there's nothing to reference
- `DataSource.FieldName` is always available and unambiguous
- It's consistent with how `filters`, `joins`, and `group_by` reference fields

**Rule:** Expressions always use `DataSource.FieldName`. Field aliases are only for output column naming and `order_by`/`having` references.

---

### QC1. Required filters

> CRS has a concept of "required" filters in some data sources due to data size. Should we separate required from optional filters?

**Current model does not distinguish required vs. optional filters.** All filters go in the same `filters` block.

**Two approaches:**

**Option A: Encode required filters in the schema metadata**

Add `required_filters` to the Neo4j graph at the data source level. The query generator validates that required filters are present:

```
Module → DataSource (required_filters: ["PayDate BETWEEN"])
                   → Fields
```

The validator checks: "if data source X is used, at least one filter on field Y with operator BETWEEN must exist." This keeps the QueryConfig format unchanged — required and optional filters look the same in the JSON — but validation enforces the rule.

**Option B: Separate required_filters in QueryConfig**

```json
{
  "required_filters": {
    "conditions": [
      {"logicType": "CONDITION", "field_name": "PayDate", "dataSource": "Payroll", "operator": "BETWEEN", "value": "2025-01-01", "value_end": "2025-12-31"}
    ]
  },
  "filters": {
    "conditions": [...]
  }
}
```

**Recommendation: Option A.** Don't change the QueryConfig format. Instead:

1. Store required filter rules in the schema/Neo4j graph (which data sources need which filters)
2. Add a validation step in `validate_query` that checks required filters are present
3. Update the prompt to tell the LLM: "Data source X requires a filter on field Y"

This way the LLM naturally includes the required filter as part of the AND conditions, and the validator catches it if missing. The demo's assumption (top-level AND with a required filter condition) is correct and doesn't need a special structure.

---

### QD1. Multiple join fields (composite join)

> Do we want to support multiple join fields? e.g., `X.EmpCode = Y.EmpCode AND X.SomethingElse = Y.SomethingElse`

**Current model: single join field per JoinConfig.** Only one `left_field` + `right_field` pair.

**To support composite joins, two options:**

**Option A: Multiple JoinConfigs (already works)**

```json
{
  "joins": [
    {"left_data_source": "X", "right_data_source": "Y", "left_field": "EmpCode", "right_field": "EmpCode", "join_type": "INNER"},
    {"left_data_source": "X", "right_data_source": "Y", "left_field": "PayPeriod", "right_field": "PayPeriod", "join_type": "INNER"}
  ]
}
```

But this is ambiguous — are these two separate joins or one composite join? The SQL interpreter would need to merge them.

**Option B: Change join fields to lists**

```json
{
  "joins": [{
    "left_data_source": "X",
    "right_data_source": "Y",
    "left_fields": ["EmpCode", "PayPeriod"],
    "right_fields": ["EmpCode", "PayPeriod"],
    "join_type": "INNER"
  }]
}
```

Maps to: `X JOIN Y ON X.EmpCode = Y.EmpCode AND X.PayPeriod = Y.PayPeriod`

**Recommendation:** Check if any JOINS_WITH relationships in the current Neo4j graph actually require composite keys. If yes, go with Option B (change to lists). If not, defer. Note: this would be a breaking change to `JoinConfig` — `left_field`/`right_field` become `left_fields`/`right_fields` (lists).

---

### QE1. Group-by field ambiguity

> Are we going to guarantee that all group by fields are from unique fields?

**No guarantee currently.** This is the same issue as Q3. If `EmployeeCode` exists in both `EmpInfo` and `Checks`, `{"field": "EmployeeCode"}` is ambiguous.

**Fix: Same as Q3** — add optional `dataSource` to `GroupByField`:

```python
class GroupByField(BaseModel):
    field: str
    dataSource: Optional[str] = None
    function: Optional[DateFunction] = None
```

The validator should enforce `dataSource` when the field name is ambiguous (exists in multiple data sources used in the query).

---

## Summary: What Needs Action

| Item | Priority | Change Type |
|---|---|---|
| Q3/QE1: Add `dataSource` to `GroupByField` | **High** | Model change |
| QC1: Required filter validation | **High** | Schema + validation |
| QB1: Document expression format rule | **Medium** | Documentation only |
| QD1: Composite join keys | **Medium** | Model change (if needed) |
| Q1: Self-join aliases | **Low** | Model change (defer) |
| Q5: Expanded function library | **Low** | Future design (defer) |
| QA2: Alias usage by frontend | **Low** | Integration decision |
