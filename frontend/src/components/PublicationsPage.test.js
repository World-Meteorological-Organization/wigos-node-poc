// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import PublicationsPage from "./PublicationsPage.vue";
import { listPublications, retryPublication } from "../api";

vi.mock("../api", () => ({ listPublications: vi.fn(), retryPublication: vi.fn() }));

const makeRow = (fields = {}) => ({
  station_id: 7,
  wigos_identifier: "0-756-0-a",
  name: "Alpha",
  status: "processed",
  updated: "2026-11-02T10:00:00Z",
  changed_by: "someone",
  finished_at: "2026-11-02T10:00:01Z",
  last_error: "",
  files: [],
  can_retry: false,
  ...fields,
});

const failedRow = (fields = {}) =>
  makeRow({ status: "failed", last_error: "wis2:wnm: broker down", can_retry: true, ...fields });

const respond = (results, count = results.length) => listPublications.mockResolvedValue({ count, results });

let wrapper;
let warn;

async function mountPage() {
  wrapper = mount(PublicationsPage, { global: { plugins: [createVuetify()] }, attachTo: document.body });
  await flushPromises();
  return wrapper;
}

const button = (text) => wrapper.findAll("button").find((b) => b.text() === text);
const retryButton = () => button("Retry");

beforeEach(() => {
  warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  listPublications.mockReset();
  retryPublication.mockReset();
});
afterEach(() => {
  wrapper?.unmount();
  expect(warn.mock.calls.filter(([m]) => String(m).includes("[Vue warn]"))).toEqual([]);
  warn.mockRestore();
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("PublicationsPage", () => {
  it("lists one row per station, who last changed it and how publishing went", async () => {
    respond([makeRow({ station_id: 8, wigos_identifier: "0-756-0-b", status: "pending", changed_by: null }), makeRow()]);
    await mountPage();

    const rows = wrapper.findAll("tbody tr");
    expect(rows).toHaveLength(2);
    expect(rows[0].text()).toContain("0-756-0-b");
    expect(rows[0].text()).toContain("Administrator");
    expect(rows[0].text()).toContain("Pending");
    expect(rows[1].text()).toContain("0-756-0-a");
    expect(rows[1].text()).toContain("someone");
    expect(rows[1].text()).toContain("Processed");
  });

  it("says so when there is nothing yet", async () => {
    respond([]);
    await mountPage();
    expect(wrapper.text()).toContain("None of your stations have been published yet.");
  });

  it("shows why loading failed", async () => {
    listPublications.mockRejectedValue(new Error("nope"));
    await mountPage();
    expect(wrapper.text()).toContain("Error: nope");
  });

  it("shows a failed station's error and offers a retry", async () => {
    respond([failedRow()]);
    await mountPage();
    expect(wrapper.text()).toContain("Publishing failed");
    expect(wrapper.text()).toContain("wis2:wnm: broker down");
    expect(retryButton()).toBeTruthy();
  });

  it("offers no retry when the station can't be retried", async () => {
    respond([makeRow()]);
    await mountPage();
    expect(retryButton()).toBeUndefined();
  });

  it("retries the station and shows the new state", async () => {
    respond([failedRow()]);
    await mountPage();
    retryPublication.mockResolvedValue(makeRow({ status: "pending" }));
    respond([makeRow({ status: "processed" })]);

    await retryButton().trigger("click");
    await flushPromises();

    expect(retryPublication).toHaveBeenCalledWith(7);
    expect(wrapper.text()).toContain("Processed");
    expect(retryButton()).toBeUndefined();
  });

  it("shows why a retry was refused and updates the list", async () => {
    respond([failedRow()]);
    await mountPage();
    retryPublication.mockRejectedValue(new Error("This station can't be retried: its job may still be running"));
    respond([failedRow()]);

    await retryButton().trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("0-756-0-a: This station can't be retried: its job may still be running");
    expect(listPublications).toHaveBeenCalledTimes(2);
  });

  it("filters by status from the server", async () => {
    respond([makeRow()]);
    await mountPage();
    expect(listPublications).toHaveBeenLastCalledWith({ status: null, limit: 50, offset: 0 });

    respond([]);
    wrapper.findComponent({ name: "VSelect" }).vm.$emit("update:modelValue", "failed");
    await flushPromises();

    expect(listPublications).toHaveBeenLastCalledWith({ status: "failed", limit: 50, offset: 0 });
    expect(wrapper.text()).toContain("No stations with this status.");
  });

  it("says when it has new data, so the counter can follow", async () => {
    respond([]);
    await mountPage();
    expect(wrapper.emitted("changed")).toHaveLength(1);
    await button("Refresh").trigger("click");
    await flushPromises();
    expect(wrapper.emitted("changed")).toHaveLength(2);
  });

  it("shows more when there are more", async () => {
    respond([makeRow()], 60);
    await mountPage();

    await button("Show more").trigger("click");
    await flushPromises();

    expect(listPublications).toHaveBeenLastCalledWith({ status: null, limit: 51, offset: 0 });
  });

  it("offers no more when everything is shown", async () => {
    respond([makeRow()]);
    await mountPage();
    expect(button("Show more")).toBeUndefined();
  });

  it("refreshes by itself only while a station is on its way", async () => {
    vi.useFakeTimers();
    respond([makeRow({ status: "pending" })]);
    await mountPage();
    expect(listPublications).toHaveBeenCalledTimes(1);

    respond([makeRow({ status: "processed" })]);
    await vi.advanceTimersByTimeAsync(5000);
    expect(listPublications).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("Processed");

    await vi.advanceTimersByTimeAsync(20000);
    expect(listPublications).toHaveBeenCalledTimes(2);
  });

  it("stops refreshing when leaving the page", async () => {
    vi.useFakeTimers();
    respond([makeRow({ status: "pending" })]);
    await mountPage();

    wrapper.unmount();
    wrapper = null;
    await vi.advanceTimersByTimeAsync(20000);

    expect(listPublications).toHaveBeenCalledTimes(1);
  });
});
