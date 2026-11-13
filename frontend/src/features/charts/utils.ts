/**
 * Chart Builder Column & Type Utilities
 */

// Helper to determine if a column is a genuine temporal (date/time/timestamp) column
export const isTemporalColumn = (col: any): boolean => {
  if (!col) return false;
  if (col.is_datetime === true || col.is_datetime === 1) return true;
  const t = (col.data_type || "").toUpperCase();
  return (
    t.includes("DATE") ||
    t.includes("TIMESTAMP") ||
    t.includes("DATETIME") ||
    t.includes("TIMESTAMPTZ") ||
    t === "TIME"
  );
};

// Helper to determine if a column is numeric
export const isNumericColumn = (col: any): boolean => {
  if (!col) return false;
  const t = (col.data_type || "").toUpperCase();
  return (
    t.includes("INT") ||
    t.includes("DOUBLE") ||
    t.includes("FLOAT") ||
    t.includes("DECIMAL") ||
    t.includes("NUMERIC") ||
    t.includes("BIGINT") ||
    t.includes("REAL")
  );
};

