import { describe, it, expect } from "vitest";
import { isTemporalColumn, isNumericColumn } from "../utils";

describe("Chart Builder Column Validation", () => {
  it("strictly validates temporal date/time columns and excludes numeric/incompatible columns", () => {
    // job_rate (DOUBLE) MUST NOT be considered temporal
    expect(isTemporalColumn({ name: "job_rate", data_type: "DOUBLE", is_datetime: false })).toBe(false);
    expect(isTemporalColumn({ name: "annual_salary", data_type: "BIGINT", is_datetime: false })).toBe(false);
    expect(isTemporalColumn({ name: "years", data_type: "BIGINT", is_datetime: false })).toBe(false);
    expect(isTemporalColumn({ name: "department", data_type: "VARCHAR", is_datetime: false })).toBe(false);

    // start_date (TIMESTAMP) MUST be recognized as temporal
    expect(isTemporalColumn({ name: "start_date", data_type: "TIMESTAMP", is_datetime: true })).toBe(true);
    expect(isTemporalColumn({ name: "order_date", data_type: "DATE", is_datetime: false })).toBe(true);
    expect(isTemporalColumn({ name: "created_at", data_type: "TIMESTAMPTZ", is_datetime: false })).toBe(true);
  });

  it("identifies numeric measure columns for metrics and aggregations", () => {
    expect(isNumericColumn({ name: "annual_salary", data_type: "BIGINT" })).toBe(true);
    expect(isNumericColumn({ name: "monthly_salary", data_type: "BIGINT" })).toBe(true);
    expect(isNumericColumn({ name: "job_rate", data_type: "DOUBLE" })).toBe(true);
    expect(isNumericColumn({ name: "years", data_type: "BIGINT" })).toBe(true);
    expect(isNumericColumn({ name: "total_revenue", data_type: "DECIMAL(10,2)" })).toBe(true);

    expect(isNumericColumn({ name: "department", data_type: "VARCHAR" })).toBe(false);
    expect(isNumericColumn({ name: "country", data_type: "VARCHAR" })).toBe(false);
    expect(isNumericColumn({ name: "start_date", data_type: "TIMESTAMP" })).toBe(false);
  });
});

