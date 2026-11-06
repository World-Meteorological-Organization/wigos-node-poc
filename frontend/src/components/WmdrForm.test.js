// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import WmdrForm from "./WmdrForm.vue";
import { getCodelist, getStation } from "../api";
import { buildWmdrRecord, parseWmdrRecord } from "../wmdr";
import allFields from "../__fixtures__/all-fields.json";

// Smoke tests: the form mounts with Vuetify, renders without Vue warnings and
// produces the same record as the logic it wraps. Behaviour details are left
// to the manual parity checklist (docs/vue-vuetify-migration-plan.md).

vi.mock("../api", () => ({
  getCodelist: vi.fn(),
  getStation: vi.fn(),
  saveStation: vi.fn(),
  checkWigosIdentifiers: vi.fn(() => Promise.resolve({})),
}));

const option = (scheme, code, label) => ({ code, label, id: `http://codes.wmo.int/wmdr/${scheme}/${code}` });
// Over 15 entries, so the observed property field is a filterable autocomplete.
const atmosphere = Array.from({ length: 20 }, (_, i) => option("ObservedVariableAtmosphere", String(220 + i), `Variable ${220 + i}`));
const CODELISTS = {
  FacilityType: [option("FacilityType", "landFixed", "Land (fixed)")],
  ObservedVariableAtmosphere: atmosphere,
  ProgramAffiliation: [option("ProgramAffiliation", "GOS", "GOS")],
};

let wrapper;
let warn;

function mountForm(props = {}) {
  wrapper = mount(WmdrForm, { props, global: { plugins: [createVuetify()] }, attachTo: document.body });
  return wrapper;
}

// The input inside the Vuetify field whose label reads `label`.
function inputByLabel(label) {
  const field = wrapper.findAll(".v-field").find((f) => f.find(".v-field-label").exists() && f.find(".v-field-label").text() === label);
  if (!field) throw new Error(`No field labelled "${label}"`);
  return field.find("input, textarea");
}

const preview = () => JSON.parse(wrapper.find(".geojson-preview").text());
const vueWarnings = () => warn.mock.calls.filter(([message]) => String(message).includes("[Vue warn]"));

beforeEach(() => {
  warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  getCodelist.mockImplementation((scheme) => Promise.resolve(CODELISTS[scheme] || []));
});
afterEach(() => {
  wrapper?.unmount();
  warn.mockRestore();
  document.body.innerHTML = "";
});

describe("WmdrForm", () => {
  it("renders a new record and updates the preview as fields are edited", async () => {
    mountForm();
    await flushPromises();

    await inputByLabel("Title *").setValue("Station A");
    await inputByLabel("Latitude *").setValue("46.2");

    expect(preview().properties.title).toBe("Station A");
    expect(preview().geometry.coordinates[1]).toBe(46.2);
    expect(wrapper.text()).toContain("Not yet valid against the WMDR2 schema");
    // The station's time has no resolution; configurations keep theirs.
    expect(() => inputByLabel("Resolution")).toThrow();
    expect(vueWarnings()).toEqual([]);
  });

  it("loads a station for editing and round-trips it unchanged", async () => {
    getStation.mockResolvedValue(allFields);
    mountForm({ stationId: 7 });
    await flushPromises();

    expect(getStation).toHaveBeenCalledWith(7);
    // `updated` is the time each record was built, so it's compared apart.
    const shown = preview();
    const expected = buildWmdrRecord(parseWmdrRecord(allFields), { now: new Date(shown.properties.updated) });
    expect(shown).toEqual(expected);
    // The primary ID can't change while editing.
    expect(inputByLabel("Local identifier").attributes("disabled")).toBeDefined();
    expect(vueWarnings()).toEqual([]);
  });

  it("edits the station's interval with a read-back and an Ongoing box", async () => {
    mountForm();
    await flushPromises();

    await inputByLabel("From").setValue("2020-01");
    expect(wrapper.text()).toContain("Since January 2020, ongoing");
    expect(preview().time.interval).toEqual(["2020-01", ".."]);

    await inputByLabel("To").setValue("2019");
    expect(wrapper.text()).toContain("The end is before the start");

    const ongoing = wrapper.findAll(".v-checkbox").find((box) => box.text() === "Ongoing");
    await ongoing.find("input").setValue(true);
    expect(inputByLabel("To").attributes("disabled")).toBeDefined();
    expect(preview().time.interval).toEqual(["2020-01", ".."]);
    expect(wrapper.text()).toContain("Since January 2020, ongoing");
    expect(vueWarnings()).toEqual([]);
  });

  it("adds an expanded contact card and edits it", async () => {
    mountForm();
    await flushPromises();

    const addContact = wrapper.findAll("button").find((b) => b.text() === "Add Contact");
    await addContact.trigger("click");
    await inputByLabel("Organization *").setValue("WMO");

    expect(preview().properties.contacts[0].organization).toBe("WMO");
    expect(vueWarnings()).toEqual([]);
  });

  it("summarises configurations, including one with nothing but its id", async () => {
    const record = structuredClone(allFields);
    record.properties.observations[0].configurations.push({ id: "Vue", time: null });
    getStation.mockResolvedValue(record);
    mountForm({ stationId: 7 });
    await flushPromises();

    const observationCard = wrapper
      .findAll(".nested-card")
      .find((card) => card.find(".nested-card-header span").text() === "224");
    await observationCard.findAll("button").find((b) => b.text() === "Expand").trigger("click");

    expect(observationCard.text()).toContain("Vaisala HMP155 · Since 2020, ongoing · operational");
    expect(observationCard.text()).toContain("No details yet");
    expect(vueWarnings()).toEqual([]);
  });

  it("opens a nested list item in the drill-in dialog", async () => {
    getStation.mockResolvedValue(allFields);
    mountForm({ stationId: 7 });
    await flushPromises();

    // Loaded observations start collapsed. The fixture's observed property has
    // no title, so the card is summarised by its notation.
    const observationCard = wrapper
      .findAll(".nested-card")
      .find((card) => card.find(".nested-card-header span").text() === "224");
    await observationCard.findAll("button").find((b) => b.text() === "Expand").trigger("click");
    const editAffiliation = observationCard.findAll("button").find((b) => b.text().includes("Edit details"));
    await editAffiliation.trigger("click");
    await flushPromises();

    const dialog = document.querySelector(".v-overlay-container .v-card");
    expect(dialog?.textContent).toContain("Program affiliation 1");
    expect(dialog?.textContent).toContain("Programme/network *");
    expect(vueWarnings()).toEqual([]);
  });
});
