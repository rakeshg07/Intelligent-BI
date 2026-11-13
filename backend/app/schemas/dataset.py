"""Dataset Schemas."""

import uuid

from pydantic import BaseModel, Field


class DatasetColumnBase(BaseModel):
    name: str
    verbose_name: str | None = None
    data_type: str
    description: str | None = None
    is_datetime: bool = False
    is_dimension: bool = True
    is_filterable: bool = True
    is_groupable: bool = True
    is_hidden_from_ai: bool = False


class DatasetColumnOut(DatasetColumnBase):
    id: uuid.UUID
    dataset_id: uuid.UUID

    model_config = {"from_attributes": True}


class DatasetMetricBase(BaseModel):
    name: str
    verbose_name: str | None = None
    sql_expression: str
    metric_type: str = "aggregate"
    number_format: str | None = None
    description: str | None = None


class DatasetMetricOut(DatasetMetricBase):
    id: uuid.UUID
    dataset_id: uuid.UUID

    model_config = {"from_attributes": True}


class RLSRuleBase(BaseModel):
    role_id: uuid.UUID
    clause: str
    description: str | None = None
    is_active: bool = True


class RLSRuleOut(RLSRuleBase):
    id: uuid.UUID
    dataset_id: uuid.UUID

    model_config = {"from_attributes": True}


class DatasetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: str | None = None
    database_id: uuid.UUID
    schema_name: str | None = None
    table_name: str | None = None
    is_virtual: bool = False
    sql_expression: str | None = None


class DatasetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    schema_name: str | None = None
    table_name: str | None = None
    sql_expression: str | None = None


class DatasetOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    database_id: uuid.UUID
    database_name: str | None = None
    schema_name: str | None = None
    table_name: str | None = None
    is_virtual: bool
    sql_expression: str | None = None
    columns: list[DatasetColumnOut] = []
    metrics: list[DatasetMetricOut] = []
    rls_rules: list[RLSRuleOut] = []

    model_config = {"from_attributes": True}
