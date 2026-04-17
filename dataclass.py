"""
Pydantic data models for the CRS Query Generator
"""

from typing import List, Optional, Literal, Union, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


# Date part extraction functions applicable to date/datetime fields
DateFunction = Literal["YEAR", "MONTH", "DAY"]


class CalculatedField(BaseModel):
    """A calculated field with an expression - supports cross-data source expressions"""

    alias: str
    expression: str
    dataSources: List[str] = Field(
        alias="dataSources"
    )  # Support multiple data sources for cross-data source expressions

    # Accept both 'dataSource' (singular, typo) and 'dataSources' (plural, correct) for backwards compatibility
    @model_validator(mode="before")
    @classmethod
    def normalize_datasources(cls, value):
        if value is None:
            return value
        if isinstance(value, dict):
            # Accept both 'dataSource' (singular) and 'dataSources' (plural)
            if "dataSource" in value and "dataSources" not in value:
                # Convert singular to list
                ds = value["dataSource"]
                if isinstance(ds, str):
                    value = {**value, "dataSources": [ds]}
                elif isinstance(ds, list):
                    value = {**value, "dataSources": ds}
        return value


class FieldConfig(BaseModel):
    """Configuration for a field to retrieve"""

    field_name: str
    dataSource: str
    alias: Optional[str] = None  # For aliasing in output
    function: Optional[DateFunction] = None  # e.g. YEAR(HireDate) → "function": "YEAR"


class FilterCondition(BaseModel):
    """A single filter condition"""

    logicType: Literal["CONDITION"] = "CONDITION"
    field_name: str
    dataSource: str
    function: Optional[DateFunction] = None  # e.g. WHERE YEAR(PayDate) = 2025
    operator: Literal[
        "=",
        "!=",
        ">",
        "<",
        ">=",
        "<=",
        "BETWEEN",
        "IN",
        "NOT IN",
        "LIKE",
        "NOT LIKE",
        "IS NULL",
        "IS NOT NULL",
    ]
    value: Optional[Union[str, int, float, List[Union[str, int, float]]]] = None
    value_end: Optional[Union[str, int, float]] = None  # For BETWEEN

    @model_validator(mode="after")
    def validate_operator_values(self):
        """Validate that values are appropriate for the operator"""
        op = self.operator
        val = self.value

        # IN operator requires a list
        if op == "IN" and val is not None and not isinstance(val, list):
            raise ValueError("IN operator requires a list of values")

        # BETWEEN requires value_end
        if op == "BETWEEN" and self.value_end is None:
            raise ValueError("BETWEEN operator requires value_end")

        # NULL operators don't need values
        if op in ("IS NULL", "IS NOT NULL") and val is not None:
            raise ValueError(f"{op} operator should not have a value")

        # Other operators need a value
        if op not in ("IS NULL", "IS NOT NULL") and val is None:
            raise ValueError(f"{op} operator requires a value")

        return self


class FilterGroup(BaseModel):
    """A group of filters with logic (for nested filters)"""

    logicType: Literal["AND", "OR"]
    conditions: List[Union[FilterCondition, "FilterGroup"]]


class Filters(BaseModel):
    """Filter configuration with conditions and logic"""

    logicType: Optional[Literal["AND", "OR"]] = None
    conditions: Optional[List[Union[FilterCondition, "FilterGroup"]]] = None


class JoinConfig(BaseModel):
    """Configuration for joining two data sources"""

    left_data_source: str
    right_data_source: str
    left_field: str
    right_field: str
    join_type: Literal["INNER", "LEFT", "RIGHT", "FULL", "CROSS"] = "INNER"


class OrderBy(BaseModel):
    """Ordering configuration"""

    field: str
    direction: Literal["ASC", "DESC"] = "ASC"
    nulls_position: Optional[Literal["FIRST", "LAST"]] = None


class AggregationFunction(BaseModel):
    """A single aggregation function (for multiple aggregations)"""

    alias: str  # Output alias like "TotalAmount", "EmployeeCount"
    field_name: str  # Use "*" with COUNT for COUNT(*)
    dataSource: str
    function: Optional[DateFunction] = None  # e.g. COUNT_DISTINCT(YEAR(HireDate))
    operator: Literal["SUM", "COUNT", "AVG", "MAX", "MIN", "COUNT_DISTINCT"]

    @model_validator(mode="after")
    def validate_count_star(self):
        """Only COUNT supports field_name '*'"""
        if self.field_name == "*" and self.operator != "COUNT":
            raise ValueError("field_name '*' is only valid with COUNT operator")
        return self


class HavingCondition(BaseModel):
    """Post-aggregation filter (HAVING clause)"""

    aggregation_alias: str  # Reference to the aggregated field alias
    operator: Literal["=", "!=", ">", "<", ">=", "<=", "BETWEEN", "IN"]
    value: Union[str, int, float, List[Union[str, int, float]]]
    value_end: Optional[Union[str, int, float]] = None


class GroupByField(BaseModel):
    """A field to group by, with optional date function"""

    field: str
    dataSource: Optional[str] = None  # required when field name exists in multiple data sources
    function: Optional[DateFunction] = None  # e.g. GROUP BY YEAR(HireDate)


class Aggregation(BaseModel):
    """Aggregation configuration (GROUP BY + aggregate functions + HAVING)"""

    # Multiple aggregation functions
    functions: List[AggregationFunction]
    # Group by fields
    group_by: List[GroupByField]
    # HAVING conditions (post-aggregation filters)
    having: Optional[List[HavingCondition]] = None


class Subquery(BaseModel):
    """A subquery that can be used in the main query"""

    alias: str
    query: "QueryConfig"  # Recursive reference to QueryConfig


class QueryConfig(BaseModel):
    """Main query configuration containing all components"""

    # Fields to retrieve (optional to allow empty queries when no query can be built)
    fields: Optional[List[FieldConfig]] = None
    # Calculated fields
    calculated_fields: Optional[List[CalculatedField]] = None
    # Filter conditions
    filters: Optional[Filters] = None
    # Joins
    joins: Optional[List[JoinConfig]] = None
    # Aggregation (supports multiple functions with HAVING)
    aggregation: Optional[Aggregation] = None
    # Subqueries
    subqueries: Optional[List[Subquery]] = None
    # Ordering (works with or without aggregation)
    order_by: Optional[List[OrderBy]] = None
    # Pagination
    limit: Optional[int] = None
    offset: Optional[int] = None
    # Distinct results
    distinct: bool = False

    @model_validator(mode="after")
    def validate_filters_logic(self):
        """Validate that logicType is present when multiple conditions exist"""
        if (
            self.filters
            and self.filters.conditions
            and len(self.filters.conditions) > 1
            and not self.filters.logicType
        ):
            raise ValueError(
                "Multiple filter conditions require 'logicType' to be specified (AND or OR)"
            )
        return self


# Handle forward reference for FilterGroup and Subquery
FilterGroup.model_rebuild()
Subquery.model_rebuild()
