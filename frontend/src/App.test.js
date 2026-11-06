// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { ref } from "vue";
import { createVuetify } from "vuetify";
import App from "./App.vue";
import { listPublications } from "./api";
import { useAuth } from "./composables/useAuth";

vi.mock("./composables/useAuth", () => ({ useAuth: vi.fn() }));
vi.mock("./api", () => ({ listPublications: vi.fn() }));

let wrapper;
let warn;

function mountApp(status = "authenticated") {
  useAuth.mockReturnValue({
    status: ref(status),
    user: ref({ username: "someone", email: "someone@example.com" }),
    setUser: vi.fn(),
    logout: vi.fn(),
  });
  wrapper = mount(App, {
    global: {
      plugins: [createVuetify()],
      stubs: {
        LoginPage: { template: '<div class="login-page" />' },
        StationsList: { template: '<div class="stations-page" />', emits: ["new", "edit", "batch", "changed"] },
        WmdrForm: { template: '<div class="form-page" />', emits: ["saved", "cancel"] },
        BatchWizard: { template: '<div class="batch-page" />', emits: ["applied", "close"] },
        PublicationsPage: { template: '<div class="publications-page" />', emits: ["changed"] },
      },
    },
    attachTo: document.body,
  });
  return flushPromises();
}

const hasSidebar = () => wrapper.find(".v-navigation-drawer").exists();
const navItem = (title) => wrapper.findAll(".v-navigation-drawer .v-list-item").find((item) => item.text() === title);
const stations = () => wrapper.findComponent(".stations-page");

beforeEach(() => {
  warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  listPublications.mockReset();
  listPublications.mockResolvedValue({ count: 0, results: [] });
});
afterEach(() => {
  wrapper?.unmount();
  expect(warn.mock.calls.filter(([m]) => String(m).includes("[Vue warn]"))).toEqual([]);
  warn.mockRestore();
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("App sidebar", () => {
  it("opens on the stations page, and moves between the main pages", async () => {
    await mountApp();
    expect(hasSidebar()).toBe(true);
    expect(wrapper.find(".stations-page").exists()).toBe(true);
    expect(navItem("Stations").classes()).toContain("v-list-item--active");

    await navItem("Publishing").trigger("click");
    expect(wrapper.find(".publications-page").exists()).toBe(true);
    expect(wrapper.find(".stations-page").exists()).toBe(false);
    expect(navItem("Publishing").classes()).toContain("v-list-item--active");
    expect(navItem("Stations").classes()).not.toContain("v-list-item--active");

    await navItem("Stations").trigger("click");
    expect(wrapper.find(".stations-page").exists()).toBe(true);
  });

  it("isn't there on the station form or the batch wizard", async () => {
    await mountApp();

    await stations().vm.$emit("new");
    await flushPromises();
    expect(wrapper.find(".form-page").exists()).toBe(true);
    expect(hasSidebar()).toBe(false);

    wrapper.findComponent(".form-page").vm.$emit("cancel");
    await flushPromises();
    expect(hasSidebar()).toBe(true);

    await stations().vm.$emit("batch", [1]);
    await flushPromises();
    expect(wrapper.find(".batch-page").exists()).toBe(true);
    expect(hasSidebar()).toBe(false);
  });

  it("isn't there before logging in", async () => {
    await mountApp("anonymous");
    expect(wrapper.find(".login-page").exists()).toBe(true);
    expect(hasSidebar()).toBe(false);
  });

  it("counts the failed stations on the Publishing item", async () => {
    listPublications.mockResolvedValue({ count: 3, results: [] });
    await mountApp();
    expect(listPublications).toHaveBeenCalledWith({ status: "failed", limit: 1 });
    expect(navItem("Publishing3")).toBeTruthy();
    expect(navItem("Stations")).toBeTruthy();
  });

  it("shows no counter without failures", async () => {
    await mountApp();
    expect(navItem("Publishing")).toBeTruthy();
    expect(wrapper.find(".v-navigation-drawer .v-chip").exists()).toBe(false);
  });

  it("keeps the counter up to date while the sidebar shows, and only then", async () => {
    vi.useFakeTimers();
    await mountApp();
    listPublications.mockResolvedValue({ count: 1, results: [] });
    await vi.advanceTimersByTimeAsync(30000);
    expect(navItem("Publishing1")).toBeTruthy();

    await stations().vm.$emit("new");
    await flushPromises();
    const calls = listPublications.mock.calls.length;
    await vi.advanceTimersByTimeAsync(90000);
    expect(listPublications).toHaveBeenCalledTimes(calls);
  });

  it("updates the counter when the publishing page has new data, such as after a retry", async () => {
    listPublications.mockResolvedValue({ count: 2, results: [] });
    await mountApp();
    await navItem("Publishing2").trigger("click");

    listPublications.mockResolvedValue({ count: 1, results: [] });
    wrapper.findComponent(".publications-page").vm.$emit("changed");
    await flushPromises();

    expect(navItem("Publishing1")).toBeTruthy();
  });

  it("updates the counter when the stations page sees new statuses, such as a save that failed", async () => {
    await mountApp();
    expect(wrapper.find(".v-navigation-drawer .v-chip").exists()).toBe(false);

    listPublications.mockResolvedValue({ count: 1, results: [] });
    stations().vm.$emit("changed");
    await flushPromises();

    expect(navItem("Publishing1")).toBeTruthy();
  });

  it("keeps the newest count when an older answer arrives last", async () => {
    await mountApp();
    let answerOlder;
    listPublications.mockReturnValueOnce(new Promise((resolve) => (answerOlder = resolve)));
    stations().vm.$emit("changed");
    listPublications.mockResolvedValueOnce({ count: 1, results: [] });
    stations().vm.$emit("changed");
    await flushPromises();

    answerOlder({ count: 0, results: [] });
    await flushPromises();

    expect(navItem("Publishing1")).toBeTruthy();
  });

  it("works without the counter when it can't be loaded", async () => {
    listPublications.mockRejectedValue(new Error("nope"));
    await mountApp();
    expect(navItem("Publishing")).toBeTruthy();
  });
});
