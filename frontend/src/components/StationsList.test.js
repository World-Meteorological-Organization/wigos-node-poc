// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createVuetify } from "vuetify";
import StationsList from "./StationsList.vue";
import StationsMap from "./StationsMap.vue";
import { listMyStations } from "../api";

vi.mock("../api", () => ({ listMyStations: vi.fn() }));

// The statuses of Alpha and Beta; Gamma can't be edited, so it never has one.
const stationsWith = (alpha, beta = "processed") => [
  { station_id: 1, wsi: "0-756-0-a", name: "Alpha", latitude: 1, longitude: 2, can_edit: true, publication_status: alpha },
  { station_id: 2, wsi: "0-756-0-b", name: "Beta", latitude: 1, longitude: 2, can_edit: true, publication_status: beta },
  { station_id: 3, wsi: "0-76-0-c", name: "Gamma", latitude: 1, longitude: 2, can_edit: false, publication_status: null },
];

let wrapper;
let warn;

async function mountList() {
  wrapper = mount(StationsList, {
    props: { selected: new Set() },
    global: { plugins: [createVuetify()], stubs: { StationsMap: true } },
    attachTo: document.body,
  });
  await flushPromises();
}

const row = (name) => wrapper.findAll("tbody tr").find((r) => r.text().includes(name));

beforeEach(() => {
  warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  listMyStations.mockReset();
});
afterEach(() => {
  wrapper?.unmount();
  expect(warn.mock.calls.filter(([m]) => String(m).includes("[Vue warn]"))).toEqual([]);
  warn.mockRestore();
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("StationsList publishing status", () => {
  it("shows a chip with each station's status", async () => {
    listMyStations.mockResolvedValue(stationsWith("processed", "failed"));
    await mountList();
    expect(row("Alpha").find(".v-chip").text()).toBe("Processed");
    expect(row("Beta").find(".v-chip").text()).toBe("Publishing failed");
  });

  it("shows a station with no status as unknown", async () => {
    listMyStations.mockResolvedValue(stationsWith(""));
    await mountList();
    expect(row("Alpha").find(".v-chip").text()).toBe("Unknown");
  });

  it("shows no chip for a station the user can't edit", async () => {
    listMyStations.mockResolvedValue(stationsWith("processed"));
    await mountList();
    expect(row("Gamma").find(".v-chip").exists()).toBe(false);
  });

  it("shows why the stations couldn't be loaded", async () => {
    listMyStations.mockRejectedValue(new Error("nope"));
    await mountList();
    expect(wrapper.text()).toContain("Error: nope");
  });

  it("keeps the list when a refresh fails", async () => {
    vi.useFakeTimers();
    listMyStations.mockResolvedValue(stationsWith("pending"));
    await mountList();

    listMyStations.mockRejectedValue(new Error("nope"));
    await vi.advanceTimersByTimeAsync(5000);

    expect(wrapper.findAll("tbody tr")).toHaveLength(3);
    expect(row("Alpha").find(".v-chip").text()).toBe("Pending");
    expect(wrapper.text()).not.toContain("nope");
  });

  it("follows a station until it is through, then stops", async () => {
    vi.useFakeTimers();
    listMyStations.mockResolvedValue(stationsWith("pending"));
    await mountList();
    expect(row("Alpha").find(".v-chip").text()).toBe("Pending");

    listMyStations.mockResolvedValue(stationsWith("processing"));
    await vi.advanceTimersByTimeAsync(5000);
    expect(row("Alpha").find(".v-chip").text()).toBe("Publishing");

    listMyStations.mockResolvedValue(stationsWith("processed"));
    await vi.advanceTimersByTimeAsync(5000);
    expect(row("Alpha").find(".v-chip").text()).toBe("Processed");

    await vi.advanceTimersByTimeAsync(30000);
    expect(listMyStations).toHaveBeenCalledTimes(3);
  });

  it("leaves the map alone while following, so it doesn't fit itself again", async () => {
    vi.useFakeTimers();
    listMyStations.mockResolvedValue(stationsWith("pending"));
    await mountList();
    const shown = wrapper.findComponent(StationsMap).props("stations");

    listMyStations.mockResolvedValue(stationsWith("processed"));
    await vi.advanceTimersByTimeAsync(5000);

    expect(listMyStations).toHaveBeenCalledTimes(2);
    expect(wrapper.findComponent(StationsMap).props("stations")).toBe(shown);
  });

  it("tells the app each time it has new statuses, so a failure reaches the counter", async () => {
    vi.useFakeTimers();
    listMyStations.mockResolvedValue(stationsWith("pending"));
    await mountList();
    expect(wrapper.emitted("changed")).toHaveLength(1);

    listMyStations.mockResolvedValue(stationsWith("failed"));
    await vi.advanceTimersByTimeAsync(5000);
    expect(wrapper.emitted("changed")).toHaveLength(2);
  });

  it("stops following when leaving the page", async () => {
    vi.useFakeTimers();
    listMyStations.mockResolvedValue(stationsWith("pending"));
    await mountList();
    wrapper.unmount();
    wrapper = null;
    await vi.advanceTimersByTimeAsync(30000);
    expect(listMyStations).toHaveBeenCalledTimes(1);
  });
});
