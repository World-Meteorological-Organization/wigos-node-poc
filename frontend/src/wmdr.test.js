import { describe, expect, it } from "vitest";
import {
  buildWmdrRecord,
  parseWmdrRecord,
  withNodeFields,
  parseConcept,
  splitWigosId,
  joinWigosId,
  wigosIdsToCheck,
  duplicateWigosIds,
} from "./wmdr";
import { validateWmdrRecord } from "./wmdrSchema";
// examples/0-20008-0-THE.json from wmo-im/wmdr2.
import upstreamExample from "./__fixtures__/upstream-example.json";
// Sets every property defined in schemas/wmdr2-bundled.json.
import allFields from "./__fixtures__/all-fields.json";
// A record saved before the move to the wmdr2-bundled schema.
import legacyRecord from "./__fixtures__/legacy-record.json";

const NOW = new Date("2026-10-21T12:00:00.000Z");
const ORIGIN = "https://node.example.org";
const roundTrip = (record) => buildWmdrRecord(parseWmdrRecord(record), { now: NOW, origin: ORIGIN });
const selfLink = (wsi) => ({ rel: "self", href: `${ORIGIN}/api/wmdrv2/wsi/${wsi}`, type: "application/geo+json" });
// The builder sets `updated` to the time the record is built and adds the self link.
const withNodeFieldsNow = (record) => ({
  ...record,
  properties: { ...record.properties, updated: NOW.toISOString() },
  links: [selfLink(record.id), ...record.links],
});

// The builder always writes milliseconds ("...00.000Z"); upstream omits them.
function withMilliseconds(value) {
  if (typeof value === "string") return value.replace(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z$/, "$1.000Z");
  if (Array.isArray(value)) return value.map(withMilliseconds);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, withMilliseconds(v)]));
  }
  return value;
}

describe.each([
  ["upstream example", upstreamExample],
  ["all-fields record", allFields],
])("%s", (_, record) => {
  it("is valid against the schema", () => {
    expect(validateWmdrRecord(record)).toEqual([]);
  });

  it("round-trips through the form without losing or adding anything but the node's fields", () => {
    const rebuilt = roundTrip(record);
    expect(rebuilt).toEqual(withNodeFieldsNow(withMilliseconds(record)));
    // A second round trip keeps one self link, not two.
    expect(roundTrip(rebuilt)).toEqual(rebuilt);
    expect(validateWmdrRecord(rebuilt)).toEqual([]);
  });
});

describe("legacy records", () => {
  const rebuilt = roundTrip(legacyRecord);
  const json = JSON.stringify(rebuilt);

  it("drops fields that aren't in the schema", () => {
    ["observingCapabilities", "deployments", "keywords", "serialNumber", "referenceSurfaces"].forEach((key) => {
      expect(json).not.toContain(`"${key}"`);
    });
    expect(rebuilt.properties.programAffiliations).toBeUndefined();
  });

  it("converts observing capabilities into observations", () => {
    const [observation] = rebuilt.properties.observations;
    expect(observation.observedProperty).toEqual({
      id: "12166",
      url: "http://codes.wmo.int/wmdr/ObservedVariableAtmosphere/12166",
    });
    expect(observation.programAffiliations).toEqual([{ programAffiliation: { id: "Gbon" } }]);
    const [configuration] = observation.configurations;
    expect(configuration.id).toBe("2302192");
    expect(configuration.observingMethod).toEqual({ id: "Eye" });
    expect(configuration.instrumentSerialNumber).toBe("12-121-212");
    expect(configuration.instrument).toEqual({ id: "321321321312", manufacturer: "SUTRON", model: "12-12" });
    expect(configuration.verticalDistance).toEqual({ distances: [2123112], referenceSurface: { id: "22128" } });
  });

  it("reports only the gaps the old format can't fill", () => {
    expect(validateWmdrRecord(rebuilt)).toEqual([
      "observations[1].configurations[1].time.resolution has an invalid format",
      "observations[1].configurations[1].verticalDistance.unit is required",
      "links[2].rel is required",
    ]);
  });
});

describe("buildWmdrRecord", () => {
  it("keeps an observation's contacts, which the form doesn't edit", () => {
    const contacts = [{ organization: "Observation team" }];
    const [observation] = allFields.properties.observations;
    const record = { ...allFields, properties: { ...allFields.properties, observations: [{ ...observation, contacts }] } };

    const form = parseWmdrRecord(record);
    form.observations[0] = { ...form.observations[0], observedGeometry: null }; // as a row edit does

    expect(buildWmdrRecord(form).properties.observations[0].contacts).toEqual(contacts);
  });

  it("drops a stored resolution on the station's time, so the record can be saved", () => {
    const rebuilt = roundTrip({ ...allFields, time: { interval: ["2020-01", ".."], resolution: "PT1H" } });
    expect(rebuilt.time).toEqual({ interval: ["2020-01", ".."] });
    expect(validateWmdrRecord(rebuilt)).toEqual([]);
  });

  it("reports every required field for an empty form", () => {
    expect(validateWmdrRecord(roundTrip({}))).toEqual([
      "id has an invalid format",
      "geometry.longitude must be number",
      "geometry.latitude must be number",
      "contacts needs at least 1 item(s)",
      "observations needs at least 1 item(s)",
      "links needs at least 1 item(s)",
    ]);
  });

  it("keeps a contact without an organization so the schema check flags it", () => {
    const form = parseWmdrRecord(allFields);
    form.contacts[0].organization = "";
    const record = buildWmdrRecord(form);
    expect(record.properties.contacts[0].name).toBe("A Person");
    expect(validateWmdrRecord(record)).toContain("contacts[1].organization is required");
  });

  it("drops entries left completely empty", () => {
    const form = parseWmdrRecord(allFields);
    form.contacts.push(parseWmdrRecord({ properties: { contacts: [{}] } }).contacts[0]);
    form.links.push({ href: "", rel: "about", type: "", hreflang: "", title: "", length: "" });
    const record = buildWmdrRecord(form);
    expect(record.properties.contacts).toHaveLength(1);
    expect(record.links.map((link) => link.rel)).toEqual(["self", "about"]);
  });

  it("keeps half-filled concepts so a missing id is reported", () => {
    const form = parseWmdrRecord(allFields);
    form.wmoRegion = { id: "", title: "Europe" };
    expect(validateWmdrRecord(buildWmdrRecord(form))).toContain("wmoRegion.id is required");
  });

  it("normalizes phone numbers to the schema's format", () => {
    const form = parseWmdrRecord(allFields);
    form.contacts[0].phones[0].value = " +41 (79) 123-45.67 ";
    expect(buildWmdrRecord(form).properties.contacts[0].phones[0].value).toBe("+41791234567");
  });

  it("writes open interval bounds as '..'", () => {
    const form = parseWmdrRecord(allFields);
    form.time = { ...form.time, intervalStart: "", intervalEnd: "2021" };
    expect(buildWmdrRecord(form).time.interval).toEqual(["..", "2021"]);
  });

  it("sets created for a new record and keeps the stored one", () => {
    expect(roundTrip({}).properties.created).toBe(NOW.toISOString());
    expect(roundTrip(allFields).properties.created).toBe(allFields.properties.created);
  });

  it("sets updated to the build time, whatever was stored", () => {
    expect(roundTrip(allFields).properties.updated).toBe(NOW.toISOString());
  });

  it("assigns an id to a configuration without one and keeps a stored one", () => {
    const form = parseWmdrRecord(allFields);
    const [configuration] = form.observations[0].configurations;
    form.observations[0].configurations.push({ ...configuration, id: "" });
    const [kept, assigned] = buildWmdrRecord(form).properties.observations[0].configurations;
    expect(kept.id).toBe("c1");
    expect(assigned.id).toMatch(/\S/);
    expect(assigned.id).not.toBe("c1");
  });

  it("keeps a stored configuration that has nothing but its id", () => {
    const stored = structuredClone(allFields);
    stored.properties.observations[0].configurations = [{ id: "Vue", time: null }];
    const rebuilt = roundTrip(stored);
    expect(rebuilt.properties.observations[0].configurations).toEqual([{ id: "Vue", time: null }]);
    expect(validateWmdrRecord(rebuilt)).toEqual([]);
  });

  it("drops a configuration left empty instead of giving it an id", () => {
    const form = parseWmdrRecord(allFields);
    form.observations[0].configurations.push(parseWmdrRecord({ properties: { observations: [{ configurations: [{}] }] } }).observations[0].configurations[0]);
    expect(buildWmdrRecord(form).properties.observations[0].configurations).toHaveLength(1);
  });

  it("links to the record by its primary WIGOS ID and hides the self link from the form", () => {
    const stored = { ...allFields, links: [{ rel: "self", href: "https://old.example.org/x" }, ...allFields.links] };
    const form = parseWmdrRecord(stored);
    expect(form.links.map((link) => link.rel)).toEqual(["about"]);
    expect(buildWmdrRecord(form, { origin: ORIGIN }).links[0]).toEqual(selfLink("0-20000-0-12345"));
  });

  it("adds no self link before the WIGOS ID is entered", () => {
    expect(roundTrip({}).links).toEqual([]);
  });
});

describe("withNodeFields", () => {
  it("sets updated and replaces the self link after a renumbering", () => {
    const stored = roundTrip(allFields);
    const renumbered = withNodeFields({ ...stored, id: "0-20000-0-NEW" }, { now: new Date("2027-01-01T00:00:00.000Z"), origin: ORIGIN });
    expect(renumbered.properties.updated).toBe("2027-01-01T00:00:00.000Z");
    expect(renumbered.links.filter((link) => link.rel === "self")).toEqual([selfLink("0-20000-0-NEW")]);
    expect(renumbered.links.slice(1)).toEqual(stored.links.slice(1));
  });

  it("always sets the logo's rel to icon", () => {
    const form = parseWmdrRecord(allFields);
    form.contacts[0].logo.rel = "";
    expect(buildWmdrRecord(form).properties.contacts[0].logo.rel).toBe("icon");
  });
});

describe("parseConcept", () => {
  it("splits a legacy concept URI into notation and url", () => {
    expect(parseConcept("http://codes.wmo.int/wmdr/ObservedVariableAtmosphere/224")).toEqual({
      id: "224",
      url: "http://codes.wmo.int/wmdr/ObservedVariableAtmosphere/224",
    });
  });

  it("treats a legacy plain string as the notation", () => {
    expect(parseConcept("landFixed")).toEqual({ id: "landFixed" });
  });

  it("returns null for empty values", () => {
    expect(parseConcept("")).toBeNull();
    expect(parseConcept(null)).toBeNull();
  });
});

describe("WIGOS ID helpers", () => {
  it("round-trips an ID whose local part contains hyphens", () => {
    expect(joinWigosId(splitWigosId("0-20000-0-AB-12"))).toBe("0-20000-0-AB-12");
  });

  it("joins an ID with every part cleared to an empty string", () => {
    expect(joinWigosId({ scheme: "0", issuer: "", issue: "", local: "" })).toBe("");
    expect(joinWigosId({ scheme: "0", issuer: "20000", issue: "", local: "" })).toBe("0-20000--");
  });

  it("checks only well-formed IDs the station doesn't already own, once each", () => {
    const ids = ["0-20000-0-B", "", "0-20000-", "0-20000-0-A", "0-20000-0-B", "0-533-1-OWN"];
    expect(wigosIdsToCheck(ids, ["0-533-1-OWN"])).toEqual(["0-20000-0-A", "0-20000-0-B"]);
  });

  it("finds IDs entered more than once, ignoring empty rows", () => {
    expect(duplicateWigosIds(["0-1-0-A", "", "0-1-0-B", "", "0-1-0-A"])).toEqual(new Set(["0-1-0-A"]));
  });
});
