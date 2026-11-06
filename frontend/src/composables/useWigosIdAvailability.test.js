import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, ref } from "vue";
import { checkWigosIdentifiers } from "../api";
import { useWigosIdAvailability } from "./useWigosIdAvailability";

vi.mock("../api", () => ({ checkWigosIdentifiers: vi.fn() }));

const TAKEN = "0-20000-0-111";
const FREE = "0-20000-0-222";

// Lets the debounce run out and the mocked request resolve.
async function settle() {
  await nextTick();
  await vi.advanceTimersByTimeAsync(400);
  await nextTick();
}

describe("useWigosIdAvailability", () => {
  let scope;
  beforeEach(() => {
    vi.useFakeTimers();
    checkWigosIdentifiers.mockReset();
    scope = effectScope();
  });
  afterEach(() => {
    scope.stop();
    vi.useRealTimers();
  });

  it("checks well-formed IDs after the debounce, skipping own and malformed ones", async () => {
    checkWigosIdentifiers.mockResolvedValue({ [TAKEN]: 5 });
    const ids = ref([TAKEN, FREE, "0-20000-0-own", "not-an-id"]);
    const statusOf = scope.run(() => useWigosIdAvailability(ids, ["0-20000-0-own"]));

    expect(statusOf(TAKEN)).toBe("checking");
    expect(statusOf("0-20000-0-own")).toBeNull();
    expect(statusOf("not-an-id")).toBeNull();
    await settle();

    expect(checkWigosIdentifiers).toHaveBeenCalledTimes(1);
    expect(checkWigosIdentifiers).toHaveBeenCalledWith([TAKEN, FREE]);
    expect(statusOf(TAKEN)).toBe("taken");
    expect(statusOf(FREE)).toBe("available");
  });

  it("only asks about IDs it hasn't seen, and restarts the debounce on every change", async () => {
    checkWigosIdentifiers.mockResolvedValue({});
    const ids = ref([FREE]);
    const statusOf = scope.run(() => useWigosIdAvailability(ids, []));
    await settle();

    ids.value = [FREE, "0-20000-0-3"];
    await nextTick();
    await vi.advanceTimersByTimeAsync(200);
    ids.value = [FREE, "0-20000-0-33"];
    await settle();

    expect(checkWigosIdentifiers).toHaveBeenCalledTimes(2);
    expect(checkWigosIdentifiers).toHaveBeenLastCalledWith(["0-20000-0-33"]);
    expect(statusOf(FREE)).toBe("available");
  });

  it("reports a failed lookup and retries it when the IDs change", async () => {
    checkWigosIdentifiers.mockRejectedValueOnce(new Error("offline")).mockResolvedValue({});
    const ids = ref([FREE]);
    const statusOf = scope.run(() => useWigosIdAvailability(ids, []));
    await settle();
    expect(statusOf(FREE)).toBe("error");

    ids.value = [FREE, TAKEN];
    await settle();
    expect(checkWigosIdentifiers).toHaveBeenLastCalledWith([TAKEN, FREE]);
    expect(statusOf(FREE)).toBe("available");
  });
});
