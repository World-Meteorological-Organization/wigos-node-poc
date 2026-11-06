// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import ConceptField from "./ConceptField.vue";

const option = (code, label) => ({ code, label, id: `http://codes.wmo.int/wmdr/X/${code}` });
const SHORT = [option("a", "Alpha"), option("b", "Beta")];
const LONG = Array.from({ length: 20 }, (_, i) => option(String(200 + i), i % 2 ? `Air temperature ${i}` : `Wind speed ${i}`));

let wrapper;
let warn;

function mountField(props) {
  wrapper = mount(ConceptField, {
    props: { label: "Concept", ...props },
    global: { plugins: [createVuetify()] },
    attachTo: document.body,
  });
  return wrapper;
}

const menuItems = () => [...document.querySelectorAll(".v-overlay-container .v-list-item")].map((el) => el.textContent.trim());
const lastEmitted = () => wrapper.emitted("update:modelValue").at(-1)[0];

beforeEach(() => {
  warn = vi.spyOn(console, "warn").mockImplementation(() => {});
});
afterEach(() => {
  wrapper?.unmount();
  expect(warn.mock.calls.filter(([m]) => String(m).includes("[Vue warn]"))).toEqual([]);
  warn.mockRestore();
  document.body.innerHTML = "";
});

describe("ConceptField", () => {
  it("keeps a value that isn't in the codelist visible", () => {
    mountField({ options: SHORT, modelValue: { id: "zz", title: "Retired value" } });
    expect(wrapper.text()).toContain("Retired value");
  });

  it("matches a stored concept by URI before notation", () => {
    const options = [option("x", "First"), { code: "x", label: "Second", id: "http://other/x" }];
    mountField({ options, modelValue: { id: "x", url: "http://other/x" } });
    expect(wrapper.text()).toContain("Second");
  });

  it("filters long codelists on every typed term, against label and notation", async () => {
    mountField({ options: LONG, modelValue: null });
    const input = wrapper.find("input");
    await input.trigger("focus");
    await input.setValue("air 21");
    await flushPromises();

    // "Air temperature 13"/"15"... have notations 213/215..., "air" and "21" both match.
    expect(menuItems().length).toBeGreaterThan(0);
    expect(menuItems().every((text) => text.startsWith("Air temperature") && text.includes("21"))).toBe(true);
  });

  it("fills the concept from the chosen option", async () => {
    mountField({ options: SHORT, modelValue: null });
    await wrapper.findComponent({ name: "VSelect" }).vm.$emit("update:modelValue", "http://codes.wmo.int/wmdr/X/b");
    expect(lastEmitted()).toEqual({ id: "b", title: "Beta", url: "http://codes.wmo.int/wmdr/X/b" });
  });

  it("edits the notation and details as free text without a codelist", async () => {
    mountField({ modelValue: null });
    await wrapper.find("input").setValue("12345");
    expect(lastEmitted()).toEqual({ id: "12345" });
  });
});
