import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  BarChart3,
  Plus,
  Play,
  Save,
  Trash2,
  Edit2,
  RefreshCw,
  ChevronLeft,
  Clock,
  AlertCircle,
  Sparkles,
} from "lucide-react";
import { api, ChartItem, DatasetItem, ChartDataResponse } from "@/app/api";
import { chartRegistry, ChartPlugin } from "@/charts";
<<<<<<< HEAD
import { isTemporalColumn, isNumericColumn } from "./utils";
=======
import { AIDrawer } from "@/features/ai/AIDrawer";
>>>>>>> upstream/main

export const ChartsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  // Mode: "list" or "explore"
  const [mode, setMode] = useState<"list" | "explore">("list");
  const [editingChartId, setEditingChartId] = useState<string | null>(null);

  // Queries
  const { data: charts = [], isLoading: isLoadingCharts, refetch: refetchCharts } = useQuery({
    queryKey: ["charts"],
    queryFn: api.getCharts,
  });

  const { data: datasets = [] } = useQuery({
    queryKey: ["datasets"],
    queryFn: api.getDatasets,
  });

  const { data: dashboards = [] } = useQuery({
    queryKey: ["dashboards"],
    queryFn: api.getDashboards,
  });

  const chartList: ChartItem[] = Array.isArray(charts)
    ? (charts as ChartItem[])
    : (charts as any)?.data || [];
  const datasetList: DatasetItem[] = Array.isArray(datasets)
    ? (datasets as DatasetItem[])
    : (datasets as any)?.data || [];
  const dashboardList = Array.isArray(dashboards)
    ? dashboards
    : (dashboards as any)?.data || [];

  // List Filter State
  const [listDatasetFilter, setListDatasetFilter] = useState<string>("all");

  // Explore Builder State
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("");
  const [selectedVizType, setSelectedVizType] = useState<string>("bar");

  // X-Axis (Dimension / Category)
  const [selectedDimension, setSelectedDimension] = useState<string>("");
  const [selectedDimensions, setSelectedDimensions] = useState<string[]>([]);

  // Y-Axis (Metric / Measure & Aggregation)
  const [primaryMetricCol, setPrimaryMetricCol] = useState<string>("count");
  const [primaryMetricAgg, setPrimaryMetricAgg] = useState<string>("SUM");
  const [additionalMetrics, setAdditionalMetrics] = useState<any[]>([]);

  // Temporal Axis
  const [timeColumn, setTimeColumn] = useState<string>("");
  const [timeGrain, setTimeGrain] = useState<string>("month");

  // Chart Options & Limits
  const [chartOptions, setChartOptions] = useState<Record<string, any>>({});
  const [rowLimit, setRowLimit] = useState<number>(100);

  // Filters state
  const [filters, setFilters] = useState<any[]>([]);
  const [newFilterCol, setNewFilterCol] = useState<string>("");
  const [newFilterOp, setNewFilterOp] = useState<string>("==");
  const [newFilterVal, setNewFilterVal] = useState<string>("");

  // Query Execution State
  const [chartData, setChartData] = useState<ChartDataResponse | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [activeViewTab, setActiveViewTab] = useState<"chart" | "data" | "sql">("chart");
  const queryRequestIdRef = useRef<number>(0);

  // Save Modal State
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [chartTitle, setChartTitle] = useState("");
  const [chartDescription, setChartDescription] = useState("");
  const [targetDashboardId, setTargetDashboardId] = useState<string>("auto");
  const [isDatasetAIDrawerOpen, setIsDatasetAIDrawerOpen] = useState(false);

  // Resolved Dataset & Columns
  const currentDataset = useMemo(() => {
    return selectedDatasetId
      ? datasetList.find((d: DatasetItem) => d.id === selectedDatasetId)
      : datasetList[0];
  }, [datasetList, selectedDatasetId]);

  const currentColumns: any[] = useMemo(() => currentDataset?.columns || [], [currentDataset]);
  const currentPredefinedMetrics: any[] = useMemo(() => currentDataset?.metrics || [], [currentDataset]);

  // Validated column subsets by type
  const validTimeColumns = useMemo(() => currentColumns.filter(isTemporalColumn), [currentColumns]);
  const numericColumns = useMemo(() => currentColumns.filter(isNumericColumn), [currentColumns]);
  const dimensionColumns = useMemo(
    () => currentColumns.filter((c) => c.is_dimension || !isTemporalColumn(c)),
    [currentColumns]
  );

  // Sync initial dataset ID
  useEffect(() => {
    if (datasetList.length > 0 && !selectedDatasetId) {
      setSelectedDatasetId(datasetList[0].id);
    }
  }, [datasetList, selectedDatasetId]);

  // Handle URL param ?dataset=...
  useEffect(() => {
    const datasetParam = searchParams.get("dataset");
    if (datasetParam && datasetList.length > 0) {
      const match = datasetList.find((d) => d.id === datasetParam);
      if (match) {
        handleDatasetChange(match.id);
        setMode("explore");
      }
    }
  }, [searchParams, datasetList]);

  // Helper to compute initial sensible defaults for a dataset
  const initializeDatasetSelections = useCallback(
    (ds: DatasetItem) => {
      const cols: any[] = ds.columns || [];
      const timeCols = cols.filter(isTemporalColumn);
      const numCols = cols.filter(isNumericColumn);

      // Best dimension: categorical column (not email, mobile, id)
      const bestDim =
        cols.find((c) => {
          const n = (c.column_name || c.name || "").toLowerCase();
          return (
            (c.is_dimension || !isTemporalColumn(c)) &&
            !isNumericColumn(c) &&
            (n.includes("dept") ||
              n.includes("category") ||
              n.includes("country") ||
              n.includes("gender") ||
              n.includes("region") ||
              n.includes("status"))
          );
        }) ||
        cols.find((c) => !isTemporalColumn(c) && !isNumericColumn(c)) ||
        cols[0];

      const bestDimName = bestDim ? bestDim.column_name || bestDim.name : "";
      setSelectedDimension(bestDimName);
      setSelectedDimensions(bestDimName ? [bestDimName] : []);

      // Time column: default to first valid temporal column only
      if (timeCols.length > 0) {
        const dtCol = timeCols[0];
        setTimeColumn(dtCol.column_name || dtCol.name);
      } else {
        setTimeColumn("");
      }

      // Metric: if numeric columns exist, pick the first one
      if (numCols.length > 0) {
        const firstNum = numCols[0];
        const numName = firstNum.column_name || firstNum.name;
        setPrimaryMetricCol(numName);
        setPrimaryMetricAgg("AVG");
      } else if (ds.metrics && ds.metrics.length > 0) {
        const firstM = ds.metrics[0];
        setPrimaryMetricCol(firstM.metric_name || (firstM as any).name);
        setPrimaryMetricAgg("SUM");
      } else {
        setPrimaryMetricCol("count");
        setPrimaryMetricAgg("COUNT");
      }

      setAdditionalMetrics([]);
      setFilters([]);
      setChartData(null);
      setQueryError(null);
    },
    []
  );

  // Explicit dataset change handler
  const handleDatasetChange = (newDatasetId: string) => {
    setSelectedDatasetId(newDatasetId);
    setChartData(null);
    setQueryError(null);
    const newDs = datasetList.find((d) => d.id === newDatasetId);
    if (newDs) {
      initializeDatasetSelections(newDs);
    }
  };

  // Build active metrics payload
  const activeMetrics = useMemo(() => {
    const list: any[] = [];
    if (primaryMetricCol === "count" || !primaryMetricCol) {
      list.push({ name: "count", label: "Count of Rows", expression: "COUNT(*)" });
    } else {
      // Check if primaryMetricCol matches a predefined dataset metric
      const predefined = currentPredefinedMetrics.find(
        (m) => (m.metric_name || (m as any).name) === primaryMetricCol
      );
      if (predefined) {
        list.push({
          name: predefined.metric_name || (predefined as any).name,
          label: predefined.verbose_name || predefined.metric_name || (predefined as any).name,
          expression: predefined.sql_expression,
        });
      } else {
        const agg = primaryMetricAgg.toUpperCase();
        const expr =
          agg === "COUNT_DISTINCT"
            ? `COUNT(DISTINCT "${primaryMetricCol}")`
            : `${agg}("${primaryMetricCol}")`;
        const mName = `${agg.toLowerCase()}_${primaryMetricCol}`;
        const label = `${agg}(${primaryMetricCol})`;
        list.push({ name: mName, label, expression: expr, column: primaryMetricCol, agg });
      }
    }

    // Append any additional metrics
    for (const extra of additionalMetrics) {
      if (!list.some((m) => m.name === extra.name || m.expression === extra.expression)) {
        list.push(extra);
      }
    }
    return list;
  }, [primaryMetricCol, primaryMetricAgg, additionalMetrics, currentPredefinedMetrics]);

  // Execute chart query mutation
  const runQueryMutation = useMutation({
    mutationFn: async () => {
      if (!selectedDatasetId) throw new Error("Please select a dataset.");
      const plugin = chartRegistry.get(selectedVizType);
      const isMultiDim = plugin?.controlPanel.dimensions.multi;

      let dims: string[] = isMultiDim
        ? selectedDimensions
        : selectedDimension
        ? [selectedDimension]
        : [];

      // For big_number KPI, dimensions are not required
      if (selectedVizType === "big_number") {
        dims = [];
      } else if (dims.length === 0 && !timeColumn) {
        // Fallback to first available dimension
        const fallbackCol = dimensionColumns[0] || currentColumns[0];
        if (fallbackCol) {
          dims = [fallbackCol.column_name || fallbackCol.name];
        }
      }

      // Enforce valid time column: only pass if valid in dataset
      const safeTimeCol = validTimeColumns.some(
        (c) => (c.column_name || c.name) === timeColumn
      )
        ? timeColumn
        : undefined;

      const payload = {
        dataset_id: selectedDatasetId,
        viz_type: selectedVizType,
        dimensions: dims,
        metrics: activeMetrics,
        filters,
        time_column: safeTimeCol,
        time_grain: safeTimeCol ? timeGrain : undefined,
        row_limit: rowLimit,
      };

      const thisRequestId = ++queryRequestIdRef.current;
      const result = await api.getChartData(payload);
      return { result, requestId: thisRequestId };
    },
    onMutate: () => {
      // Clear previous error on new execution
      setQueryError(null);
    },
    onSuccess: ({ result, requestId }) => {
      // Prevent stale asynchronous responses from overwriting newer query results
      if (requestId === queryRequestIdRef.current) {
        setChartData(result);
        setQueryError(null);
      }
    },
    onError: (err: any) => {
      // On failure: do NOT represent stale chart data as new results
      setChartData(null);
      setQueryError(err?.message || "Query execution failed. Please verify axis configuration.");
    },
  });

  // Auto-run query when explore mode loads or critical axes change
  const lastQueryKeyRef = useRef<string>("");
  useEffect(() => {
    if (mode !== "explore" || !selectedDatasetId || !currentDataset) return;

    const currentKey = JSON.stringify({
      ds: selectedDatasetId,
      viz: selectedVizType,
      dim: selectedDimension,
      dims: selectedDimensions,
      mCol: primaryMetricCol,
      mAgg: primaryMetricAgg,
      addM: additionalMetrics,
      tc: timeColumn,
      tg: timeGrain,
      f: filters,
      lim: rowLimit,
    });

    if (lastQueryKeyRef.current !== currentKey) {
      lastQueryKeyRef.current = currentKey;
      runQueryMutation.mutate();
    }
  }, [
    mode,
    selectedDatasetId,
    currentDataset,
    selectedVizType,
    selectedDimension,
    selectedDimensions,
    primaryMetricCol,
    primaryMetricAgg,
    additionalMetrics,
    timeColumn,
    timeGrain,
    filters,
    rowLimit,
  ]);

  // Save chart mutation
  const saveChartMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        title: chartTitle.trim(),
        description: chartDescription.trim(),
        dataset_id: selectedDatasetId,
        viz_type: selectedVizType,
        dashboard_id: targetDashboardId && targetDashboardId !== "auto" && targetDashboardId !== "none" ? targetDashboardId : undefined,
        params: {
          dimension: selectedDimension,
          dimensions: selectedDimensions,
          primary_metric_col: primaryMetricCol,
          primary_metric_agg: primaryMetricAgg,
          metrics: activeMetrics,
          additional_metrics: additionalMetrics,
          time_column: timeColumn,
          time_grain: timeGrain,
          options: chartOptions,
          filters,
          row_limit: rowLimit,
        },
      };

      if (editingChartId) {
        return api.updateChart(editingChartId, payload);
      } else {
        return api.createChart(payload);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["charts"] });
      queryClient.invalidateQueries({ queryKey: ["dashboards"] });
      setIsSaveModalOpen(false);
      setEditingChartId(null);
      setMode("list");
    },
  });

  // Delete chart mutation
  const deleteChartMutation = useMutation({
    mutationFn: (id: string) => api.deleteChart(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["charts"] });
    },
  });

  const handleOpenExplore = (chartToEdit?: ChartItem) => {
    if (chartToEdit) {
      setEditingChartId(chartToEdit.id);
      setChartTitle(chartToEdit.title);
      setChartDescription(chartToEdit.description || "");
      setSelectedDatasetId(chartToEdit.dataset_id);
      setSelectedVizType(chartToEdit.viz_type);
      const p = chartToEdit.params || {};

      setSelectedDimension(p.dimension || "");
      setSelectedDimensions(p.dimensions || (p.dimension ? [p.dimension] : []));

      if (p.primary_metric_col) {
        setPrimaryMetricCol(p.primary_metric_col);
        setPrimaryMetricAgg(p.primary_metric_agg || "SUM");
      } else if (p.metrics && p.metrics.length > 0) {
        const firstM = p.metrics[0];
        setPrimaryMetricCol(firstM.column || firstM.name || "count");
        setPrimaryMetricAgg(firstM.agg || "SUM");
      } else {
        setPrimaryMetricCol("count");
        setPrimaryMetricAgg("SUM");
      }

      setAdditionalMetrics(p.additional_metrics || []);
      setTimeColumn(p.time_column || "");
      setTimeGrain(p.time_grain || "month");
      setChartOptions(p.options || {});
      setFilters(p.filters || []);
      setRowLimit(p.row_limit || 100);
      setChartData(null);
      setQueryError(null);
    } else {
      setEditingChartId(null);
      setChartTitle("New Chart");
      setChartDescription("");
      if (currentDataset) {
        initializeDatasetSelections(currentDataset);
      }
    }
    setMode("explore");
  };

  const handleAddFilter = () => {
    if (!newFilterCol) return;
    setFilters([...filters, { col: newFilterCol, op: newFilterOp, val: newFilterVal }]);
    setNewFilterCol("");
    setNewFilterVal("");
  };

  const handleRemoveFilter = (index: number) => {
    setFilters(filters.filter((_, idx) => idx !== index));
  };

  // Render chart using Plugin Registry
  const plugin: ChartPlugin | undefined = chartRegistry.get(selectedVizType);
  const chartProps = plugin && chartData ? plugin.transformProps(chartData, chartOptions) : null;

  return (
    <div className="space-y-6">
      {/* ==================== LIST MODE VIEW ==================== */}
      {mode === "list" && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900">Charts</h1>
              <p className="text-sm text-slate-500">
                Explore datasets, configure dynamic dimensions & metrics, and assemble ECharts visualizations.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => refetchCharts()}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-md hover:bg-slate-50 transition"
              >
                <RefreshCw className={`w-4 h-4 ${isLoadingCharts ? "animate-spin" : ""}`} />
                Refresh
              </button>
              <button
                onClick={() => handleOpenExplore()}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 shadow-sm transition"
              >
                <Plus className="w-4 h-4" />
                Create Chart
              </button>
            </div>
          </div>

          {/* Dataset Filter Dropdown */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm">
            <div className="flex items-center gap-3">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-500 whitespace-nowrap">
                DATASET
              </label>
              <select
                value={listDatasetFilter}
                onChange={(e) => setListDatasetFilter(e.target.value)}
                className="px-3 py-1.5 text-xs font-medium text-slate-800 bg-white border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm min-w-[240px]"
              >
                <option value="all">All Datasets ({chartList.length} charts)</option>
                {datasetList.map((ds: DatasetItem) => {
                  const count = chartList.filter((c) => c.dataset_id === ds.id).length;
                  return (
                    <option key={ds.id} value={ds.id}>
                      {ds.name} ({ds.table_name || "Virtual"}) — {count} charts
                    </option>
                  );
                })}
              </select>
            </div>

            <div className="text-xs text-slate-500">
              Showing{" "}
              <span className="font-semibold text-slate-800">
                {listDatasetFilter === "all"
                  ? chartList.length
                  : chartList.filter((c) => c.dataset_id === listDatasetFilter).length}
              </span>{" "}
              of {chartList.length} charts
            </div>
          </div>

          {/* Charts Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {chartList
              .filter((chart: ChartItem) =>
                listDatasetFilter === "all" ? true : chart.dataset_id === listDatasetFilter
              )
              .map((chart: ChartItem) => {
                const ds = datasetList.find((d: DatasetItem) => d.id === chart.dataset_id);
                return (
                  <div
                    key={chart.id}
                    className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm hover:shadow-md transition flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-3">
                          <div className="p-2.5 bg-blue-50 text-blue-600 rounded-lg">
                            <BarChart3 className="w-5 h-5" />
                          </div>
                          <div>
                            <h3 className="font-semibold text-slate-900 text-sm">{chart.title}</h3>
                            <span className="inline-block px-2 py-0.5 text-[10px] uppercase font-bold tracking-wider bg-slate-100 text-slate-700 rounded mt-0.5">
                              {chart.viz_type}
                            </span>
                          </div>
                        </div>
                        <button
                          onClick={() => {
                            if (confirm(`Delete chart '${chart.title}'?`)) {
                              deleteChartMutation.mutate(chart.id);
                            }
                          }}
                          className="text-slate-400 hover:text-red-600 transition p-1"
                          title="Delete chart"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>

                      {chart.description && (
                        <p className="text-xs text-slate-500 mt-2 line-clamp-2">{chart.description}</p>
                      )}

                      <div className="mt-4 pt-3 border-t border-slate-100 space-y-1 text-xs text-slate-600">
                        <div className="flex justify-between">
                          <span className="text-slate-400">Dataset:</span>
                          <span className="font-medium text-slate-800 truncate max-w-[180px]">
                            {ds?.name || "Dataset"}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-400">Created:</span>
                          <span className="text-slate-600">
                            {chart.created_at ? new Date(chart.created_at).toLocaleDateString() : "—"}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="mt-5 pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
                      <button
                        onClick={() => handleOpenExplore(chart)}
                        className="px-3 py-1.5 text-xs font-medium text-blue-600 hover:bg-blue-50 rounded flex items-center gap-1.5 transition"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                        Explore / Edit
                      </button>
                    </div>
                  </div>
                );
              })}
          </div>

          {chartList.length === 0 && (
            <div className="rounded-xl border border-slate-200 bg-white p-12 text-center space-y-3">
              <div className="inline-flex p-3 rounded-full bg-blue-50 text-blue-600">
                <BarChart3 className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-semibold text-slate-900">No Charts Created Yet</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                Explore connected datasets, choose from Apache ECharts visualizations, and save charts to assemble dashboards.
              </p>
              <button
                onClick={() => handleOpenExplore()}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-blue-600 rounded-md hover:bg-blue-700 shadow-sm transition"
              >
                <Plus className="w-4 h-4" />
                Build Your First Chart
              </button>
            </div>
          )}
        </div>
      )}

      {/* ==================== EXPLORE MODE VIEW ==================== */}
      {mode === "explore" && (
        <div className="flex flex-col h-[calc(100vh-4rem)] -m-6 overflow-hidden bg-slate-50">
          {/* Top Navbar */}
          <div className="bg-white border-b border-slate-200 px-4 py-2.5 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={() => {
                  setMode("list");
                  setSearchParams({});
                }}
                className="inline-flex items-center gap-1 text-xs text-slate-600 hover:text-slate-900 font-medium px-2 py-1 rounded hover:bg-slate-100 transition"
              >
                <ChevronLeft className="w-4 h-4" />
                Back to Charts
              </button>
              <div className="h-4 w-px bg-slate-200" />
              <div>
                <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-blue-600" />
                  {chartTitle || "Explore Chart"}
                </h2>
                <p className="text-[11px] text-slate-400">
                  Dataset: {currentDataset?.name || "None"} ({currentColumns.length} columns)
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => runQueryMutation.mutate()}
                disabled={runQueryMutation.isPending}
                className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded shadow-sm transition"
              >
                {runQueryMutation.isPending ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    Running Query...
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 fill-current" />
                    Run Query
                  </>
                )}
              </button>

              <button
                onClick={() => setIsSaveModalOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 hover:bg-slate-50 rounded shadow-sm transition"
              >
                <Save className="w-3.5 h-3.5" />
                Save Chart
              </button>
            </div>
          </div>

          {/* Main Explore Layout: Controls Sidebar on Left, Visualization Canvas on Right */}
          <div className="flex-1 flex overflow-hidden">
            {/* Left Controls Sidebar */}
            <div className="w-84 border-r border-slate-200 bg-white overflow-y-auto p-4 space-y-5 flex-shrink-0">
              {/* 1. Dataset Selection */}
              <div>
                <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1">
                  Dataset
                </label>
                <select
                  value={selectedDatasetId}
                  onChange={(e) => handleDatasetChange(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs border border-slate-300 rounded font-medium focus:ring-2 focus:ring-blue-500 bg-white shadow-sm"
                >
                  {datasetList.map((d: DatasetItem) => (
                    <option key={d.id} value={d.id}>
                      {d.name} ({d.table_name || "Virtual"})
                    </option>
                  ))}
                </select>
              </div>

              {/* 2. Visualization Type Picker */}
              <div>
                <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">
                  Visualization Type
                </label>
                <div className="grid grid-cols-2 gap-1.5">
                  {chartRegistry.getAllMetadata().map((meta) => (
                    <button
                      key={meta.id}
                      onClick={() => setSelectedVizType(meta.id)}
                      className={`px-2 py-1.5 text-left text-xs rounded border transition flex items-center justify-between ${
                        selectedVizType === meta.id
                          ? "border-blue-600 bg-blue-50 text-blue-900 font-semibold ring-1 ring-blue-500"
                          : "border-slate-200 text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      <span className="truncate">{meta.name}</span>
                      <span className="text-[9px] text-slate-400 capitalize shrink-0 ml-1">
                        {meta.category}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {/* 3. X-Axis (Dimensions / Categories) */}
              <div className="pt-3 border-t border-slate-100 space-y-2">
                <div className="flex items-center justify-between">
                  <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
                    X-Axis (Category / Dimension)
                  </label>
                  <span className="text-[10px] text-slate-400">
                    {plugin?.controlPanel.dimensions.multi ? "Multi-select" : "Single"}
                  </span>
                </div>

                {plugin?.controlPanel.dimensions.multi ? (
                  <div className="space-y-1.5 max-h-36 overflow-y-auto border border-slate-200 p-2 rounded bg-slate-50/50">
                    {currentColumns.map((c) => {
                      const colName = c.column_name || c.name;
                      return (
                        <label
                          key={colName}
                          className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer hover:text-blue-600"
                        >
                          <input
                            type="checkbox"
                            checked={selectedDimensions.includes(colName)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedDimensions([...selectedDimensions, colName]);
                              } else {
                                setSelectedDimensions(
                                  selectedDimensions.filter((dim) => dim !== colName)
                                );
                              }
                            }}
                            className="rounded text-blue-600 focus:ring-blue-500"
                          />
                          <span className="font-mono text-[11px]">{colName}</span>
                          <span className="text-[10px] text-slate-400 ml-auto">
                            {c.data_type}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                ) : (
                  <select
                    value={selectedDimension}
                    onChange={(e) => {
                      setSelectedDimension(e.target.value);
                      setSelectedDimensions(e.target.value ? [e.target.value] : []);
                    }}
                    className="w-full px-2.5 py-1.5 text-xs border border-slate-300 rounded bg-white font-medium focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">-- Choose X-Axis Column --</option>
                    {currentColumns.map((c) => {
                      const colName = c.column_name || c.name;
                      return (
                        <option key={colName} value={colName}>
                          {colName} ({c.data_type})
                        </option>
                      );
                    })}
                  </select>
                )}
              </div>

              {/* 4. Y-Axis (Metric & Aggregation) */}
              <div className="pt-3 border-t border-slate-100 space-y-2">
                <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
                  Y-Axis (Metric & Aggregation)
                </label>

                {/* Primary Metric Row */}
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 space-y-2">
                  <div className="flex gap-1.5 items-center">
                    {/* Aggregation Function Selector */}
                    <select
                      value={primaryMetricAgg}
                      onChange={(e) => setPrimaryMetricAgg(e.target.value)}
                      disabled={primaryMetricCol === "count"}
                      className="w-24 px-1.5 py-1 text-xs border border-slate-300 rounded bg-white font-mono font-semibold text-blue-800 disabled:opacity-50"
                    >
                      <option value="SUM">SUM</option>
                      <option value="AVG">AVG</option>
                      <option value="MIN">MIN</option>
                      <option value="MAX">MAX</option>
                      <option value="COUNT">COUNT</option>
                      <option value="COUNT_DISTINCT">DIST</option>
                    </select>

                    {/* Column Selector */}
                    <select
                      value={primaryMetricCol}
                      onChange={(e) => setPrimaryMetricCol(e.target.value)}
                      className="flex-1 min-w-0 px-2 py-1 text-xs border border-slate-300 rounded bg-white font-medium text-slate-800"
                    >
                      <option value="count">Count of Rows (COUNT(*))</option>
                      {numericColumns.length > 0 && (
                        <optgroup label="Numeric Measures">
                          {numericColumns.map((c) => {
                            const colName = c.column_name || c.name;
                            return (
                              <option key={colName} value={colName}>
                                {colName} ({c.data_type})
                              </option>
                            );
                          })}
                        </optgroup>
                      )}
                      {currentColumns
                        .filter((c) => !isNumericColumn(c))
                        .map((c) => {
                          const colName = c.column_name || c.name;
                          return (
                            <option key={colName} value={colName}>
                              {colName} ({c.data_type})
                            </option>
                          );
                        })}
                    </select>
                  </div>

                  <div className="text-[11px] text-slate-500 font-mono bg-white px-2 py-1 rounded border border-slate-200 flex items-center justify-between">
                    <span className="text-slate-400">SQL Expression:</span>
                    <span className="font-semibold text-blue-600 truncate ml-2">
                      {primaryMetricCol === "count"
                        ? "COUNT(*)"
                        : `${primaryMetricAgg}("${primaryMetricCol}")`}
                    </span>
                  </div>
                </div>

                {/* Additional Metrics for Multi-Series Visualizations */}
                {additionalMetrics.length > 0 && (
                  <div className="space-y-1 pt-1">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Additional Series:
                    </div>
                    {additionalMetrics.map((sm, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between text-xs bg-blue-50 text-blue-900 px-2 py-1 rounded font-mono"
                      >
                        <span className="truncate">{sm.label || sm.expression}</span>
                        <button
                          type="button"
                          onClick={() =>
                            setAdditionalMetrics(additionalMetrics.filter((_, i) => i !== idx))
                          }
                          className="text-blue-400 hover:text-red-600 ml-1"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* 5. Temporal Axis & Time Grain (Strictly Validated for DATE / TIMESTAMP) */}
              <div className="pt-3 border-t border-slate-100 space-y-2">
                <div className="flex items-center justify-between">
                  <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
                    Time Column & Grain
                  </label>
                  {validTimeColumns.length === 0 && (
                    <span className="text-[10px] text-amber-600 font-medium">None in schema</span>
                  )}
                </div>

                {validTimeColumns.length > 0 ? (
                  <div className="space-y-2">
                    <select
                      value={timeColumn}
                      onChange={(e) => setTimeColumn(e.target.value)}
                      className="w-full px-2.5 py-1.5 text-xs border border-slate-300 rounded bg-white font-medium"
                    >
                      <option value="">None (Categorical X-Axis)</option>
                      {validTimeColumns.map((c) => {
                        const colName = c.column_name || c.name;
                        return (
                          <option key={colName} value={colName}>
                            {colName} ({c.data_type})
                          </option>
                        );
                      })}
                    </select>

                    {timeColumn && (
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] text-slate-500 whitespace-nowrap">Grain:</span>
                        <select
                          value={timeGrain}
                          onChange={(e) => setTimeGrain(e.target.value)}
                          className="flex-1 px-2 py-1 text-xs border border-slate-300 rounded bg-white font-mono"
                        >
                          <option value="hour">Hour</option>
                          <option value="day">Day</option>
                          <option value="week">Week</option>
                          <option value="month">Month</option>
                          <option value="quarter">Quarter</option>
                          <option value="year">Year</option>
                        </select>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="p-2 rounded bg-slate-50 border border-slate-200 text-[11px] text-slate-500 italic">
                    This dataset has no detected DATE or TIMESTAMP columns. Time-based date_trunc grouping is disabled.
                  </div>
                )}
              </div>

              {/* 6. Ad-Hoc Filters */}
              <div className="pt-3 border-t border-slate-100 space-y-2">
                <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
                  Filters ({filters.length})
                </label>

                {filters.length > 0 && (
                  <div className="space-y-1">
                    {filters.map((f, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between text-xs bg-slate-100 p-1.5 rounded font-mono"
                      >
                        <span className="truncate">
                          {f.col} {f.op} {String(f.val)}
                        </span>
                        <button
                          onClick={() => handleRemoveFilter(idx)}
                          className="text-slate-400 hover:text-red-600 text-xs px-1"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                <div className="space-y-1.5 pt-1">
                  <select
                    value={newFilterCol}
                    onChange={(e) => setNewFilterCol(e.target.value)}
                    className="w-full px-2 py-1 text-xs border border-slate-300 rounded bg-white"
                  >
                    <option value="">+ Add Column Filter...</option>
                    {currentColumns.map((c) => {
                      const colName = c.column_name || c.name;
                      return (
                        <option key={colName} value={colName}>
                          {colName} ({c.data_type})
                        </option>
                      );
                    })}
                  </select>

                  {newFilterCol && (
                    <div className="flex gap-1">
                      <select
                        value={newFilterOp}
                        onChange={(e) => setNewFilterOp(e.target.value)}
                        className="w-16 px-1 py-1 text-xs border border-slate-300 rounded bg-white font-mono"
                      >
                        <option value="==">=</option>
                        <option value="!=">!=</option>
                        <option value=">">&gt;</option>
                        <option value=">=">&gt;=</option>
                        <option value="<">&lt;</option>
                        <option value="<=">&lt;=</option>
                        <option value="LIKE">LIKE</option>
                      </select>
                      <input
                        type="text"
                        placeholder="Filter value..."
                        value={newFilterVal}
                        onChange={(e) => setNewFilterVal(e.target.value)}
                        className="flex-1 px-2 py-1 text-xs border border-slate-300 rounded"
                      />
                      <button
                        type="button"
                        onClick={handleAddFilter}
                        className="px-2.5 py-1 text-xs font-semibold bg-blue-600 text-white rounded hover:bg-blue-700"
                      >
                        Add
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* 7. Chart Customization Options */}
              {plugin?.controlPanel.options && (
                <div className="pt-3 border-t border-slate-100 space-y-2">
                  <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
                    Chart Customization
                  </label>
                  {Object.entries(plugin.controlPanel.options).map(
                    ([optKey, optConfig]: [string, any]) => (
                      <div key={optKey} className="text-xs">
                        {optConfig.type === "boolean" && (
                          <label className="flex items-center gap-2 cursor-pointer text-slate-700 hover:text-slate-900">
                            <input
                              type="checkbox"
                              checked={chartOptions[optKey] ?? optConfig.default}
                              onChange={(e) =>
                                setChartOptions({ ...chartOptions, [optKey]: e.target.checked })
                              }
                              className="rounded text-blue-600 focus:ring-blue-500"
                            />
                            <span>{optConfig.label}</span>
                          </label>
                        )}
                        {optConfig.type === "select" && (
                          <div>
                            <label className="block text-[11px] text-slate-600 mb-1">
                              {optConfig.label}
                            </label>
                            <select
                              value={chartOptions[optKey] ?? optConfig.default}
                              onChange={(e) =>
                                setChartOptions({ ...chartOptions, [optKey]: e.target.value })
                              }
                              className="w-full px-2.5 py-1 text-xs border border-slate-300 rounded bg-white font-medium"
                            >
                              {optConfig.options.map((o: string) => (
                                <option key={o} value={o}>
                                  {o}
                                </option>
                              ))}
                            </select>
                          </div>
                        )}
                      </div>
                    )
                  )}
                </div>
              )}
            </div>

            {/* Right Canvas / Visualization Area */}
            <div className="flex-1 flex flex-col overflow-hidden bg-white">
              {/* Tab Navigation: Visualization / Data Preview / SQL */}
              <div className="px-4 pt-2 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
                <div className="flex gap-4">
                  <button
                    onClick={() => setActiveViewTab("chart")}
                    className={`pb-2 text-xs font-semibold border-b-2 transition ${
                      activeViewTab === "chart"
                        ? "border-blue-600 text-blue-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    Visualization
                  </button>
                  <button
                    onClick={() => setActiveViewTab("data")}
                    className={`pb-2 text-xs font-semibold border-b-2 transition ${
                      activeViewTab === "data"
                        ? "border-blue-600 text-blue-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    Data Preview ({chartData?.row_count ?? 0})
                  </button>
                  <button
                    onClick={() => setActiveViewTab("sql")}
                    className={`pb-2 text-xs font-semibold border-b-2 transition ${
                      activeViewTab === "sql"
                        ? "border-blue-600 text-blue-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    Generated Dialect SQL
                  </button>
                </div>

                {chartData && (
                  <div className="flex items-center gap-2 pb-1.5 text-[11px] text-slate-500">
                    <Clock className="w-3.5 h-3.5" />
                    <span>{chartData.duration_ms} ms</span>
                  </div>
                )}
              </div>

              {/* View Content Canvas */}
              <div className="flex-1 overflow-auto p-4 flex flex-col justify-center relative">
                {/* 1. Visualization Tab */}
                {activeViewTab === "chart" && (
                  <div className="h-full w-full flex flex-col justify-center relative">
                    {/* Error Banner: When query fails, display error clearly without rendering stale charts */}
                    {queryError && (
                      <div className="m-4 p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-800 flex items-start gap-3 shadow-sm">
                        <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
                        <div className="space-y-1">
                          <h4 className="font-bold text-red-900">Query Execution Error</h4>
                          <p className="leading-relaxed">{queryError}</p>
                        </div>
                      </div>
                    )}

                    {/* Loading State: Prevents stale data from masquerading as fresh query result */}
                    {runQueryMutation.isPending && (
                      <div className="absolute inset-0 bg-white/80 backdrop-blur-xs z-20 flex flex-col items-center justify-center text-slate-600 text-xs">
                        <RefreshCw className="w-8 h-8 text-blue-600 animate-spin mb-3" />
                        <span className="font-semibold text-slate-800">
                          Executing Query Against DuckDB...
                        </span>
                        <span className="text-slate-400 mt-1">Generating live visualization</span>
                      </div>
                    )}

                    {/* Chart Render */}
                    {!queryError && plugin && chartProps ? (
                      <div className="h-full w-full">
                        <plugin.Renderer {...chartProps} />
                      </div>
                    ) : !queryError ? (
                      <div className="h-full flex flex-col items-center justify-center text-slate-500 text-xs py-16 px-4">
                        <div className="w-14 h-14 rounded-2xl bg-blue-50 flex items-center justify-center text-blue-600 mb-4 border border-blue-100 shadow-sm">
                          <BarChart3 className="w-7 h-7" />
                        </div>
                        <h3 className="text-base font-semibold text-slate-800 mb-1">
                          Ready to Explore {currentDataset?.name || "Dataset"}
                        </h3>
                        <p className="text-slate-500 max-w-md text-center mb-6 leading-relaxed">
                          Selected chart:{" "}
                          <span className="font-semibold text-slate-700">
                            {plugin?.metadata.name || selectedVizType}
                          </span>
                          .
                          {selectedDimension && (
                            <>
                              {" "}
                              Grouping by{" "}
                              <span className="font-semibold text-blue-700 font-mono bg-blue-50 px-1.5 py-0.5 rounded">
                                {selectedDimension}
                              </span>
                              .
                            </>
                          )}
                        </p>
                        <button
                          onClick={() => runQueryMutation.mutate()}
                          disabled={runQueryMutation.isPending}
                          className="inline-flex items-center gap-2 px-5 py-2.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 active:bg-blue-800 rounded-lg shadow transition hover:shadow-md disabled:opacity-50"
                        >
                          <Play className="w-4 h-4 fill-current" />
                          Run Query & Generate Chart
                        </button>
                      </div>
                    ) : null}
                  </div>
                )}

                {/* 2. Data Preview Tab */}
                {activeViewTab === "data" && (
                  <div className="h-full overflow-auto border border-slate-200 rounded-lg">
                    {chartData && chartData.rows.length > 0 ? (
                      <table className="w-full text-left text-xs font-mono">
                        <thead className="bg-slate-100 text-slate-700 sticky top-0 border-b border-slate-200 font-semibold">
                          <tr>
                            {chartData.columns.map((col) => (
                              <th key={col} className="px-3 py-2 whitespace-nowrap">
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 text-[11px]">
                          {chartData.rows.map((row, rIdx) => (
                            <tr key={rIdx} className="hover:bg-slate-50">
                              {row.map((val, cIdx) => (
                                <td
                                  key={cIdx}
                                  className="px-3 py-1.5 whitespace-nowrap text-slate-800"
                                >
                                  {val !== null && val !== undefined ? String(val) : "null"}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <div className="p-8 text-center text-slate-400 text-xs">
                        {queryError ? "Query failed. No records to display." : "No query results to display. Click 'Run Query'."}
                      </div>
                    )}
                  </div>
                )}

                {/* 3. SQL Tab */}
                {activeViewTab === "sql" && (
                  <div className="h-full overflow-auto bg-slate-900 text-slate-100 p-4 rounded-lg font-mono text-xs">
                    {chartData?.sql ? (
                      <pre className="whitespace-pre-wrap">{chartData.sql}</pre>
                    ) : (
                      <div className="text-slate-500">Run query to view generated dialect SQL.</div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Save Chart Modal */}
          {isSaveModalOpen && (
            <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
              <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 space-y-4">
                <h3 className="font-bold text-base text-slate-900">
                  {editingChartId ? "Update Chart" : "Save Chart"}
                </h3>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Chart Title *
                  </label>
                  <input
                    type="text"
                    value={chartTitle}
                    onChange={(e) => setChartTitle(e.target.value)}
                    placeholder="e.g. Salary Distribution by Department"
                    className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Description
                  </label>
                  <input
                    type="text"
                    value={chartDescription}
                    onChange={(e) => setChartDescription(e.target.value)}
                    placeholder="Optional notes or insights"
                    className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Add to Dashboard
                  </label>
                  <select
                    value={targetDashboardId}
                    onChange={(e) => setTargetDashboardId(e.target.value)}
                    className="w-full px-3 py-1.5 text-xs border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 bg-white"
                  >
                    <option value="auto">
                      Auto-link to {currentDataset?.name ? `${currentDataset.name} Dashboard` : "Dataset Dashboard"} (Recommended)
                    </option>
                    {dashboardList.map((d: any) => (
                      <option key={d.id} value={d.id}>
                        {d.title}
                      </option>
                    ))}
                    <option value="none">Do not add to any dashboard</option>
                  </select>
                  <p className="text-[11px] text-slate-400 mt-1">
                    Your chart will instantly reflect as a tile in the selected dashboard.
                  </p>
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    onClick={() => setIsSaveModalOpen(false)}
                    className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => saveChartMutation.mutate()}
                    disabled={!chartTitle.trim() || saveChartMutation.isPending}
                    className="px-4 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded shadow-sm disabled:opacity-50"
                  >
                    {saveChartMutation.isPending ? "Saving..." : "Save Chart"}
                  </button>
                </div>
              </div>
            </div>
          )}
          {/* Floating AI Button at bottom-right dedicated to the open dataset */}
          <div className="fixed bottom-6 right-6 z-40 flex items-center">
            <button
              onClick={() => setIsDatasetAIDrawerOpen(true)}
              className="group relative flex items-center gap-2 px-4 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-full shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-200 ring-4 ring-blue-500/20"
              title={`Ask AI about ${currentDataset?.name || "this dataset"}`}
            >
              <Sparkles className="w-5 h-5 animate-pulse text-amber-300" />
              <span className="text-xs font-bold tracking-wide">
                Ask AI: {currentDataset?.name ? currentDataset.name.slice(0, 20) : "Dataset"}
              </span>
            </button>
          </div>

          {/* Dedicated AI Drawer bound specifically to the current open dataset */}
          <AIDrawer
            isOpen={isDatasetAIDrawerOpen}
            onClose={() => setIsDatasetAIDrawerOpen(false)}
            datasetId={selectedDatasetId || currentDataset?.id}
            datasetName={currentDataset?.name}
          />
        </div>
      )}
    </div>
  );
};

export default ChartsPage;