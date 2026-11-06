// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import SheetGrid from "./SheetGrid.vue";
import { makeRow } from "../../batch/common";
import * as affiliations from "../../batch/affiliations";
import upstreamExample from "../../__fixtures__/upstream-example.json";

// The grid's own interaction logic: keyboard navigation, editing, paste.

const SHEET = {
  columns: [
    { key: "station_name", label: "Station", kind: "key" },
    { key: "a", label: "A", kind: "text" },
    { key: "b", label: "B", kind: "number" },
  ],
  importKeys: ["station_name"],
};

const ROWS = ["1", "2", "3"].map((id) => makeRow(id, id, { station_name: `S${id}` }, { a: `a${id}`, b: id }));

let wrapper;
let warn;

function mountGrid() {
  wrapper = mount(SheetGrid, {
    props: {
      sheet: SHEET,
      codelists: {},
      rows: ROWS,
      selectedIds: new Set(),
      // Feed the emitted rows back, as v-model would.
      "onUpdate:rows": (rows) => wrapper.setProps({ rows }),
      "onUpdate:selectedIds": (selectedIds) => wrapper.setProps({ selectedIds }),
    },
    global: { plugins: [createVuetify()] },
    attachTo: document.body,
  });
  return wrapper;
}

const grid = () => wrapper.find(".sheet-scroll");
const cell = (r, c) => wrapper.find(`[data-cell="${r}:${c}"]`);
const activeCell = () => wrapper.find(".sheet-active").attributes("data-cell");
const cellsOf = (key) => wrapper.props("rows").map((row) => row.cells[key]);
const rowUpdates = () => wrapper.emitted("update:rows") || [];
const vueWarnings = () => warn.mock.calls.filter(([message]) => String(message).includes("[Vue warn]"));

async function paste(text) {
  const event = new Event("paste", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "clipboardData", { value: { getData: () => text } });
  grid().element.dispatchEvent(event);
  await wrapper.vm.$nextTick();
}

beforeEach(() => {
  warn = vi.spyOn(console, "warn").mockImplementation(() => {});
});
afterEach(() => {
  wrapper?.unmount();
  warn.mockRestore();
  document.body.innerHTML = "";
});

describe("SheetGrid", () => {
  it("moves the active cell with the arrow keys and Tab, within the grid", async () => {
    mountGrid();
    expect(activeCell()).toBe("0:0");

    await grid().trigger("keydown", { key: "ArrowRight" });
    await grid().trigger("keydown", { key: "ArrowDown" });
    expect(activeCell()).toBe("1:1");

    await grid().trigger("keydown", { key: "Tab" });
    await grid().trigger("keydown", { key: "Tab" });
    expect(activeCell()).toBe("1:2");

    await grid().trigger("keydown", { key: "ArrowUp" });
    await grid().trigger("keydown", { key: "ArrowUp" });
    expect(activeCell()).toBe("0:2");
    expect(vueWarnings()).toEqual([]);
  });

  it("edits on typing and commits once on Enter, despite the blur that follows", async () => {
    mountGrid();
    await cell(0, 1).trigger("mousedown");
    await grid().trigger("keydown", { key: "z" });

    const editor = wrapper.find("input.sheet-editor");
    expect(editor.element.value).toBe("z");
    await editor.setValue("zz");
    await editor.trigger("keydown", { key: "Enter" });
    await editor.trigger("blur");

    expect(rowUpdates()).toHaveLength(1);
    expect(cellsOf("a")).toEqual(["zz", "a2", "a3"]);
    expect(activeCell()).toBe("1:1");
    expect(cell(0, 1).classes()).toContain("sheet-changed");
  });

  it("cancels an edit with Escape", async () => {
    mountGrid();
    await cell(1, 1).trigger("mousedown");
    await grid().trigger("keydown", { key: "F2" });

    const editor = wrapper.find("input.sheet-editor");
    expect(editor.element.value).toBe("a2");
    await editor.setValue("changed");
    await editor.trigger("keydown", { key: "Escape" });

    expect(rowUpdates()).toHaveLength(0);
    expect(wrapper.find("input.sheet-editor").exists()).toBe(false);
  });

  it("doesn't edit key columns", async () => {
    mountGrid();
    await grid().trigger("keydown", { key: "x" });
    await grid().trigger("keydown", { key: "Delete" });

    expect(wrapper.find("input.sheet-editor").exists()).toBe(false);
    expect(rowUpdates()).toHaveLength(0);
  });

  it("pastes a partial block from the active cell, ignoring rows past the end", async () => {
    mountGrid();
    await cell(1, 1).trigger("mousedown");
    await paste("p\t5\nq\t6\nr\t7\n");

    expect(rowUpdates()).toHaveLength(1);
    expect(cellsOf("a")).toEqual(["a1", "p", "q"]);
    expect(cellsOf("b")).toEqual(["1", "5", "6"]);
  });

  it("matches pasted whole rows on their key columns, wherever the active cell is", async () => {
    mountGrid();
    await cell(2, 2).trigger("mousedown");
    // Rows in another order, one unknown; only editable cells are written.
    await paste("S3\tthree\t30\nS1\tone\t10\nS9\tnine\t90\n");

    expect(rowUpdates()).toHaveLength(1);
    expect(cellsOf("a")).toEqual(["one", "a2", "three"]);
    expect(cellsOf("b")).toEqual(["10", "2", "30"]);
    expect(wrapper.text()).toContain("Pasted rows: 2 rows matched, 4 cells changed");
    expect(wrapper.text()).toContain("S9");
  });

  it("shows locked cells as such and keeps them read-only, but not on added rows", async () => {
    const sheet = { ...SHEET, columns: SHEET.columns.map((col) => (col.key === "a" ? { ...col, lockedOnExisting: true } : col)) };
    mountGrid();
    await wrapper.setProps({ sheet, rows: [...ROWS, { ...makeRow("4", "4", { station_name: "S4" }, { a: "", b: "" }), isNew: true }] });

    expect(cell(0, 1).classes()).toContain("sheet-locked");
    expect(cell(0, 1).find(".sheet-lock").exists()).toBe(true);
    expect(cell(3, 1).classes()).not.toContain("sheet-locked");

    await cell(0, 1).trigger("mousedown");
    await grid().trigger("keydown", { key: "Enter" });
    expect(wrapper.find("input.sheet-editor").exists()).toBe(false);

    await cell(3, 1).trigger("mousedown");
    await grid().trigger("keydown", { key: "Enter" });
    expect(wrapper.find("input.sheet-editor").exists()).toBe(true);
  });

  it("offers only the station's observations for the observed property of an added row", async () => {
    const record = structuredClone(upstreamExample);
    record.properties.observations.push({ ...structuredClone(record.properties.observations[0]), observedProperty: { id: "224" } });
    const { rows } = affiliations.addRows(affiliations.toRows([{ stationId: 1, record }]), new Set(["1:0:0"]));
    mountGrid();
    await wrapper.setProps({ sheet: affiliations, rows });

    // Existing rows: read-only. The added row: a dropdown.
    await cell(0, 2).trigger("mousedown");
    await grid().trigger("keydown", { key: "Enter" });
    expect(wrapper.find("select.sheet-editor").exists()).toBe(false);

    const addedIndex = rows.findIndex((row) => row.isNew);
    await cell(addedIndex, 2).trigger("mousedown");
    await grid().trigger("keydown", { key: "Enter" });
    const editor = wrapper.find("select.sheet-editor");
    expect(editor.findAll("option").map((o) => o.text())).toEqual(["12164", "224"]);
    await editor.setValue("224");
    await editor.trigger("keydown", { key: "Enter" });

    const added = wrapper.props("rows")[addedIndex];
    expect(added).toMatchObject({ isNew: true, obsIndex: 1, cells: { observed_property: "224" } });
  });

  it("marks an invalid edited cell", async () => {
    mountGrid();
    await cell(2, 2).trigger("mousedown");
    await grid().trigger("keydown", { key: "Enter" });
    const editor = wrapper.find("input.sheet-editor");
    await editor.setValue("not a number");
    await editor.trigger("keydown", { key: "Enter" });

    expect(cell(2, 2).classes()).toContain("sheet-invalid");
    expect(cell(2, 2).attributes("title")).toContain("Must be a number");
  });

  it("fills a value into the selected rows", async () => {
    mountGrid();
    const checkboxes = wrapper.findAll("tbody input[type=checkbox]");
    await checkboxes[0].setValue(true);
    await checkboxes[2].setValue(true);

    const fill = wrapper.find(".sheet-fill-row input.sheet-fill");
    await fill.setValue("filled");
    await fill.trigger("keydown", { key: "Enter" });

    expect(cellsOf("a")).toEqual(["filled", "a2", "filled"]);
  });
});
