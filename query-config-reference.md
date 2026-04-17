# QueryConfig SQL Reference

Complete reference for every `QueryConfig` output shape and how to interpret each as SQL.

---

## Table of Contents

- [1. fields — SELECT columns](#1-fields--select-columns)
- [2. calculated_fields — computed expressions](#2-calculated_fields--computed-expressions)
- [3. filters — WHERE clause](#3-filters--where-clause)
- [4. joins — JOIN clause](#4-joins--join-clause)
- [5. aggregation — GROUP BY + aggregate functions](#5-aggregation--group-by--aggregate-functions)
- [6. order_by, limit, offset — sorting and pagination](#6-order_by-limit-offset--sorting-and-pagination)
- [7. subqueries — nested queries](#7-subqueries--nested-queries)
- [8. Combined query patterns](#8-combined-query-patterns)
- [Quick reference table](#quick-reference-table)

---

## 1. `fields` — SELECT columns

`fields` is the SELECT list — only include fields you want in the output. Fields used solely for filtering, joining, or grouping do NOT go in `fields`.

### Basic field

```json
{"field_name": "EmployeeName", "dataSource": "EmpInfo"}
```

```sql
SELECT EmpInfo.EmployeeName
```

### Field with alias

```json
{"field_name": "EmployeeName", "dataSource": "EmpInfo", "alias": "FullName"}
```

```sql
SELECT EmpInfo.EmployeeName AS FullName
```

### Field with date function

```json
{"field_name": "HireDate", "dataSource": "EmpInfo", "function": "YEAR", "alias": "HireYear"}
```

```sql
SELECT YEAR(EmpInfo.HireDate) AS HireYear
```

```json
{"field_name": "PayDate", "dataSource": "Checks", "function": "MONTH", "alias": "PayMonth"}
```

```sql
SELECT MONTH(Checks.PayDate) AS PayMonth
```

```json
{"field_name": "StartDate", "dataSource": "EmpInfo", "function": "DAY", "alias": "StartDay"}
```

```sql
SELECT DAY(EmpInfo.StartDate) AS StartDay
```

### DISTINCT

When `distinct: true` on the QueryConfig:

```json
{"distinct": true, "fields": [{"field_name": "DeptCode", "dataSource": "EmpInfo"}]}
```

```sql
SELECT DISTINCT EmpInfo.DeptCode
```

---

## 2. `calculated_fields` — computed expressions

Calculated fields are always included in the output (they are separate SELECT columns alongside `fields`).

### Basic expression

```json
{"alias": "AnnualPay", "expression": "Salary * 12", "dataSources": ["PayInfo"]}
```

```sql
SELECT (Salary * 12) AS AnnualPay
```

### Cross-data-source expression

```json
{"alias": "NetPay", "expression": "Gross.Amount - Deductions.Amount", "dataSources": ["Gross", "Deductions"]}
```

```sql
SELECT (Gross.Amount - Deductions.Amount) AS NetPay
```

---

## 3. `filters` — WHERE clause

Filters reference fields directly by `field_name` + `dataSource`. Filter-only fields do NOT appear in `fields`.

### Single condition

```json
{
  "filters": {
    "conditions": [
      {"logicType": "CONDITION", "field_name": "Status", "dataSource": "EmpInfo", "operator": "=", "value": "Active"}
    ]
  }
}
```

```sql
WHERE EmpInfo.Status = 'Active'
```

### With date function

```json
{"logicType": "CONDITION", "field_name": "PayDate", "dataSource": "Checks", "function": "YEAR", "operator": "=", "value": 2025}
```

```sql
WHERE YEAR(Checks.PayDate) = 2025
```

```json
{"logicType": "CONDITION", "field_name": "PayDate", "dataSource": "Checks", "function": "MONTH", "operator": ">=", "value": 6}
```

```sql
WHERE MONTH(Checks.PayDate) >= 6
```

### All operators

| Operator | JSON | SQL |
|---|---|---|
| `=` | `"operator": "=", "value": "dev"` | `= 'dev'` |
| `!=` | `"operator": "!=", "value": "dev"` | `!= 'dev'` |
| `>` | `"operator": ">", "value": 1000` | `> 1000` |
| `<` | `"operator": "<", "value": 500` | `< 500` |
| `>=` | `"operator": ">=", "value": 1000` | `>= 1000` |
| `<=` | `"operator": "<=", "value": 500` | `<= 500` |
| `BETWEEN` | `"operator": "BETWEEN", "value": "2025-01-01", "value_end": "2025-12-31"` | `BETWEEN '2025-01-01' AND '2025-12-31'` |
| `IN` | `"operator": "IN", "value": ["A", "B", "C"]` | `IN ('A', 'B', 'C')` |
| `NOT IN` | `"operator": "NOT IN", "value": ["X", "Y"]` | `NOT IN ('X', 'Y')` |
| `LIKE` | `"operator": "LIKE", "value": "%smith%"` | `LIKE '%smith%'` |
| `NOT LIKE` | `"operator": "NOT LIKE", "value": "%test%"` | `NOT LIKE '%test%'` |
| `IS NULL` | `"operator": "IS NULL"` (no value) | `IS NULL` |
| `IS NOT NULL` | `"operator": "IS NOT NULL"` (no value) | `IS NOT NULL` |

### AND group

```json
{
  "filters": {
    "logicType": "AND",
    "conditions": [
      {"logicType": "CONDITION", "field_name": "Dept", "dataSource": "EmpInfo", "operator": "=", "value": "dev"},
      {"logicType": "CONDITION", "field_name": "Status", "dataSource": "EmpInfo", "operator": "=", "value": "Active"}
    ]
  }
}
```

```sql
WHERE EmpInfo.Dept = 'dev'
  AND EmpInfo.Status = 'Active'
```

### OR group

```json
{
  "filters": {
    "logicType": "OR",
    "conditions": [
      {"logicType": "CONDITION", "field_name": "Dept", "dataSource": "EmpInfo", "operator": "=", "value": "dev"},
      {"logicType": "CONDITION", "field_name": "Dept", "dataSource": "EmpInfo", "operator": "=", "value": "qa"}
    ]
  }
}
```

```sql
WHERE EmpInfo.Dept = 'dev'
   OR EmpInfo.Dept = 'qa'
```

### Nested groups (AND containing OR)

```json
{
  "filters": {
    "logicType": "AND",
    "conditions": [
      {"logicType": "CONDITION", "field_name": "Status", "dataSource": "EmpInfo", "operator": "=", "value": "Active"},
      {
        "logicType": "OR",
        "conditions": [
          {"logicType": "CONDITION", "field_name": "Dept", "dataSource": "EmpInfo", "operator": "=", "value": "dev"},
          {"logicType": "CONDITION", "field_name": "Dept", "dataSource": "EmpInfo", "operator": "=", "value": "qa"}
        ]
      }
    ]
  }
}
```

```sql
WHERE EmpInfo.Status = 'Active'
  AND (EmpInfo.Dept = 'dev' OR EmpInfo.Dept = 'qa')
```

### Nested groups (OR containing AND)

```json
{
  "filters": {
    "logicType": "OR",
    "conditions": [
      {
        "logicType": "AND",
        "conditions": [
          {"logicType": "CONDITION", "field_name": "Dept", "dataSource": "EmpInfo", "operator": "=", "value": "dev"},
          {"logicType": "CONDITION", "field_name": "Amount", "dataSource": "Checks", "operator": ">", "value": 1000}
        ]
      },
      {"logicType": "CONDITION", "field_name": "Amount", "dataSource": "Checks", "operator": ">", "value": 5000}
    ]
  }
}
```

```sql
WHERE (EmpInfo.Dept = 'dev' AND Checks.Amount > 1000)
   OR Checks.Amount > 5000
```

### Deep nesting (3 levels)

```json
{
  "filters": {
    "logicType": "AND",
    "conditions": [
      {"logicType": "CONDITION", "field_name": "Status", "dataSource": "EmpInfo", "operator": "=", "value": "Active"},
      {
        "logicType": "OR",
        "conditions": [
          {
            "logicType": "AND",
            "conditions": [
              {"logicType": "CONDITION", "field_name": "Dept", "dataSource": "EmpInfo", "operator": "=", "value": "dev"},
              {"logicType": "CONDITION", "field_name": "Level", "dataSource": "EmpInfo", "operator": ">=", "value": 5}
            ]
          },
          {"logicType": "CONDITION", "field_name": "Role", "dataSource": "EmpInfo", "operator": "=", "value": "Manager"}
        ]
      }
    ]
  }
}
```

```sql
WHERE EmpInfo.Status = 'Active'
  AND (
    (EmpInfo.Dept = 'dev' AND EmpInfo.Level >= 5)
    OR EmpInfo.Role = 'Manager'
  )
```

---

## 4. `joins` — JOIN clause

### INNER JOIN (default)

```json
{"left_data_source": "EmpInfo", "right_data_source": "Checks", "left_field": "EmpCode", "right_field": "EmpCode", "join_type": "INNER"}
```

```sql
FROM EmpInfo
INNER JOIN Checks ON EmpInfo.EmpCode = Checks.EmpCode
```

### LEFT JOIN

```json
{"left_data_source": "EmpInfo", "right_data_source": "Checks", "left_field": "EmpCode", "right_field": "EmpCode", "join_type": "LEFT"}
```

```sql
FROM EmpInfo
LEFT JOIN Checks ON EmpInfo.EmpCode = Checks.EmpCode
```

### RIGHT JOIN

```json
{"left_data_source": "EmpInfo", "right_data_source": "Checks", "left_field": "EmpCode", "right_field": "EmpCode", "join_type": "RIGHT"}
```

```sql
FROM EmpInfo
RIGHT JOIN Checks ON EmpInfo.EmpCode = Checks.EmpCode
```

### FULL OUTER JOIN

```json
{"left_data_source": "EmpInfo", "right_data_source": "Checks", "left_field": "EmpCode", "right_field": "EmpCode", "join_type": "FULL"}
```

```sql
FROM EmpInfo
FULL OUTER JOIN Checks ON EmpInfo.EmpCode = Checks.EmpCode
```

### CROSS JOIN

```json
{"left_data_source": "EmpInfo", "right_data_source": "Depts", "left_field": "", "right_field": "", "join_type": "CROSS"}
```

```sql
FROM EmpInfo
CROSS JOIN Depts
```

### Multiple joins (chain)

```json
[
  {"left_data_source": "EmpInfo", "right_data_source": "Checks", "left_field": "EmpCode", "right_field": "EmpCode", "join_type": "INNER"},
  {"left_data_source": "Checks", "right_data_source": "PayCodes", "left_field": "PayCodeId", "right_field": "PayCodeId", "join_type": "LEFT"}
]
```

```sql
FROM EmpInfo
INNER JOIN Checks ON EmpInfo.EmpCode = Checks.EmpCode
LEFT JOIN PayCodes ON Checks.PayCodeId = PayCodes.PayCodeId
```

---

## 5. `aggregation` — GROUP BY + aggregate functions

Aggregation functions are always included in the output (they are separate SELECT columns alongside `fields`).

### All aggregation operators

| Operator | JSON | SQL |
|---|---|---|
| `SUM` | `"operator": "SUM"` | `SUM(field)` |
| `COUNT` | `"operator": "COUNT"` | `COUNT(field)` |
| `AVG` | `"operator": "AVG"` | `AVG(field)` |
| `MAX` | `"operator": "MAX"` | `MAX(field)` |
| `MIN` | `"operator": "MIN"` | `MIN(field)` |
| `COUNT_DISTINCT` | `"operator": "COUNT_DISTINCT"` | `COUNT(DISTINCT field)` |

### Basic aggregation

```json
{
  "aggregation": {
    "functions": [
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM"}
    ],
    "group_by": [{"field": "DeptCode"}]
  }
}
```

```sql
SELECT DeptCode, SUM(Checks.Amount) AS TotalAmount
FROM Checks
GROUP BY DeptCode
```

### Multiple aggregation functions

```json
{
  "aggregation": {
    "functions": [
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM"},
      {"alias": "AvgAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "AVG"},
      {"alias": "EmpCount", "field_name": "EmpCode", "dataSource": "Checks", "operator": "COUNT_DISTINCT"}
    ],
    "group_by": [{"field": "DeptCode"}]
  }
}
```

```sql
SELECT DeptCode,
       SUM(Checks.Amount) AS TotalAmount,
       AVG(Checks.Amount) AS AvgAmount,
       COUNT(DISTINCT Checks.EmpCode) AS EmpCount
FROM Checks
GROUP BY DeptCode
```

### Aggregation with date function

```json
{
  "aggregation": {
    "functions": [
      {"alias": "HireCount", "field_name": "EmpCode", "dataSource": "EmpInfo", "operator": "COUNT"}
    ],
    "group_by": [{"field": "HireDate", "function": "YEAR"}]
  }
}
```

```sql
SELECT YEAR(HireDate), COUNT(EmpInfo.EmpCode) AS HireCount
FROM EmpInfo
GROUP BY YEAR(HireDate)
```

### Date function on the aggregation function itself

```json
{"alias": "UniqueYears", "field_name": "HireDate", "dataSource": "EmpInfo", "function": "YEAR", "operator": "COUNT_DISTINCT"}
```

```sql
COUNT(DISTINCT YEAR(EmpInfo.HireDate)) AS UniqueYears
```

### Multiple group-by fields (plain + date function)

```json
{
  "group_by": [
    {"field": "DeptCode"},
    {"field": "HireDate", "function": "YEAR"},
    {"field": "HireDate", "function": "MONTH"}
  ]
}
```

```sql
GROUP BY DeptCode, YEAR(HireDate), MONTH(HireDate)
```

### HAVING (post-aggregation filter)

```json
{
  "aggregation": {
    "functions": [
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM"}
    ],
    "group_by": [{"field": "EmpCode"}],
    "having": [{"aggregation_alias": "TotalAmount", "operator": ">", "value": 5000}]
  }
}
```

```sql
SELECT EmpCode, SUM(Amount) AS TotalAmount
FROM Checks
GROUP BY EmpCode
HAVING SUM(Amount) > 5000
```

### HAVING with BETWEEN

```json
{
  "having": [{"aggregation_alias": "TotalAmount", "operator": "BETWEEN", "value": 1000, "value_end": 5000}]
}
```

```sql
HAVING SUM(Amount) BETWEEN 1000 AND 5000
```

### HAVING with IN

```json
{
  "having": [{"aggregation_alias": "EmpCount", "operator": "IN", "value": [5, 10, 15]}]
}
```

```sql
HAVING COUNT(EmpCode) IN (5, 10, 15)
```

### Multiple HAVING conditions

```json
{
  "having": [
    {"aggregation_alias": "TotalAmount", "operator": ">", "value": 5000},
    {"aggregation_alias": "EmpCount", "operator": ">=", "value": 3}
  ]
}
```

```sql
HAVING SUM(Amount) > 5000
   AND COUNT(DISTINCT EmpCode) >= 3
```

---

## 6. `order_by`, `limit`, `offset` — sorting and pagination

These are **top-level** on QueryConfig — they work with or without aggregation.

`order_by` can reference field names, aliases, or aggregation aliases.

### ORDER BY (without aggregation)

```json
{
  "fields": [{"field_name": "EmpName", "dataSource": "EmpInfo"}],
  "order_by": [{"field": "EmpName", "direction": "ASC"}]
}
```

```sql
SELECT EmpInfo.EmpName
FROM EmpInfo
ORDER BY EmpName ASC
```

### ORDER BY with aggregation

```json
{
  "aggregation": {
    "functions": [{"alias": "Total", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM"}],
    "group_by": [{"field": "EmpCode"}]
  },
  "order_by": [{"field": "Total", "direction": "DESC"}]
}
```

```sql
SELECT EmpCode, SUM(Amount) AS Total
FROM Checks
GROUP BY EmpCode
ORDER BY Total DESC
```

### ORDER BY with NULLS position

```json
{
  "order_by": [{"field": "TotalAmount", "direction": "ASC", "nulls_position": "LAST"}]
}
```

```sql
ORDER BY TotalAmount ASC NULLS LAST
```

### Multiple ORDER BY

```json
{
  "order_by": [
    {"field": "DeptCode", "direction": "ASC"},
    {"field": "TotalAmount", "direction": "DESC"}
  ]
}
```

```sql
ORDER BY DeptCode ASC, TotalAmount DESC
```

### LIMIT (top-N)

```json
{
  "fields": [
    {"field_name": "EmpName", "dataSource": "EmpInfo"},
    {"field_name": "HireDate", "dataSource": "EmpInfo"}
  ],
  "order_by": [{"field": "HireDate", "direction": "DESC"}],
  "limit": 5
}
```

```sql
SELECT EmpInfo.EmpName, EmpInfo.HireDate
FROM EmpInfo
ORDER BY HireDate DESC
LIMIT 5
```

### LIMIT + OFFSET (pagination)

```json
{
  "fields": [{"field_name": "EmpName", "dataSource": "EmpInfo"}],
  "order_by": [{"field": "EmpName", "direction": "ASC"}],
  "limit": 10,
  "offset": 20
}
```

```sql
SELECT EmpInfo.EmpName
FROM EmpInfo
ORDER BY EmpName ASC
LIMIT 10 OFFSET 20
```

### LIMIT + OFFSET with aggregation

```json
{
  "aggregation": {
    "functions": [{"alias": "Total", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM"}],
    "group_by": [{"field": "DeptCode"}]
  },
  "order_by": [{"field": "Total", "direction": "DESC"}],
  "limit": 10,
  "offset": 0
}
```

```sql
SELECT DeptCode, SUM(Amount) AS Total
FROM Checks
GROUP BY DeptCode
ORDER BY Total DESC
LIMIT 10 OFFSET 0
```

---

## 7. `subqueries` — nested queries

Subqueries are always included in the output (they are separate SELECT columns alongside `fields`).

### Scalar subquery

```json
{
  "subqueries": [
    {
      "alias": "MaxSalary",
      "query": {
        "aggregation": {
          "functions": [{"alias": "MaxSal", "field_name": "Salary", "dataSource": "PayInfo", "operator": "MAX"}],
          "group_by": []
        }
      }
    }
  ]
}
```

```sql
SELECT ...,
  (SELECT MAX(PayInfo.Salary) FROM PayInfo) AS MaxSalary
```

### Subquery with filters

```json
{
  "subqueries": [
    {
      "alias": "DevMaxSalary",
      "query": {
        "filters": {
          "conditions": [
            {"logicType": "CONDITION", "field_name": "DeptCode", "dataSource": "PayInfo", "operator": "=", "value": "dev"}
          ]
        },
        "aggregation": {
          "functions": [{"alias": "MaxSal", "field_name": "Salary", "dataSource": "PayInfo", "operator": "MAX"}],
          "group_by": []
        }
      }
    }
  ]
}
```

```sql
SELECT ...,
  (SELECT MAX(PayInfo.Salary) FROM PayInfo WHERE PayInfo.DeptCode = 'dev') AS DevMaxSalary
```

---

## 8. Combined query patterns

All possible combinations of QueryConfig sections and their full SQL interpretation.

### Pattern 1: Fields only (simple SELECT)

```json
{
  "fields": [
    {"field_name": "EmpCode", "dataSource": "EmpInfo"},
    {"field_name": "EmpName", "dataSource": "EmpInfo"}
  ]
}
```

```sql
SELECT EmpInfo.EmpCode,
       EmpInfo.EmpName
FROM EmpInfo
```

### Pattern 2: Fields + filters (SELECT with WHERE)

```json
{
  "fields": [
    {"field_name": "EmpCode", "dataSource": "EmpInfo"},
    {"field_name": "EmpName", "dataSource": "EmpInfo"}
  ],
  "filters": {
    "conditions": [
      {"logicType": "CONDITION", "field_name": "Status", "dataSource": "EmpInfo", "operator": "=", "value": "Active"}
    ]
  }
}
```

```sql
SELECT EmpInfo.EmpCode,
       EmpInfo.EmpName
FROM EmpInfo
WHERE EmpInfo.Status = 'Active'
```

Note: `Status` is used for filtering only — it does NOT appear in `fields`.

### Pattern 3: Fields + joins (multi-table SELECT)

```json
{
  "fields": [
    {"field_name": "EmpName", "dataSource": "EmpInfo"},
    {"field_name": "Amount", "dataSource": "Checks"}
  ],
  "joins": [
    {"left_data_source": "EmpInfo", "right_data_source": "Checks", "left_field": "EmpCode", "right_field": "EmpCode", "join_type": "INNER"}
  ]
}
```

```sql
SELECT EmpInfo.EmpName,
       Checks.Amount
FROM EmpInfo
INNER JOIN Checks ON EmpInfo.EmpCode = Checks.EmpCode
```

### Pattern 4: Fields + joins + filters (multi-table with WHERE)

```json
{
  "fields": [
    {"field_name": "EmpName", "dataSource": "EmpInfo"},
    {"field_name": "Amount", "dataSource": "Checks"}
  ],
  "joins": [
    {"left_data_source": "EmpInfo", "right_data_source": "Checks", "left_field": "EmpCode", "right_field": "EmpCode", "join_type": "INNER"}
  ],
  "filters": {
    "logicType": "AND",
    "conditions": [
      {"logicType": "CONDITION", "field_name": "Status", "dataSource": "EmpInfo", "operator": "=", "value": "Active"},
      {"logicType": "CONDITION", "field_name": "Amount", "dataSource": "Checks", "operator": ">", "value": 1000}
    ]
  }
}
```

```sql
SELECT EmpInfo.EmpName,
       Checks.Amount
FROM EmpInfo
INNER JOIN Checks ON EmpInfo.EmpCode = Checks.EmpCode
WHERE EmpInfo.Status = 'Active'
  AND Checks.Amount > 1000
```

### Pattern 5: Fields + aggregation (GROUP BY)

```json
{
  "fields": [
    {"field_name": "DeptCode", "dataSource": "Checks"}
  ],
  "aggregation": {
    "functions": [
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM"}
    ],
    "group_by": [{"field": "DeptCode"}]
  }
}
```

```sql
SELECT Checks.DeptCode,
       SUM(Checks.Amount) AS TotalAmount
FROM Checks
GROUP BY DeptCode
```

### Pattern 6: Fields + filters + aggregation (WHERE + GROUP BY)

```json
{
  "fields": [
    {"field_name": "DeptCode", "dataSource": "Checks"}
  ],
  "filters": {
    "conditions": [
      {"logicType": "CONDITION", "field_name": "PayDate", "dataSource": "Checks", "function": "YEAR", "operator": "=", "value": 2025}
    ]
  },
  "aggregation": {
    "functions": [
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM"}
    ],
    "group_by": [{"field": "DeptCode"}]
  }
}
```

```sql
SELECT Checks.DeptCode,
       SUM(Checks.Amount) AS TotalAmount
FROM Checks
WHERE YEAR(Checks.PayDate) = 2025
GROUP BY DeptCode
```

### Pattern 7: Fields + joins + filters + aggregation (full analytics)

```json
{
  "fields": [
    {"field_name": "EmpName", "dataSource": "EmpInfo"}
  ],
  "joins": [
    {"left_data_source": "EmpInfo", "right_data_source": "Checks", "left_field": "EmpCode", "right_field": "EmpCode", "join_type": "INNER"}
  ],
  "filters": {
    "conditions": [
      {"logicType": "CONDITION", "field_name": "DeptCode", "dataSource": "EmpInfo", "operator": "=", "value": "dev"}
    ]
  },
  "aggregation": {
    "functions": [
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM"}
    ],
    "group_by": [{"field": "EmpName"}]
  },
  "order_by": [{"field": "TotalAmount", "direction": "DESC"}],
  "limit": 10
}
```

```sql
SELECT EmpInfo.EmpName,
       SUM(Checks.Amount) AS TotalAmount
FROM EmpInfo
INNER JOIN Checks ON EmpInfo.EmpCode = Checks.EmpCode
WHERE EmpInfo.DeptCode = 'dev'
GROUP BY EmpInfo.EmpName
ORDER BY TotalAmount DESC
LIMIT 10
```

Note: `DeptCode` is used for filtering only — it does NOT appear in `fields`.

### Pattern 8: Aggregation with HAVING (post-aggregation filter)

```json
{
  "fields": [
    {"field_name": "DeptCode", "dataSource": "Checks"}
  ],
  "aggregation": {
    "functions": [
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM"},
      {"alias": "EmpCount", "field_name": "EmpCode", "dataSource": "Checks", "operator": "COUNT_DISTINCT"}
    ],
    "group_by": [{"field": "DeptCode"}],
    "having": [
      {"aggregation_alias": "TotalAmount", "operator": ">", "value": 50000},
      {"aggregation_alias": "EmpCount", "operator": ">=", "value": 5}
    ]
  },
  "order_by": [{"field": "TotalAmount", "direction": "DESC"}]
}
```

```sql
SELECT Checks.DeptCode,
       SUM(Checks.Amount) AS TotalAmount,
       COUNT(DISTINCT Checks.EmpCode) AS EmpCount
FROM Checks
GROUP BY DeptCode
HAVING SUM(Checks.Amount) > 50000
   AND COUNT(DISTINCT Checks.EmpCode) >= 5
ORDER BY TotalAmount DESC
```

### Pattern 9: Date function in SELECT + filter + GROUP BY

```json
{
  "fields": [
    {"field_name": "HireDate", "dataSource": "EmpInfo", "function": "YEAR", "alias": "HireYear"}
  ],
  "filters": {
    "conditions": [
      {"logicType": "CONDITION", "field_name": "HireDate", "dataSource": "EmpInfo", "function": "YEAR", "operator": ">=", "value": 2020}
    ]
  },
  "aggregation": {
    "functions": [
      {"alias": "HireCount", "field_name": "EmpCode", "dataSource": "EmpInfo", "operator": "COUNT"}
    ],
    "group_by": [{"field": "HireDate", "function": "YEAR"}]
  },
  "order_by": [{"field": "HireYear", "direction": "ASC"}]
}
```

```sql
SELECT YEAR(EmpInfo.HireDate) AS HireYear,
       COUNT(EmpInfo.EmpCode) AS HireCount
FROM EmpInfo
WHERE YEAR(EmpInfo.HireDate) >= 2020
GROUP BY YEAR(EmpInfo.HireDate)
ORDER BY HireYear ASC
```

### Pattern 10: Fields + calculated fields

```json
{
  "fields": [
    {"field_name": "EmpName", "dataSource": "EmpInfo"},
    {"field_name": "Salary", "dataSource": "PayInfo"}
  ],
  "calculated_fields": [
    {"alias": "AnnualPay", "expression": "Salary * 12", "dataSources": ["PayInfo"]}
  ],
  "joins": [
    {"left_data_source": "EmpInfo", "right_data_source": "PayInfo", "left_field": "EmpCode", "right_field": "EmpCode", "join_type": "INNER"}
  ]
}
```

```sql
SELECT EmpInfo.EmpName,
       PayInfo.Salary,
       (Salary * 12) AS AnnualPay
FROM EmpInfo
INNER JOIN PayInfo ON EmpInfo.EmpCode = PayInfo.EmpCode
```

### Pattern 11: Fields + subqueries

```json
{
  "fields": [
    {"field_name": "EmpName", "dataSource": "EmpInfo"},
    {"field_name": "Salary", "dataSource": "PayInfo"}
  ],
  "joins": [
    {"left_data_source": "EmpInfo", "right_data_source": "PayInfo", "left_field": "EmpCode", "right_field": "EmpCode", "join_type": "INNER"}
  ],
  "subqueries": [
    {
      "alias": "CompanyAvg",
      "query": {
        "aggregation": {
          "functions": [{"alias": "AvgSal", "field_name": "Salary", "dataSource": "PayInfo", "operator": "AVG"}],
          "group_by": []
        }
      }
    }
  ]
}
```

```sql
SELECT EmpInfo.EmpName,
       PayInfo.Salary,
       (SELECT AVG(PayInfo.Salary) FROM PayInfo) AS CompanyAvg
FROM EmpInfo
INNER JOIN PayInfo ON EmpInfo.EmpCode = PayInfo.EmpCode
```

### Pattern 12: DISTINCT + filters

```json
{
  "fields": [
    {"field_name": "DeptCode", "dataSource": "EmpInfo"}
  ],
  "filters": {
    "conditions": [
      {"logicType": "CONDITION", "field_name": "Status", "dataSource": "EmpInfo", "operator": "=", "value": "Active"}
    ]
  },
  "distinct": true
}
```

```sql
SELECT DISTINCT EmpInfo.DeptCode
FROM EmpInfo
WHERE EmpInfo.Status = 'Active'
```

### Pattern 13: Freeform field with LIKE (keyword search)

```json
{
  "fields": [
    {"field_name": "EmpCode", "dataSource": "EmpInfo"},
    {"field_name": "EmpName", "dataSource": "EmpInfo"}
  ],
  "filters": {
    "conditions": [
      {"logicType": "CONDITION", "field_name": "EmpName", "dataSource": "EmpInfo", "operator": "LIKE", "value": "%smith%"}
    ]
  }
}
```

```sql
SELECT EmpInfo.EmpCode,
       EmpInfo.EmpName
FROM EmpInfo
WHERE EmpInfo.EmpName LIKE '%smith%'
```

### Pattern 14: Multiple joins + aggregation + HAVING + ORDER + LIMIT (kitchen sink)

```json
{
  "fields": [
    {"field_name": "EmpName", "dataSource": "EmpInfo"},
    {"field_name": "HireDate", "dataSource": "EmpInfo", "function": "YEAR", "alias": "HireYear"}
  ],
  "calculated_fields": [
    {"alias": "AnnualPay", "expression": "Salary * 12", "dataSources": ["PayInfo"]}
  ],
  "joins": [
    {"left_data_source": "EmpInfo", "right_data_source": "Checks", "left_field": "EmpCode", "right_field": "EmpCode", "join_type": "INNER"},
    {"left_data_source": "EmpInfo", "right_data_source": "PayInfo", "left_field": "EmpCode", "right_field": "EmpCode", "join_type": "LEFT"}
  ],
  "filters": {
    "logicType": "AND",
    "conditions": [
      {"logicType": "CONDITION", "field_name": "Status", "dataSource": "EmpInfo", "operator": "=", "value": "Active"},
      {"logicType": "CONDITION", "field_name": "HireDate", "dataSource": "EmpInfo", "function": "YEAR", "operator": ">=", "value": 2020},
      {
        "logicType": "OR",
        "conditions": [
          {"logicType": "CONDITION", "field_name": "DeptCode", "dataSource": "EmpInfo", "operator": "=", "value": "dev"},
          {"logicType": "CONDITION", "field_name": "DeptCode", "dataSource": "EmpInfo", "operator": "=", "value": "qa"}
        ]
      }
    ]
  },
  "aggregation": {
    "functions": [
      {"alias": "TotalExpenses", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM"},
      {"alias": "CheckCount", "field_name": "Amount", "dataSource": "Checks", "operator": "COUNT"}
    ],
    "group_by": [
      {"field": "EmpName"},
      {"field": "HireDate", "function": "YEAR"}
    ],
    "having": [
      {"aggregation_alias": "TotalExpenses", "operator": ">", "value": 10000},
      {"aggregation_alias": "CheckCount", "operator": ">=", "value": 5}
    ]
  },
  "subqueries": [
    {
      "alias": "CompanyAvgExpense",
      "query": {
        "aggregation": {
          "functions": [{"alias": "AvgExp", "field_name": "Amount", "dataSource": "Checks", "operator": "AVG"}],
          "group_by": []
        }
      }
    }
  ],
  "order_by": [
    {"field": "TotalExpenses", "direction": "DESC"},
    {"field": "HireYear", "direction": "ASC"}
  ],
  "limit": 20,
  "distinct": false
}
```

```sql
SELECT EmpInfo.EmpName,
       YEAR(EmpInfo.HireDate) AS HireYear,
       (Salary * 12) AS AnnualPay,
       SUM(Checks.Amount) AS TotalExpenses,
       COUNT(Checks.Amount) AS CheckCount,
       (SELECT AVG(Checks.Amount) FROM Checks) AS CompanyAvgExpense
FROM EmpInfo
INNER JOIN Checks ON EmpInfo.EmpCode = Checks.EmpCode
LEFT JOIN PayInfo ON EmpInfo.EmpCode = PayInfo.EmpCode
WHERE EmpInfo.Status = 'Active'
  AND YEAR(EmpInfo.HireDate) >= 2020
  AND (EmpInfo.DeptCode = 'dev' OR EmpInfo.DeptCode = 'qa')
GROUP BY EmpInfo.EmpName, YEAR(EmpInfo.HireDate)
HAVING SUM(Checks.Amount) > 10000
   AND COUNT(Checks.Amount) >= 5
ORDER BY TotalExpenses DESC, HireYear ASC
LIMIT 20
```

Note: `Status` and `DeptCode` are used for filtering only — they do NOT appear in `fields`.

### Pattern 15: Empty query (cannot be built)

```json
{}
```

```sql
-- No valid query can be constructed (missing fields, no valid joins, etc.)
```

---

## Quick reference table

| QueryConfig field | SQL clause | Output column? |
|---|---|---|
| `fields` | `SELECT col` | Yes — always |
| `fields` + `function` | `SELECT YEAR/MONTH/DAY(col)` | Yes — always |
| `calculated_fields` | `SELECT (expr) AS alias` | Yes — always |
| `filters.conditions` | `WHERE ...` | No |
| `filters.conditions` + `function` | `WHERE YEAR/MONTH/DAY(col) ...` | No |
| `filters` nested groups | `WHERE (... AND/OR ...)` | No |
| `joins` | `[INNER\|LEFT\|RIGHT\|FULL\|CROSS] JOIN ... ON ...` | No |
| `aggregation.functions` | `SELECT AGG(col) AS alias` | Yes — always |
| `aggregation.functions` + `function` | `SELECT AGG(YEAR/MONTH/DAY(col))` | Yes — always |
| `aggregation.group_by` | `GROUP BY col` | No |
| `aggregation.group_by` + `function` | `GROUP BY YEAR/MONTH/DAY(col)` | No |
| `aggregation.having` | `HAVING AGG(col) op value` | No |
| `order_by` | `ORDER BY col [ASC\|DESC] [NULLS FIRST\|LAST]` | No |
| `limit` | `LIMIT N` | No |
| `offset` | `OFFSET N` | No |
| `subqueries` | `SELECT (subquery) AS alias` | Yes — always |
| `distinct` | `SELECT DISTINCT` | N/A (modifier) |
| `{}` (empty) | no valid query | N/A |

---

## SQL clause assembly order

When converting a full QueryConfig to SQL, assemble in this order:

```
1. SELECT       ← fields + calculated_fields + aggregation.functions + subqueries
                  + DISTINCT modifier
2. FROM         ← primary data source (first field's dataSource)
3. JOIN         ← joins[]
4. WHERE        ← filters.conditions (recursive AND/OR groups)
5. GROUP BY     ← aggregation.group_by[]
6. HAVING       ← aggregation.having[]
7. ORDER BY     ← order_by[]
8. LIMIT        ← limit
9. OFFSET       ← offset
```
