// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import DurationField from "./DurationField.vue";

let wrapper;
let warn;

// Feeds every emitted value back in, as v-model does.
function mountField(modelValue = "") {
  wrapper = mount(DurationField, {
    props: { label: "Resolution", modelValue, "onUpdate:modelValue": (value) => wrapper.setProps({ modelValue: value }) },
    global: { plugins: [createVuetify()] },
    attachTo: document.body,
  });
  return wrapper;
}

const amountInput = () => wrapper.find(".duration-amount input");
const unitSelect = () => wrapper.findComponent({ name: "VSelect" });
const value = () => wrapper.props("modelValue");
const chip = (title) => wrapper.findAll(".v-chip").find((c) => c.text() === title);

beforeEach(() => {
  warn = vi.spyOn(console, "warn").mockImplementation(() => {});
});
afterEach(() => {
  wrapper?.unmount();
  expect(warn.mock.calls.filter(([m]) => String(m).includes("[Vue warn]"))).toEqual([]);
  warn.mockRestore();
  document.body.innerHTML = "";
});

describe("DurationField", () => {
  it("shows a stored duration as a number and a unit", () => {
    mountField("PT10M");
    expect(amountInput().element.value).toBe("10");
    expect(unitSelect().props("modelValue")).toBe("M");
  });

  it("tells minutes and months apart", () => {
    mountField("P1M");
    expect(unitSelect().props("modelValue")).toBe("MO");
  });

  it("writes the duration once both parts are set, and clears it with the number", async () => {
    mountField();
    await amountInput().setValue("3");
    expect(value()).toBe("");
    expect(wrapper.text()).toContain("Choose a unit");

    await unitSelect().vm.$emit("update:modelValue", "H");
    expect(value()).toBe("PT3H");
    await unitSelect().vm.$emit("update:modelValue", "D");
    expect(value()).toBe("P3D");

    await amountInput().setValue("");
    expect(value()).toBe("");
  });

  it("allows a fraction only for seconds", async () => {
    mountField("PT1H");
    await amountInput().setValue("1.5");
    expect(wrapper.text()).toContain("Enter a whole number");
    expect(value()).toBe("PT1H");

    await unitSelect().vm.$emit("update:modelValue", "S");
    expect(value()).toBe("PT1.5S");
  });

  it("sets a quick pick and highlights it", async () => {
    mountField();
    await chip("12H").trigger("click");
    expect(value()).toBe("PT12H");
    expect(amountInput().element.value).toBe("12");
    expect(chip("12H").classes()).toContain("v-chip--variant-flat");

    await chip("1M").trigger("click");
    expect(value()).toBe("P1M");
    expect(unitSelect().props("modelValue")).toBe("MO");

    expect(wrapper.findAll(".v-chip").map((c) => c.text())).toEqual(["30m", "1H", "3H", "6H", "12H", "1D", "1M"]);
    await chip("1D").trigger("click");
    expect(value()).toBe("P1D");
  });

  it("keeps a stored value that isn't one number and unit until another is entered", async () => {
    mountField("P1DT6H");
    expect(wrapper.text()).toContain("Stored as P1DT6H");
    expect(amountInput().element.value).toBe("");

    await chip("30m").trigger("click");
    expect(value()).toBe("PT30M");
    expect(wrapper.text()).not.toContain("Stored as");
  });
});
