import { computed, toValue } from "vue";
import { splitList } from "../batch/common";
import { idsInRows, ownIdsInRows, rowNote } from "../batch/wigosIds";
import { duplicateWigosIds } from "../wmdr";
import { useWigosIdAvailability } from "./useWigosIdAvailability";

// Duplicate and availability checks for the cells of the WIGOS identifiers
// grid. `active` and `rows` are refs or getters; the ID lists stay empty for
// the other operations. Returns `cellStatus(row, column)` for the grid:
// { error } or { hint }, or null. Called from a template or computed, it
// tracks the availability results.
export function useWigosIdStatus(active, rows) {
  const ids = computed(() => (toValue(active) ? idsInRows(toValue(rows)) : []));
  const ownIds = computed(() => (toValue(active) ? ownIdsInRows(toValue(rows)) : []));
  const availability = useWigosIdAvailability(ids, ownIds);
  const duplicates = computed(() => duplicateWigosIds(ids.value));

  return (row, column) => {
    if (!toValue(active)) return null;
    // A station with more additional IDs than the grid shows keeps the rest.
    if (column.key === "station_name") {
      const note = rowNote(row);
      return note ? { hint: note } : null;
    }
    if (column.kind !== "wsi" && column.kind !== "wsis") return null;
    const cellIds = column.kind === "wsi" ? [row.cells[column.key]].filter(Boolean) : splitList(row.cells[column.key]);
    const duplicate = cellIds.find((id) => duplicates.value.has(id));
    if (duplicate) return { error: `${duplicate} is entered more than once in this batch` };
    const taken = cellIds.find((id) => availability(id) === "taken");
    if (taken) return { error: `${taken} is already registered to another station` };
    if (cellIds.some((id) => availability(id) === "checking")) return { hint: "checking…" };
    if (cellIds.some((id) => availability(id) === "error")) return { hint: "couldn't check availability" };
    return null;
  };
}
