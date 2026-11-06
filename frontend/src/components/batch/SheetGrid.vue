<script setup>
import { computed, ref, watch } from "vue";
import { cellState, codelistLabel, isCellChanged, isCellEditable, isEditable, normalizeCell } from "../../batch/common";
import { exportSheet, mergeSheet, pastedTable, readSheet } from "../../batch/sheetIO";
import { codelistOptions } from "../../codelists";
import SheetCellEditor from "./SheetCellEditor.vue";
import SheetFillInput from "./SheetFillInput.vue";

// An Excel-like grid over batch rows (see src/batch/common.js). Key columns
// are read-only; every other cell is edited in place. Rows are never added
// or removed here, apart from an operation's own `actions` slot.
//
// Keyboard: arrows/Tab move, Enter/F2 or typing edits, Esc cancels, Delete
// clears. A tab-separated block pasted from Excel fills from the active cell.
//
// A plain table with native inputs: a Vuetify field per cell would be too
// heavy for thousands of rows. `rows` and `selectedIds` are replaced, never
// mutated.

const CHECKBOX_WIDTH = 36;

const props = defineProps({
  sheet: { type: Object, required: true },
  codelists: { type: Object, required: true },
  cellStatus: { type: Function, default: null },
  exportName: { type: String, default: "batch" },
});
const rows = defineModel("rows", { type: Array, required: true });
const selectedIds = defineModel("selectedIds", { type: Set, required: true });

const columns = computed(() => props.sheet.columns);
const container = ref(null);
const fileInput = ref(null);
const active = ref({ r: 0, c: 0 });
// { value } while a cell is edited. Cleared before anything else when an
// edit ends, so the blur that follows Enter doesn't commit a second time.
const editing = ref(null);
const filter = ref("");
const importState = ref(null);

const keyColumns = computed(() => columns.value.filter((column) => !isEditable(column)));
const visibleRows = computed(() => {
  const terms = filter.value.toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return rows.value;
  return rows.value.filter((row) => {
    const haystack = keyColumns.value.map((column) => row.cells[column.key] ?? "").join(" ").toLowerCase();
    return terms.every((term) => haystack.includes(term));
  });
});

// Sticky offsets for the checkbox and key columns.
const stickyLeft = computed(() => {
  const offsets = {};
  let left = CHECKBOX_WIDTH;
  columns.value.forEach((column) => {
    if (isEditable(column)) return;
    offsets[column.key] = left;
    left += column.width || 140;
  });
  return offsets;
});

const r = computed(() => Math.min(active.value.r, Math.max(visibleRows.value.length - 1, 0)));
const c = computed(() => Math.min(active.value.c, columns.value.length - 1));
const activeRow = computed(() => visibleRows.value[r.value]);
const activeColumn = computed(() => columns.value[c.value]);

watch(
  [r, c],
  () => {
    container.value?.querySelector(`[data-cell="${r.value}:${c.value}"]`)?.scrollIntoView({ block: "nearest", inline: "nearest" });
  },
  { flush: "post" }
);

const displayValue = (column, value) =>
  column.kind === "codelist" && value ? codelistLabel(codelistOptions(column.codelist, props.codelists), value) : value;

// updates: [{ rowId, key, value }]; values are normalized here. An added row
// is re-synced with the operation (e.g. moved to the observation it names).
function setCells(updates) {
  const byRow = new Map();
  updates.forEach(({ rowId, key, value }) => {
    const column = columns.value.find((col) => col.key === key);
    const row = rows.value.find((r) => r.id === rowId);
    if (!column || !isCellEditable(column, row)) return;
    if (!byRow.has(rowId)) byRow.set(rowId, {});
    byRow.get(rowId)[key] = normalizeCell(column, value, props.codelists, row);
  });
  if (!byRow.size) return;
  rows.value = rows.value.map((row) => {
    if (!byRow.has(row.id)) return row;
    const next = { ...row, cells: { ...row.cells, ...byRow.get(row.id) } };
    return (next.isNew && props.sheet.syncNewRow?.(next)) || next;
  });
}

function move(direction) {
  const deltas = { up: [-1, 0], down: [1, 0], left: [0, -1], right: [0, 1] };
  const [dr, dc] = deltas[direction] || [0, 0];
  active.value = {
    r: Math.min(Math.max(r.value + dr, 0), Math.max(visibleRows.value.length - 1, 0)),
    c: Math.min(Math.max(c.value + dc, 0), columns.value.length - 1),
  };
}

function startEditing(initial) {
  const row = activeRow.value;
  const column = activeColumn.value;
  if (!row || !isCellEditable(column, row)) return;
  // A dropdown can't start from a typed character; it opens on the current value.
  if (column.kind === "codelist" || column.choices) initial = undefined;
  editing.value = { value: initial ?? row.cells[column.key] ?? "" };
}

function stopEditing(commit, direction) {
  const current = editing.value;
  if (!current) return;
  editing.value = null;
  if (commit && activeRow.value) setCells([{ rowId: activeRow.value.id, key: activeColumn.value.key, value: current.value }]);
  container.value?.focus();
  if (direction) move(direction);
}

function handleKeydown(e) {
  if (editing.value || e.target !== container.value) return;
  const row = activeRow.value;
  const column = activeColumn.value;
  const arrows = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };
  if (arrows[e.key]) {
    e.preventDefault();
    move(arrows[e.key]);
  } else if (e.key === "Tab") {
    e.preventDefault();
    move(e.shiftKey ? "left" : "right");
  } else if (e.key === "Enter" || e.key === "F2") {
    e.preventDefault();
    startEditing();
  } else if ((e.key === "Delete" || e.key === "Backspace") && row && isCellEditable(column, row)) {
    e.preventDefault();
    setCells([{ rowId: row.id, key: column.key, value: "" }]);
  } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
    e.preventDefault();
    startEditing(e.key);
  }
}

function handlePaste(e) {
  if (editing.value || !activeRow.value) return;
  const text = e.clipboardData.getData("text/plain");
  if (!text) return;
  e.preventDefault();
  // Whole rows are matched to the grid rows like an import.
  const table = pastedTable(text, props.sheet);
  if (table) {
    mergeTable(table, "Pasted rows");
    return;
  }
  const lines = text.replace(/\r?\n$/, "").split(/\r?\n/);
  const updates = [];
  // Rows beyond the last one are ignored, never added.
  lines.forEach((line, i) => {
    const row = visibleRows.value[r.value + i];
    if (!row) return;
    line.split("\t").forEach((value, j) => {
      const column = columns.value[c.value + j];
      if (column && isCellEditable(column, row)) updates.push({ rowId: row.id, key: column.key, value });
    });
  });
  setCells(updates);
}

function handleCopy(e) {
  if (editing.value || !activeRow.value) return;
  e.preventDefault();
  e.clipboardData.setData("text/plain", activeRow.value.cells[activeColumn.value.key] ?? "");
}

function fill(column, value) {
  setCells(rows.value.filter((row) => selectedIds.value.has(row.id)).map((row) => ({ rowId: row.id, key: column.key, value })));
}

function resetCell() {
  const row = activeRow.value;
  const column = activeColumn.value;
  if (!row || !isCellEditable(column, row)) return;
  setCells([{ rowId: row.id, key: column.key, value: row.original[column.key] ?? "" }]);
}

function resetAll() {
  rows.value = rows.value.map((row) => ({ ...row, cells: { ...row.original } }));
}

// Applies a file's or a paste's table; `source` names it in the report.
function mergeTable(table, source) {
  const { rows: next, report } = mergeSheet(table, props.sheet, rows.value, props.codelists);
  if (!report.error) rows.value = next;
  importState.value = { status: "done", file: source, report };
}

async function handleImport(file) {
  importState.value = { status: "loading" };
  try {
    mergeTable(await readSheet(file), file.name);
  } catch (err) {
    importState.value = { status: "done", file: file.name, report: { error: `Couldn't read the file: ${err.message}` } };
  }
}

function onFileChosen(e) {
  const file = e.target.files?.[0];
  e.target.value = "";
  if (file) handleImport(file);
}

const allVisibleSelected = computed(
  () => visibleRows.value.length > 0 && visibleRows.value.every((row) => selectedIds.value.has(row.id))
);
function toggleAll() {
  const next = new Set(selectedIds.value);
  const select = !allVisibleSelected.value;
  visibleRows.value.forEach((row) => (select ? next.add(row.id) : next.delete(row.id)));
  selectedIds.value = next;
}
function toggleRow(id) {
  const next = new Set(selectedIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  selectedIds.value = next;
}

const tableWidth = computed(() => CHECKBOX_WIDTH + columns.value.reduce((sum, column) => sum + (column.width || 140), 0));
const activeChanged = computed(
  () => !!activeRow.value && isEditable(activeColumn.value) && isCellChanged(activeRow.value, activeColumn.value.key)
);
const anyChanged = computed(() =>
  rows.value.some((row) => columns.value.some((column) => isEditable(column) && isCellChanged(row, column.key)))
);

// Cell states for the visible rows, computed once per change instead of
// several times per cell while rendering.
const cellStates = computed(() =>
  visibleRows.value.map((row) => columns.value.map((column) => cellState(row, column, props.codelists, props.cellStatus)))
);

function cellClasses(column, state, isActive) {
  return [
    "sheet-cell",
    isEditable(column) ? "" : "sheet-sticky sheet-key",
    !isEditable(column) && state.editable ? "sheet-key-editable" : "",
    isEditable(column) && !state.editable ? "sheet-locked" : "",
    state.changed ? "sheet-changed" : "",
    state.error ? "sheet-invalid" : "",
    isActive ? "sheet-active" : "",
  ];
}

function cellTitle(row, column, state) {
  return (
    [
      isEditable(column) && !state.editable ? "Identifies this row; it can only be set on added rows" : null,
      state.error,
      state.hint,
      state.changed ? `Was: ${displayValue(column, row.original[column.key] ?? "") || "(empty)"}` : null,
      column.kind === "codelist" && state.value ? `Notation: ${state.value}` : null,
    ]
      .filter(Boolean)
      .join("\n") || undefined
  );
}

const isActiveCell = (ri, ci) => ri === r.value && ci === c.value;

function onCellMousedown(e, ri, ci) {
  if (isActiveCell(ri, ci) && editing.value) return;
  e.preventDefault();
  stopEditing(true);
  active.value = { r: ri, c: ci };
  container.value?.focus();
}

// The mousedown before it has already made the cell active.
function onCellDblclick(ri, ci) {
  const state = cellStates.value[ri][ci];
  if (state.editable) editing.value = { value: state.value };
}

const importWarning = computed(() => {
  const report = importState.value?.report;
  return !!report && !report.error && (report.unmatched.length > 0 || report.unknownHeaders.length > 0);
});
</script>

<template>
  <div class="sheet">
    <div class="sheet-toolbar">
      <v-text-field
        v-model="filter"
        class="sheet-filter"
        type="search"
        placeholder="Filter rows…"
        prepend-inner-icon="mdi-magnify"
        aria-label="Filter rows by station, WIGOS ID or observed property"
        hide-details
      />
      <slot name="actions" />
      <v-spacer />
      <v-btn variant="text" :disabled="!activeChanged" @click="resetCell">Reset cell</v-btn>
      <v-btn variant="text" :disabled="!anyChanged" @click="resetAll">Reset all</v-btn>
      <v-btn variant="tonal" color="secondary" prepend-icon="mdi-upload" @click="fileInput?.click()">
        Import CSV/Excel
      </v-btn>
      <input
        ref="fileInput"
        type="file"
        hidden
        accept=".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        @change="onFileChosen"
      />
      <v-btn variant="tonal" color="secondary" prepend-icon="mdi-download" @click="exportSheet(columns, rows, 'csv', exportName)">
        Export CSV
      </v-btn>
      <v-btn variant="tonal" color="secondary" prepend-icon="mdi-download" @click="exportSheet(columns, rows, 'xlsx', exportName)">
        Export Excel
      </v-btn>
    </div>

    <v-alert v-if="importState?.status === 'loading'" class="mb-3" type="info" variant="tonal" density="compact">
      Importing…
    </v-alert>
    <v-alert
      v-else-if="importState?.status === 'done'"
      class="mb-3"
      :type="importState.report.error ? 'error' : importWarning ? 'warning' : 'success'"
      variant="tonal"
      density="compact"
      closable
      @click:close="importState = null"
    >
      <template v-if="importState.report.error">{{ importState.file }}: {{ importState.report.error }}</template>
      <template v-else>
        <strong>{{ importState.file }}</strong>: {{ importState.report.matched }} rows matched,
        {{ importState.report.changedCells }} cells changed<template v-if="importState.report.added > 0"
          >, {{ importState.report.added }} rows added</template
        >.
        <div v-if="importState.report.restored > 0">
          {{ importState.report.restored }}
          {{ importState.report.restored === 1 ? "cell was" : "cells were" }} kept as they were: Excel had reformatted
          them (e.g. 12-12 as 12-Dec, or a long number as 3.2E+11). Use Export Excel to edit in Excel without this.
        </div>
        <div v-if="importState.report.unmatched.length > 0">
          {{ importState.report.unmatched.length }} rows not matched to a station in this batch and ignored:
          {{ importState.report.unmatched.slice(0, 10).join(", ") }}{{ importState.report.unmatched.length > 10 ? "…" : "" }}
        </div>
        <div v-if="importState.report.unknownHeaders.length > 0">
          Unknown columns ignored: {{ importState.report.unknownHeaders.join(", ") }}
        </div>
      </template>
    </v-alert>

    <div
      ref="container"
      class="sheet-scroll"
      tabindex="0"
      role="grid"
      :aria-rowcount="visibleRows.length"
      @keydown="handleKeydown"
      @paste="handlePaste"
      @copy="handleCopy"
    >
      <table class="sheet-table" :style="{ width: `${tableWidth}px` }">
        <colgroup>
          <col :style="{ width: `${CHECKBOX_WIDTH}px` }" />
          <col v-for="column in columns" :key="column.key" :style="{ width: `${column.width || 140}px` }" />
        </colgroup>
        <thead>
          <tr>
            <th class="sheet-sticky sheet-check" style="left: 0">
              <input type="checkbox" :checked="allVisibleSelected" aria-label="Select all rows" @change="toggleAll" />
            </th>
            <th
              v-for="column in columns"
              :key="column.key"
              :class="isEditable(column) ? '' : 'sheet-sticky sheet-key'"
              :style="isEditable(column) ? undefined : { left: `${stickyLeft[column.key]}px` }"
              :title="column.lockedOnExisting ? `${column.key}\nIdentifies existing rows; set only on added rows` : column.key"
            >
              <v-icon v-if="column.lockedOnExisting" icon="mdi-lock-outline" size="x-small" class="sheet-lock" />
              {{ column.label }}<span v-if="column.required" class="required-mark">*</span>
            </th>
          </tr>
          <tr v-if="selectedIds.size > 0" class="sheet-fill-row">
            <th class="sheet-sticky sheet-check" style="left: 0" />
            <template v-for="column in columns" :key="column.key">
              <th v-if="isEditable(column)">
                <SheetFillInput :column="column" :codelists="codelists" @fill="(value) => fill(column, value)" />
              </th>
              <th v-else class="sheet-sticky sheet-key" :style="{ left: `${stickyLeft[column.key]}px` }">
                <span v-if="column === keyColumns[keyColumns.length - 1]" class="sheet-fill-label">
                  Fill {{ selectedIds.size }} selected →
                </span>
              </th>
            </template>
          </tr>
        </thead>
        <tbody>
          <tr v-if="visibleRows.length === 0">
            <td :colspan="columns.length + 1" class="sheet-empty">
              {{ rows.length ? "No rows match the filter." : "Nothing to edit for the selected stations." }}
            </td>
          </tr>
          <tr
            v-for="(row, ri) in visibleRows"
            :key="row.id"
            :class="{ 'sheet-row-selected': selectedIds.has(row.id), 'sheet-row-new': row.isNew }"
          >
            <td class="sheet-sticky sheet-check" style="left: 0">
              <input
                type="checkbox"
                :checked="selectedIds.has(row.id)"
                :aria-label="`Select row ${row.id}`"
                @change="toggleRow(row.id)"
              />
            </td>
            <td
              v-for="(column, ci) in columns"
              :key="column.key"
              :data-cell="`${ri}:${ci}`"
              :class="cellClasses(column, cellStates[ri][ci], isActiveCell(ri, ci))"
              :style="isEditable(column) ? undefined : { left: `${stickyLeft[column.key]}px` }"
              :title="cellTitle(row, column, cellStates[ri][ci])"
              @mousedown="onCellMousedown($event, ri, ci)"
              @dblclick="onCellDblclick(ri, ci)"
            >
              <SheetCellEditor
                v-if="isActiveCell(ri, ci) && editing"
                v-model="editing.value"
                :column="column"
                :choices="column.choices ? column.choices(row) : null"
                :codelists="codelists"
                @commit="(direction) => stopEditing(true, direction)"
                @cancel="stopEditing(false)"
              />
              <span v-else class="sheet-value">
                <v-icon
                  v-if="isEditable(column) && !cellStates[ri][ci].editable"
                  icon="mdi-lock-outline"
                  size="x-small"
                  class="sheet-lock"
                />
                {{ displayValue(column, cellStates[ri][ci].value) }}
                <span v-if="cellStates[ri][ci].hint" class="sheet-hint"> · {{ cellStates[ri][ci].hint }}</span>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="sheet-help">
      Click a cell and type to edit; Enter or Tab confirms, Esc cancels. Paste a block copied from Excel to fill from the
      selected cell; whole rows (all columns, or with the header) are matched to their rows like an import instead.
      <v-icon icon="mdi-lock-outline" size="x-small" /> cells identify existing rows and can only be set on added rows.
      Lists are separated by ";".
      <template v-if="filter"> Showing {{ visibleRows.length }} of {{ rows.length }} rows.</template>
    </div>
  </div>
</template>

<style scoped>
.sheet-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.sheet-filter {
  flex: 0 0 16rem;
}

.sheet-scroll {
  overflow: auto;
  max-height: 65vh;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}

.sheet-scroll:focus {
  outline: none;
  box-shadow: 0 0 0 3px #dbeafe;
}

.sheet-table {
  table-layout: fixed;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 0.85rem;
}

.sheet-table th,
.sheet-table td {
  height: 2rem;
  padding: 0;
  border-right: 1px solid #e2e8f0;
  border-bottom: 1px solid #e2e8f0;
  background: #fff;
}

.sheet-table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  padding: 0.4rem 0.5rem;
  background: #f8fafc;
  text-align: left;
  font-size: 0.75rem;
  font-weight: 600;
  color: #475569;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sheet-table thead tr.sheet-fill-row th {
  top: 2rem;
  padding: 0.2rem;
  background: #eff6ff;
}

.sheet-table .sheet-sticky {
  position: sticky;
  z-index: 1;
}

.sheet-table thead .sheet-sticky {
  z-index: 3;
}

.sheet-table .sheet-check {
  text-align: center;
}

.sheet-table .sheet-key {
  background: #f8fafc;
  color: #475569;
}

.sheet-cell {
  cursor: cell;
}

.sheet-value {
  display: block;
  padding: 0 0.5rem;
  line-height: 2rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sheet-hint {
  color: #64748b;
  font-size: 0.75rem;
}

.sheet-table td.sheet-changed {
  background: #fef9c3;
}

.sheet-table td.sheet-invalid {
  box-shadow: inset 0 0 0 2px #dc2626;
}

.sheet-table td.sheet-active {
  box-shadow: inset 0 0 0 2px #2563eb;
}

.sheet-table td.sheet-active.sheet-invalid {
  box-shadow: inset 0 0 0 2px #2563eb, inset 0 0 0 4px #dc2626;
}

.sheet-table .sheet-row-selected td {
  background: #eff6ff;
}

.sheet-table .sheet-row-selected td.sheet-changed {
  background: #fef9c3;
}

/* Identifies an existing row (e.g. an affiliation's programme and start):
   hatched and muted, also on selected rows. Added rows show the same
   columns as ordinary editable cells. */
.sheet-table td.sheet-locked,
.sheet-table .sheet-row-selected td.sheet-locked {
  background: repeating-linear-gradient(-45deg, #f1f5f9 0 6px, #e8edf3 6px 12px);
  color: #94a3b8;
  cursor: not-allowed;
}

.sheet-lock {
  margin-right: 0.2rem;
  vertical-align: -1px;
  opacity: 0.8;
}

.sheet-row-new td.sheet-key {
  font-style: italic;
}

/* A key cell an added row can set (its observed property). */
.sheet-table td.sheet-key-editable {
  background: #fff;
  color: inherit;
  cursor: cell;
}

/* Marks an added row next to its checkbox. */
.sheet-table .sheet-row-new td.sheet-check {
  box-shadow: inset 3px 0 0 #059669;
}

.sheet-fill-label {
  font-size: 0.75rem;
  color: #1d4ed8;
}

.sheet-table td.sheet-empty {
  padding: 1rem;
  color: #64748b;
  text-align: center;
}

.sheet-help {
  margin-top: 0.5rem;
  font-size: 0.8rem;
  color: #64748b;
}
</style>
