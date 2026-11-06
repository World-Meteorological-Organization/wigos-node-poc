import { describe, expect, it } from "vitest";
import { dayFromPicker, describeInterval, intervalError, pickerFromDay, readBound } from "./interval";

describe("readBound", () => {
  it.each([
    ["2020", "year", "2020"],
    ["2020-01", "month", "January 2020"],
    ["2020-01-31", "day", "31 January 2020"],
    ["2020-01-31T06:00:00Z", "datetime", "31 January 2020, 06:00:00 UTC"],
    ["2020-01-31T06:00:00.5Z", "datetime", "31 January 2020, 06:00:00 UTC"],
    ["T06:00Z", "time", "06:00 UTC, time of day"],
    ["T06Z", "time", "06:00 UTC, time of day"],
  ])("reads %s as a %s", (value, kind, label) => {
    expect(readBound(value)).toMatchObject({ kind, label });
  });

  it("tells empty, open and invalid bounds apart", () => {
    expect(readBound("").kind).toBe("empty");
    expect(readBound(" .. ").kind).toBe("open");
    expect(readBound("last year").kind).toBe("invalid");
  });

  it.each(["2020-13", "2020-02-30", "2021-02-29", "2020-01-01T24:00:00Z", "T25:00Z"])("rejects %s, which isn't a real date or time", (value) => {
    expect(readBound(value)).toMatchObject({ kind: "invalid", message: "Not a valid date or time" });
  });

  it("accepts only full days for affiliation and territory dates", () => {
    expect(readBound("2020-01-31", { daysOnly: true }).kind).toBe("day");
    expect(readBound("2020", { daysOnly: true })).toMatchObject({ kind: "invalid", message: "Use a date as YYYY-MM-DD" });
    expect(readBound("..", { daysOnly: true }).kind).toBe("open");
  });
});

describe("intervalError", () => {
  it("accepts an end in the same period as the start", () => {
    expect(intervalError("2020", "2020")).toBeNull();
    expect(intervalError("2020-01", "2020-01-31")).toBeNull();
  });

  it("reports an end before the start", () => {
    expect(intervalError("2020", "2019-12-31")).toBe("The end is before the start");
    expect(intervalError("T18:00Z", "T06:00Z")).toBe("The end is before the start");
  });

  it("doesn't compare open, invalid or mixed-scale bounds", () => {
    expect(intervalError("2020", "..")).toBeNull();
    expect(intervalError("2020", "soon")).toBeNull();
    expect(intervalError("2020", "T06:00Z")).toBeNull();
  });
});

describe("describeInterval", () => {
  it.each([
    ["2020-01", "..", "Since January 2020, ongoing"],
    ["2020-01", "", "Since January 2020, ongoing"],
    ["..", "2015-03", "Until end of March 2015"],
    ["2010", "2015-03", "2010 – end of March 2015"],
    ["2026-06", "2026", "June 2026 – end of 2026"],
    ["2010", "2015-03-31", "2010 – 31 March 2015"],
    ["2010", "2015-03-31T12:00:00Z", "2010 – 31 March 2015, 12:00:00 UTC"],
    ["..", "..", ""],
    ["", "", ""],
    ["someday", "..", "Since someday, ongoing"],
  ])("describes %s to %s", (start, end, text) => {
    expect(describeInterval(start, end)).toBe(text);
  });
});

describe("date picker values", () => {
  it("converts between the picker's local date and a day bound", () => {
    expect(dayFromPicker(new Date(2020, 0, 31))).toBe("2020-01-31");
    expect(dayFromPicker("2020-01-31")).toBe("2020-01-31");
    expect(dayFromPicker(pickerFromDay("2020-02-29"))).toBe("2020-02-29");
  });

  it("opens the picker empty for anything but a day", () => {
    expect(pickerFromDay("2020-01")).toBeNull();
    expect(pickerFromDay("..")).toBeNull();
  });
});
