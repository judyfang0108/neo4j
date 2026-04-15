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

Every `FieldConfig` becomes a column reference. `show` controls whether it appears in the output.

### Basic field

```json
{"field_name": "EmployeeName", "dataSource": "EmpInfo", "show": true}
```

```sql
SELECT EmpInfo.EmployeeName
```

### Field with alias

```json
{"field_name": "EmployeeName", "dataSource": "EmpInfo", "alias": "FullName", "show": true}
```

```sql
SELECT EmpInfo.EmployeeName AS FullName
```

### Hidden field (used in filter/join/group only)

```json
{"field_name": "DeptCode", "dataSource": "EmpInfo", "show": false}
```

```sql
-- DeptCode is referenced (WHERE/JOIN/GROUP BY) but excluded from the result columns
```

### Field with date function

```json
{"field_name": "HireDate", "dataSource": "EmpInfo", "function": "YEAR", "alias": "HireYear", "show": true}
```

```sql
SELECT YEAR(EmpInfo.HireDate) AS HireYear
```

```json
{"field_name": "PayDate", "dataSource": "Checks", "function": "MONTH", "alias": "PayMonth", "show": true}
```

```sql
SELECT MONTH(Checks.PayDate) AS PayMonth
```

```json
{"field_name": "StartDate", "dataSource": "EmpInfo", "function": "DAY", "alias": "StartDay", "show": true}
```

```sql
SELECT DAY(EmpInfo.StartDate) AS StartDay
```

### DISTINCT

When `distinct: true` on the QueryConfig:

```json
{"distinct": true, "fields": [{"field_name": "DeptCode", "dataSource": "EmpInfo", "show": true}]}
```

```sql
SELECT DISTINCT EmpInfo.DeptCode
```

---

## 2. `calculated_fields` — computed expressions

### Basic expression

```json
{"alias": "AnnualPay", "expression": "Salary * 12", "dataSources": ["PayInfo"], "show": true}
```

```sql
SELECT (Salary * 12) AS AnnualPay
```

### Cross-data-source expression

```json
{"alias": "NetPay", "expression": "Gross.Amount - Deductions.Amount", "dataSources": ["Gross", "Deductions"], "show": true}
```

```sql
SELECT (Gross.Amount - Deductions.Amount) AS NetPay
```

### Hidden calculated field

```json
{"alias": "TaxBracket", "expression": "Salary * 0.3", "dataSources": ["PayInfo"], "show": false}
```

```sql
-- (Salary * 0.3) AS TaxBracket is computed internally but not returned to the user
```

---

## 3. `filters` — WHERE clause

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
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM", "show": true}
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
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM", "show": true},
      {"alias": "AvgAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "AVG", "show": true},
      {"alias": "EmpCount", "field_name": "EmpCode", "dataSource": "Checks", "operator": "COUNT_DISTINCT", "show": true}
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

### Hidden aggregation (computed but not shown)

```json
{
  "aggregation": {
    "functions": [
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM", "show": true},
      {"alias": "RowCount", "field_name": "EmpCode", "dataSource": "Checks", "operator": "COUNT", "show": false}
    ],
    "group_by": [{"field": "DeptCode"}]
  }
}
```

```sql
SELECT DeptCode,
       SUM(Checks.Amount) AS TotalAmount
       -- COUNT(Checks.EmpCode) AS RowCount  (computed, not in output)
FROM Checks
GROUP BY DeptCode
```

### Aggregation with date function

```json
{
  "aggregation": {
    "functions": [
      {"alias": "HireCount", "field_name": "EmpCode", "dataSource": "EmpInfo", "operator": "COUNT", "show": true}
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
{"alias": "UniqueYears", "field_name": "HireDate", "dataSource": "EmpInfo", "function": "YEAR", "operator": "COUNT_DISTINCT", "show": true}
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
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM", "show": true}
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

### ORDER BY (without aggregation)

```json
{
  "fields": [{"field_name": "EmpName", "dataSource": "EmpInfo", "show": true}],
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
    "functions": [{"alias": "Total", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM", "show": true}],
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
    {"field_name": "EmpName", "dataSource": "EmpInfo", "show": true},
    {"field_name": "HireDate", "dataSource": "EmpInfo", "show": true}
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
  "fields": [{"field_name": "EmpName", "dataSource": "EmpInfo", "show": true}],
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
    "functions": [{"alias": "Total", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM", "show": true}],
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

### Scalar subquery (shown)

```json
{
  "subqueries": [
    {
      "alias": "MaxSalary",
      "show": true,
      "query": {
        "aggregation": {
          "functions": [{"alias": "MaxSal", "field_name": "Salary", "dataSource": "PayInfo", "operator": "MAX", "show": true}],
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

### Hidden subquery

```json
{
  "subqueries": [
    {
      "alias": "AvgDeptPay",
      "show": false,
      "query": {
        "aggregation": {
          "functions": [{"alias": "AvgPay", "field_name": "Salary", "dataSource": "PayInfo", "operator": "AVG", "show": true}],
          "group_by": []
        }
      }
    }
  ]
}
```

```sql
-- (SELECT AVG(PayInfo.Salary) FROM PayInfo) AS AvgDeptPay  (computed, not in output)
```

### Subquery with filters

```json
{
  "subqueries": [
    {
      "alias": "DevMaxSalary",
      "show": true,
      "query": {
        "filters": {
          "conditions": [
            {"logicType": "CONDITION", "field_name": "DeptCode", "dataSource": "PayInfo", "operator": "=", "value": "dev"}
          ]
        },
        "aggregation": {
          "functions": [{"alias": "MaxSal", "field_name": "Salary", "dataSource": "PayInfo", "operator": "MAX", "show": true}],
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
    {"field_name": "EmpCode", "dataSource": "EmpInfo", "show": true},
    {"field_name": "EmpName", "dataSource": "EmpInfo", "show": true}
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
    {"field_name": "EmpCode", "dataSource": "EmpInfo", "show": true},
    {"field_name": "EmpName", "dataSource": "EmpInfo", "show": true}
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

### Pattern 3: Fields + joins (multi-table SELECT)

```json
{
  "fields": [
    {"field_name": "EmpName", "dataSource": "EmpInfo", "show": true},
    {"field_name": "Amount", "dataSource": "Checks", "show": true}
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
    {"field_name": "EmpName", "dataSource": "EmpInfo", "show": true},
    {"field_name": "Amount", "dataSource": "Checks", "show": true}
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
    {"field_name": "DeptCode", "dataSource": "Checks", "show": true}
  ],
  "aggregation": {
    "functions": [
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM", "show": true}
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
    {"field_name": "DeptCode", "dataSource": "Checks", "show": true}
  ],
  "filters": {
    "conditions": [
      {"logicType": "CONDITION", "field_name": "PayDate", "dataSource": "Checks", "function": "YEAR", "operator": "=", "value": 2025}
    ]
  },
  "aggregation": {
    "functions": [
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM", "show": true}
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
    {"field_name": "EmpName", "dataSource": "EmpInfo", "show": true},
    {"field_name": "DeptCode", "dataSource": "EmpInfo", "show": false}
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
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM", "show": true}
    ],
    "group_by": [{"field": "EmpName"}]
  },
  "order_by": [{"field": "TotalAmount", "direction": "DESC"}],
  "limit": 10
}
```

```sql
SELECT EmpInfo.EmpName,
       -- EmpInfo.DeptCode  (show: false, used in WHERE only)
       SUM(Checks.Amount) AS TotalAmount
FROM EmpInfo
INNER JOIN Checks ON EmpInfo.EmpCode = Checks.EmpCode
WHERE EmpInfo.DeptCode = 'dev'
GROUP BY EmpInfo.EmpName
ORDER BY TotalAmount DESC
LIMIT 10
```

### Pattern 8: Aggregation with HAVING (post-aggregation filter)

```json
{
  "fields": [
    {"field_name": "DeptCode", "dataSource": "Checks", "show": true}
  ],
  "aggregation": {
    "functions": [
      {"alias": "TotalAmount", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM", "show": true},
      {"alias": "EmpCount", "field_name": "EmpCode", "dataSource": "Checks", "operator": "COUNT_DISTINCT", "show": true}
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
    {"field_name": "HireDate", "dataSource": "EmpInfo", "function": "YEAR", "alias": "HireYear", "show": true}
  ],
  "filters": {
    "conditions": [
      {"logicType": "CONDITION", "field_name": "HireDate", "dataSource": "EmpInfo", "function": "YEAR", "operator": ">=", "value": 2020}
    ]
  },
  "aggregation": {
    "functions": [
      {"alias": "HireCount", "field_name": "EmpCode", "dataSource": "EmpInfo", "operator": "COUNT", "show": true}
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
    {"field_name": "EmpName", "dataSource": "EmpInfo", "show": true},
    {"field_name": "Salary", "dataSource": "PayInfo", "show": true}
  ],
  "calculated_fields": [
    {"alias": "AnnualPay", "expression": "Salary * 12", "dataSources": ["PayInfo"], "show": true}
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
    {"field_name": "EmpName", "dataSource": "EmpInfo", "show": true},
    {"field_name": "Salary", "dataSource": "PayInfo", "show": true}
  ],
  "joins": [
    {"left_data_source": "EmpInfo", "right_data_source": "PayInfo", "left_field": "EmpCode", "right_field": "EmpCode", "join_type": "INNER"}
  ],
  "subqueries": [
    {
      "alias": "CompanyAvg",
      "show": true,
      "query": {
        "aggregation": {
          "functions": [{"alias": "AvgSal", "field_name": "Salary", "dataSource": "PayInfo", "operator": "AVG", "show": true}],
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
    {"field_name": "DeptCode", "dataSource": "EmpInfo", "show": true}
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
    {"field_name": "EmpCode", "dataSource": "EmpInfo", "show": true},
    {"field_name": "EmpName", "dataSource": "EmpInfo", "show": true}
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
    {"field_name": "EmpName", "dataSource": "EmpInfo", "show": true},
    {"field_name": "DeptCode", "dataSource": "EmpInfo", "show": false},
    {"field_name": "HireDate", "dataSource": "EmpInfo", "function": "YEAR", "alias": "HireYear", "show": true}
  ],
  "calculated_fields": [
    {"alias": "AnnualPay", "expression": "Salary * 12", "dataSources": ["PayInfo"], "show": true}
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
      {"alias": "TotalExpenses", "field_name": "Amount", "dataSource": "Checks", "operator": "SUM", "show": true},
      {"alias": "CheckCount", "field_name": "Amount", "dataSource": "Checks", "operator": "COUNT", "show": true},
      {"alias": "MaxCheck", "field_name": "Amount", "dataSource": "Checks", "operator": "MAX", "show": false}
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
      "show": true,
      "query": {
        "aggregation": {
          "functions": [{"alias": "AvgExp", "field_name": "Amount", "dataSource": "Checks", "operator": "AVG", "show": true}],
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
SELECT EmpInfo.EmpName,                             -- field, show: true
       -- EmpInfo.DeptCode                           -- field, show: false (WHERE only)
       YEAR(EmpInfo.HireDate) AS HireYear,           -- field + function, show: true
       (Salary * 12) AS AnnualPay,                   -- calculated_field, show: true
       SUM(Checks.Amount) AS TotalExpenses,          -- aggregation, show: true
       COUNT(Checks.Amount) AS CheckCount,           -- aggregation, show: true
       -- MAX(Checks.Amount) AS MaxCheck             -- aggregation, show: false
       (SELECT AVG(Checks.Amount) FROM Checks) AS CompanyAvgExpense  -- subquery, show: true
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
| `fields` (show: true) | `SELECT col` | Yes |
| `fields` (show: false) | referenced in FROM, not in SELECT | No |
| `fields` + `function` | `SELECT YEAR/MONTH/DAY(col)` | Depends on `show` |
| `calculated_fields` (show: true) | `SELECT (expr) AS alias` | Yes |
| `calculated_fields` (show: false) | computed, not in SELECT | No |
| `filters.conditions` | `WHERE ...` | No |
| `filters.conditions` + `function` | `WHERE YEAR/MONTH/DAY(col) ...` | No |
| `filters` nested groups | `WHERE (... AND/OR ...)` | No |
| `joins` | `[INNER\|LEFT\|RIGHT\|FULL\|CROSS] JOIN ... ON ...` | No |
| `aggregation.functions` (show: true) | `SELECT AGG(col) AS alias` | Yes |
| `aggregation.functions` (show: false) | computed, not in SELECT | No |
| `aggregation.functions` + `function` | `SELECT AGG(YEAR/MONTH/DAY(col))` | Depends on `show` |
| `aggregation.group_by` | `GROUP BY col` | No |
| `aggregation.group_by` + `function` | `GROUP BY YEAR/MONTH/DAY(col)` | No |
| `aggregation.having` | `HAVING AGG(col) op value` | No |
| `order_by` | `ORDER BY col [ASC\|DESC] [NULLS FIRST\|LAST]` | No |
| `limit` | `LIMIT N` | No |
| `offset` | `OFFSET N` | No |
| `subqueries` (show: true) | `SELECT (subquery) AS alias` | Yes |
| `subqueries` (show: false) | computed, not in SELECT | No |
| `distinct` | `SELECT DISTINCT` | N/A (modifier) |
| `{}` (empty) | no valid query | N/A |

---

## SQL clause assembly order

When converting a full QueryConfig to SQL, assemble in this order:

```
1. SELECT       ← fields (show:true) + calculated_fields (show:true)
                  + aggregation.functions (show:true) + subqueries (show:true)
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
