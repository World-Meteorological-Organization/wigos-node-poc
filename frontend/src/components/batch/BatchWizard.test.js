// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import BatchWizard from "./BatchWizard.vue";
import { getStations, saveStationsBatch } from "../../api";
import allFields from "../../__fixtures__/all-fields.json";

// Smoke test: one batch from picking the operation to the results, with
// the API mocked. Grid details are in SheetGrid.test.js.

vi.mock("../../api", () => ({
  getCodelist: vi.fn(() => Promise.resolve([])),
  getStations: vi.fn(),
  saveStationsBatch: vi.fn(),
  checkWigosIdentifiers: vi.fn(() => Promise.resolve({})),
}));

const NEW_ID = "0-20000-0-99999";

let wrapper;
let warn;

const vueWarnings = () => warn.mock.calls.filter(([message]) => String(message).includes("[Vue warn]"));
const button = (text) => wrapper.findAll("button").find((b) => b.text().includes(text));
const dialogButton = (text) =>
  [...document.querySelectorAll(".v-overlay-container button")].find((b) => b.textContent.includes(text));

beforeEach(() => {
  warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  getStations.mockResolvedValue({ 7: allFields });
  saveStationsBatch.mockImplementation((updates) =>
    Promise.resolve({
      summary: { ok: updates.length, error: 0 },
      results: updates.map((update, index) => ({ index, station_id: update.station_id, wsi: update.wmdrv2.id, status: "ok" })),
    })
  );
});
afterEach(() => {
  wrapper?.unmount();
  warn.mockRestore();
  vi.clearAllMocks();
  document.body.innerHTML = "";
});

describe("BatchWizard", () => {
  it("edits WIGOS identifiers, previews with a dry run and applies", async () => {
    wrapper = mount(BatchWizard, {
      props: { stationIds: [7] },
      global: { plugins: [createVuetify()] },
      attachTo: document.body,
    });
    await flushPromises();

    await wrapper.findAll(".operation-card").find((card) => card.text().includes("WIGOS identifiers")).trigger("click");
    await flushPromises();
    expect(getStations).toHaveBeenCalledWith([7]);
    expect(wrapper.find('[data-cell="0:0"]').text()).toBe(allFields.id);
    expect(button("Apply").attributes("disabled")).toBeDefined();

    // Additional ID 2 (column 4) is empty; fill it in.
    await wrapper.find('[data-cell="0:4"]').trigger("mousedown");
    await wrapper.find(".sheet-scroll").trigger("keydown", { key: "Enter" });
    const editor = wrapper.find("input.sheet-editor");
    await editor.setValue(NEW_ID);
    await editor.trigger("keydown", { key: "Enter" });
    expect(wrapper.text()).toContain("1 cell changed in 1 station");

    await button("Apply").trigger("click");
    await flushPromises();
    expect(saveStationsBatch).toHaveBeenLastCalledWith(
      [{ station_id: 7, wmdrv2: expect.objectContaining({ id: allFields.id }) }],
      { dryRun: true }
    );
    const sent = saveStationsBatch.mock.calls[0][0][0].wmdrv2;
    expect(sent.properties.additionalIds).toEqual([...allFields.properties.additionalIds, NEW_ID]);

    const confirm = dialogButton("Confirm and save 1 station");
    expect(confirm.disabled).toBe(false);
    confirm.click();
    await flushPromises();

    expect(saveStationsBatch).toHaveBeenCalledTimes(2);
    expect(saveStationsBatch.mock.calls[1]).toHaveLength(1);
    expect(wrapper.text()).toContain("1 saved, 0 failed.");
    expect(wrapper.emitted("applied")).toEqual([[[]]]);
    expect(vueWarnings()).toEqual([]);
  });

  it("offers a retry when the stations can't be loaded", async () => {
    getStations.mockRejectedValueOnce(new Error("offline"));
    wrapper = mount(BatchWizard, {
      props: { stationIds: [7] },
      global: { plugins: [createVuetify()] },
      attachTo: document.body,
    });
    await wrapper.findAll(".operation-card")[0].trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Couldn't load the stations: offline");

    await button("Retry").trigger("click");
    await flushPromises();
    expect(getStations).toHaveBeenCalledTimes(2);
    expect(wrapper.find(".sheet-table").exists()).toBe(true);
  });
});
