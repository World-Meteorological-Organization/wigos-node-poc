export const WIGOS_ID_PATTERN = /^(0|1|2|3)-([1-9]\d*)-([0-9]+)-([A-Za-z0-9._-]+)$/;
export const CONFORMANCE_CLASS = "http://wigos.wmo.int/spec/wmdr/2/conf/core";

// Record shape follows schemas/wmdr2-bundled.json in wmo-im/wmdr2. Cleaning
// only drops entries the user left completely empty; partially filled entries
// are kept so schema validation can point at what's missing, instead of the
// input silently disappearing from the record.

// A WIGOS ID is scheme-issuer-issue-local. The local part may itself
// contain hyphens, so only the first three separators are split on.
export function splitWigosId(id) {
  const [scheme = "0", issuer = "", issue = "", ...rest] = (id || "").split("-");
  return { scheme: scheme || "0", issuer, issue, local: rest.join("-") };
}

// Clearing every part gives "" rather than "0---", so an emptied additional
// ID row is dropped from the record like any other empty list entry.
export function joinWigosId({ scheme, issuer, issue, local }) {
  if (!issuer && !issue && !local) return "";
  return [scheme || "0", issuer, issue, local].join("-");
}

// IDs worth looking up on the server: well-formed, not already belonging to
// the station being edited, de-duplicated and sorted so the list is stable
// across renders.
export function wigosIdsToCheck(ids, ownIds = []) {
  const own = new Set(ownIds);
  return [...new Set(ids)].filter((id) => WIGOS_ID_PATTERN.test(id) && !own.has(id)).sort();
}

// IDs entered more than once across the primary and additional ID fields.
export function duplicateWigosIds(ids) {
  const seen = new Set();
  const duplicates = new Set();
  for (const id of ids) {
    if (!id) continue;
    if (seen.has(id)) duplicates.add(id);
    seen.add(id);
  }
  return duplicates;
}

const trim = (v) => (v ?? "").toString().trim();

// Configuration ids are assigned here, not typed in. crypto.randomUUID needs a
// secure context (https or localhost), hence the fallback.
function newId() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function cleanStringArray(arr) {
  return (arr || []).map(trim).filter(Boolean);
}

function isoDateTime(value) {
  if (!trim(value)) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? trim(value) : d.toISOString();
}

// Numbers are kept as the raw string when they don't parse, so the schema
// check reports "must be number" rather than the value vanishing.
function toNumber(value) {
  const text = trim(value);
  return text !== "" && !Number.isNaN(Number(text)) ? Number(text) : text;
}

// Concepts ({ id, title?, description?, url? }) reference a WMO codelist
// entry. `id` is the codelist notation (e.g. "landFixed"), matching the
// upstream examples; `url` is the concept URI, which keeps notations
// unambiguous across domains.
const CONCEPT_KEYS = ["id", "title", "description", "url"];

function cleanConcept(concept) {
  const cleaned = {};
  CONCEPT_KEYS.forEach((key) => {
    const value = trim(concept?.[key]);
    if (value) cleaned[key] = value;
  });
  return Object.keys(cleaned).length ? cleaned : null;
}

// [start, end] where an open end is "..". Returns null when both are empty.
function cleanDates(start, end) {
  if (!trim(start) && !trim(end)) return null;
  return [trim(start) || "..", trim(end) || ".."];
}

function cleanPhoneOrEmail(entry, normalize = (v) => v) {
  const value = normalize(trim(entry.value));
  if (!value) return null;
  const cleaned = { value };
  const roles = cleanStringArray(entry.roles);
  if (roles.length) cleaned.roles = roles;
  return cleaned;
}

// The schema wants "+41791234567"; accept the usual spacing and punctuation.
const normalizePhone = (value) => value.replace(/[\s\-.()]/g, "");

function cleanAddress(address) {
  const cleaned = {};
  ["city", "administrativeArea", "postalCode", "country"].forEach((key) => {
    const value = trim(address[key]);
    if (value) cleaned[key] = value;
  });
  const deliveryPoint = cleanStringArray(address.deliveryPoint);
  if (deliveryPoint.length) cleaned.deliveryPoint = deliveryPoint;
  const roles = cleanStringArray(address.roles);
  if (roles.length) cleaned.roles = roles;
  return Object.keys(cleaned).length ? cleaned : null;
}

// Record-level links allow rel/type/hreflang/title/length; contact links and
// logos additionally allow profile/created/updated. A link with nothing but
// its default `rel` counts as empty.
const LINK_KEYS = ["href", "rel", "type", "hreflang", "title"];

function cleanLink(link, { extended = false } = {}) {
  if (!link) return null;
  const cleaned = {};
  LINK_KEYS.forEach((key) => {
    const value = trim(link[key]);
    if (value) cleaned[key] = value;
  });
  if (trim(link.length)) cleaned.length = toNumber(link.length);
  if (extended) {
    const profile = cleanStringArray(link.profile);
    if (profile.length) cleaned.profile = profile;
    ["created", "updated"].forEach((key) => {
      const value = isoDateTime(link[key]);
      if (value) cleaned[key] = value;
    });
  }
  return Object.keys(cleaned).some((key) => key !== "rel") ? cleaned : null;
}

function cleanContact(contact) {
  const organization = trim(contact.organization);
  // Keys are added in schema order so the preview reads like the spec.
  const cleaned = {};

  const identifier = trim(contact.identifier);
  if (identifier) cleaned.identifier = identifier;
  const name = trim(contact.name);
  if (name) cleaned.name = name;
  const position = trim(contact.position);
  if (position) cleaned.position = position;
  if (organization) cleaned.organization = organization;
  const logo = cleanLink(contact.logo, { extended: true });
  if (logo) cleaned.logo = { ...logo, rel: "icon" };

  const phones = (contact.phones || []).map((p) => cleanPhoneOrEmail(p, normalizePhone)).filter(Boolean);
  if (phones.length) cleaned.phones = phones;
  const emails = (contact.emails || []).map((e) => cleanPhoneOrEmail(e)).filter(Boolean);
  if (emails.length) cleaned.emails = emails;
  const addresses = (contact.addresses || []).map(cleanAddress).filter(Boolean);
  if (addresses.length) cleaned.addresses = addresses;
  const links = (contact.links || []).map((link) => cleanLink(link, { extended: true })).filter(Boolean);
  if (links.length) cleaned.links = links;
  const hoursOfService = trim(contact.hoursOfService);
  if (hoursOfService) cleaned.hoursOfService = hoursOfService;
  const contactInstructions = trim(contact.contactInstructions);
  if (contactInstructions) cleaned.contactInstructions = contactInstructions;
  const roles = cleanStringArray(contact.roles);
  if (roles.length) cleaned.roles = roles;

  // A contact missing its organization is kept so the schema check flags it.
  return Object.keys(cleaned).length ? cleaned : null;
}

function cleanTime(time) {
  if (!time) return null;
  const cleaned = {};
  const date = trim(time.date);
  if (date) cleaned.date = date;
  const timestamp = isoDateTime(time.timestamp);
  if (timestamp) cleaned.timestamp = timestamp;
  const interval = cleanDates(time.intervalStart, time.intervalEnd);
  if (interval) cleaned.interval = interval;
  const resolution = trim(time.resolution);
  if (resolution) cleaned.resolution = resolution;
  return Object.keys(cleaned).length ? cleaned : null;
}

function cleanGeometry(geometry) {
  if (!geometry) return null;
  const latitude = trim(geometry.latitude);
  const longitude = trim(geometry.longitude);
  const height = trim(geometry.height);
  if (latitude === "" && longitude === "" && height === "") return null;
  const coordinates = [toNumber(longitude), toNumber(latitude)];
  if (height !== "") coordinates.push(toNumber(height));
  return { type: "Point", coordinates };
}

function cleanExternalId(externalId) {
  const cleaned = {};
  ["scheme", "value"].forEach((key) => {
    const value = trim(externalId[key]);
    if (value) cleaned[key] = value;
  });
  return Object.keys(cleaned).length ? cleaned : null;
}

function cleanTerritory(entry) {
  const territory = cleanConcept(entry.territory);
  const dates = cleanDates(entry.dateStart, entry.dateEnd);
  if (!territory && !dates) return null;
  const cleaned = { territory };
  if (dates) cleaned.dates = dates;
  return cleaned;
}

function cleanInstrument(instrument) {
  const cleaned = {};
  ["id", "manufacturer", "model"].forEach((key) => {
    const value = trim(instrument?.[key]);
    if (value) cleaned[key] = value;
  });
  return Object.keys(cleaned).length ? cleaned : null;
}

function cleanVerticalDistance(verticalDistance) {
  const distances = cleanStringArray(verticalDistance?.distances).map(toNumber);
  const unit = cleanConcept(verticalDistance?.unit);
  const referenceSurface = cleanConcept(verticalDistance?.referenceSurface);
  if (!distances.length && !unit && !referenceSurface) return null;
  const cleaned = { distances };
  if (unit) cleaned.unit = unit;
  if (referenceSurface) cleaned.referenceSurface = referenceSurface;
  return cleaned;
}

function cleanConfiguration(configuration) {
  const cleaned = {};
  // `time` is required on a configuration but may be null.
  cleaned.time = cleanTime(configuration.time);
  const geometry = cleanGeometry(configuration.geometry);
  if (geometry) cleaned.geometry = geometry;
  ["observingMethod", "operatingStatus", "sourceOfObservation"].forEach((key) => {
    const concept = cleanConcept(configuration[key]);
    if (concept) cleaned[key] = concept;
  });
  const instrument = cleanInstrument(configuration.instrument);
  if (instrument) cleaned.instrument = instrument;
  const instrumentSerialNumber = trim(configuration.instrumentSerialNumber);
  if (instrumentSerialNumber) cleaned.instrumentSerialNumber = instrumentSerialNumber;
  const verticalDistance = cleanVerticalDistance(configuration.verticalDistance);
  if (verticalDistance) cleaned.verticalDistance = verticalDistance;
  // A stored id is kept so the batch import can match the configuration, and
  // a stored configuration with nothing but its id stays a configuration. Only
  // one added in the form and left empty is dropped.
  const id = trim(configuration.id);
  if (!id && Object.keys(cleaned).length === 1 && !cleaned.time) return null;
  return { id: id || newId(), ...cleaned };
}

function cleanProgramAffiliation(entry) {
  const programAffiliation = cleanConcept(entry.programAffiliation);
  const reportingStatus = cleanConcept(entry.reportingStatus);
  const dates = cleanDates(entry.dateStart, entry.dateEnd);
  if (!programAffiliation && !reportingStatus && !dates) return null;
  const cleaned = {};
  if (programAffiliation) cleaned.programAffiliation = programAffiliation;
  if (reportingStatus) cleaned.reportingStatus = reportingStatus;
  if (dates) cleaned.dates = dates;
  return cleaned;
}

function cleanObservation(observation) {
  const cleaned = {};
  const observedProperty = cleanConcept(observation.observedProperty);
  if (observedProperty) cleaned.observedProperty = observedProperty;
  const observedGeometry = cleanConcept(observation.observedGeometry);
  if (observedGeometry) cleaned.observedGeometry = observedGeometry;
  cleaned.programAffiliations = (observation.programAffiliations || []).map(cleanProgramAffiliation).filter(Boolean);
  cleaned.configurations = (observation.configurations || []).map(cleanConfiguration).filter(Boolean);
  // Not editable in the form, so kept exactly as stored.
  if (observation.contacts?.length) cleaned.contacts = observation.contacts;
  const isEmpty = !observedProperty && !observedGeometry && !cleaned.programAffiliations.length && !cleaned.configurations.length && !cleaned.contacts;
  return isEmpty ? null : cleaned;
}

// The node's lookup of a record by WIGOS ID (backend: wmdrv2-wsi).
export const SELF_LINK_PATH = "/api/wmdrv2/wsi/";

// The fields this node sets on every record it saves, from the form and from
// the batch wizard alike: `updated` (now) and a `self` link to the record by
// its primary WIGOS ID, replacing any stored one (the ID may have changed).
export function withNodeFields(record, { now = new Date(), origin = globalThis.location?.origin ?? "" } = {}) {
  const links = (record.links || []).filter((link) => link?.rel !== "self");
  const self = record.id
    ? [{ rel: "self", href: `${origin}${SELF_LINK_PATH}${encodeURIComponent(record.id)}`, type: "application/geo+json" }]
    : [];
  return { ...record, properties: { ...record.properties, updated: now.toISOString() }, links: [...self, ...links] };
}

// `created` keeps the stored value (now for a new record); withNodeFields sets
// `updated` and the self link. None of them is edited in the form.
export function buildWmdrRecord(form, { now = new Date(), origin } = {}) {
  const properties = {
    type: "facility",
    title: trim(form.title),
    contacts: (form.contacts || []).map(cleanContact).filter(Boolean),
    observations: (form.observations || []).map(cleanObservation).filter(Boolean),
  };
  properties.created = isoDateTime(form.created) || now.toISOString();

  if (trim(form.description)) properties.description = trim(form.description);
  if (cleanStringArray(form.additionalTitles).length) properties.additionalTitles = cleanStringArray(form.additionalTitles);
  if (cleanStringArray(form.additionalIds).length) properties.additionalIds = cleanStringArray(form.additionalIds);
  const facilityType = cleanConcept(form.facilityType);
  if (facilityType) properties.facilityType = facilityType;
  const wmoRegion = cleanConcept(form.wmoRegion);
  if (wmoRegion) properties.wmoRegion = wmoRegion;
  const territories = (form.territories || []).map(cleanTerritory).filter(Boolean);
  if (territories.length) properties.territories = territories;
  const externalIds = (form.externalIds || []).map(cleanExternalId).filter(Boolean);
  if (externalIds.length) properties.externalIds = externalIds;

  const coordinates = [toNumber(form.longitude), toNumber(form.latitude)];
  if (trim(form.height) !== "") coordinates.push(toNumber(form.height));

  const record = {
    id: trim(form.id),
    conformsTo: [CONFORMANCE_CLASS],
    type: "Feature",
    geometry: {
      type: "Point",
      coordinates,
    },
  };
  // The schema doesn't allow a resolution here, and the form has no field to
  // clear a stored one, which would make the record impossible to save.
  const time = cleanTime(form.time && { ...form.time, resolution: "" });
  if (time) record.time = time;
  record.properties = properties;
  record.links = (form.links || []).map((link) => cleanLink(link)).filter(Boolean);
  return withNodeFields(record, { now, origin });
}

// ---------------------------------------------------------------------------
// Parsing a stored record back into form state. Records saved before the
// move to the wmdr2-bundled schema (plain-string codelist values,
// `observingCapabilities`/`deployments`, station-level `programAffiliations`)
// are converted to the new shape so they can be edited and re-saved.

function toDatetimeLocal(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  // Seconds are included so re-saving doesn't truncate them; a
  // datetime-local input shows seconds when its value has them.
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// An open bound stays ".." in the form, so its Unknown/Ongoing box is ticked.
const fromOpenDate = (value) => value || "";

function parseDates(dates) {
  const [start, end] = dates || [];
  return { dateStart: fromOpenDate(start), dateEnd: fromOpenDate(end) };
}

// Accepts a concept object, or a legacy plain string (a notation, or a
// concept URI whose last path segment is the notation).
export function parseConcept(value) {
  if (!value) return null;
  if (typeof value === "string") {
    return /^https?:\/\//.test(value) ? { id: value.split("/").filter(Boolean).pop(), url: value } : { id: value };
  }
  const concept = { id: value.id != null ? String(value.id) : "" };
  ["title", "description", "url"].forEach((key) => {
    if (value[key]) concept[key] = value[key];
  });
  return concept;
}

function parseTime(time) {
  const [intervalStart, intervalEnd] = (time && time.interval) || [];
  return {
    date: (time && time.date) || "",
    timestamp: time && time.timestamp ? toDatetimeLocal(time.timestamp) : "",
    intervalStart: fromOpenDate(intervalStart),
    intervalEnd: fromOpenDate(intervalEnd),
    resolution: (time && time.resolution) || "",
  };
}

function parsePhoneOrEmail(entry) {
  return { value: entry.value || "", roles: entry.roles || [] };
}

function parseAddress(address) {
  return {
    city: address.city || "",
    administrativeArea: address.administrativeArea || "",
    postalCode: address.postalCode || "",
    country: address.country || "",
    deliveryPoint: address.deliveryPoint || [],
    roles: address.roles || [],
  };
}

function parseLink(link) {
  return {
    href: link?.href || "",
    rel: link?.rel || "",
    type: link?.type || "",
    hreflang: link?.hreflang || "",
    title: link?.title || "",
    length: link?.length != null ? String(link.length) : "",
    profile: link?.profile || [],
    created: toDatetimeLocal(link?.created),
    updated: toDatetimeLocal(link?.updated),
  };
}

function parseContact(contact) {
  return {
    identifier: contact.identifier || "",
    organization: contact.organization || "",
    name: contact.name || "",
    position: contact.position || "",
    logo: parseLink(contact.logo),
    phones: (contact.phones || []).map(parsePhoneOrEmail),
    emails: (contact.emails || []).map(parsePhoneOrEmail),
    addresses: (contact.addresses || []).map(parseAddress),
    links: (contact.links || []).map(parseLink),
    hoursOfService: contact.hoursOfService || "",
    contactInstructions: contact.contactInstructions || "",
    roles: contact.roles || [],
  };
}

function parseGeometry(geometry) {
  const coordinates = geometry && geometry.coordinates;
  if (!coordinates) return { latitude: "", longitude: "", height: "" };
  return {
    latitude: String(coordinates[1]),
    longitude: String(coordinates[0]),
    height: coordinates[2] != null ? String(coordinates[2]) : "",
  };
}

function parseInstrument(instrument) {
  return {
    id: instrument?.id != null ? String(instrument.id) : "",
    manufacturer: instrument?.manufacturer || "",
    model: instrument?.model || "",
  };
}

function parseVerticalDistance(verticalDistance) {
  return {
    distances: (verticalDistance?.distances || []).map(String),
    unit: parseConcept(verticalDistance?.unit),
    referenceSurface: parseConcept(verticalDistance?.referenceSurface),
  };
}

function parseConfiguration(configuration) {
  return {
    id: configuration.id != null ? String(configuration.id) : "",
    time: parseTime(configuration.time),
    geometry: parseGeometry(configuration.geometry),
    observingMethod: parseConcept(configuration.observingMethod),
    operatingStatus: parseConcept(configuration.operatingStatus),
    sourceOfObservation: parseConcept(configuration.sourceOfObservation),
    instrument: parseInstrument(configuration.instrument),
    instrumentSerialNumber: configuration.instrumentSerialNumber || "",
    verticalDistance: parseVerticalDistance(configuration.verticalDistance),
  };
}

function parseProgramAffiliation(entry) {
  return {
    programAffiliation: parseConcept(entry.programAffiliation),
    reportingStatus: parseConcept(entry.reportingStatus),
    ...parseDates(entry.dates),
  };
}

function parseObservation(observation) {
  return {
    observedProperty: parseConcept(observation.observedProperty),
    observedGeometry: parseConcept(observation.observedGeometry),
    programAffiliations: (observation.programAffiliations || []).map(parseProgramAffiliation),
    configurations: (observation.configurations || []).map(parseConfiguration),
    ...(observation.contacts && { contacts: observation.contacts }),
  };
}

// Legacy: method/status/source lived on the capability and deployments held
// the instrument (with its serial number) and a list of reference surfaces.
function parseLegacyObservingCapability(capability, programAffiliations) {
  const deployments = capability.deployments?.length ? capability.deployments : [{}];
  return {
    observedProperty: parseConcept(capability.observedProperty),
    observedGeometry: null,
    programAffiliations,
    configurations: deployments.map((deployment) => {
      const [referenceSurface] = deployment.referenceSurfaces || [];
      return parseConfiguration({
        id: deployment.id,
        time: deployment.time || capability.time,
        geometry: deployment.geometry,
        observingMethod: capability.observingMethod,
        operatingStatus: capability.operatingStatus,
        sourceOfObservation: capability.sourceOfObservation,
        instrument: deployment.instrument,
        instrumentSerialNumber: deployment.instrument?.serialNumber,
        verticalDistance: referenceSurface && {
          distances: [referenceSurface.verticalDistance],
          referenceSurface: referenceSurface.referenceSurface,
        },
      });
    }),
  };
}

export function parseWmdrRecord(record) {
  const properties = record.properties || {};
  const coordinates = (record.geometry && record.geometry.coordinates) || ["", ""];
  const observations = properties.observations
    ? properties.observations.map(parseObservation)
    : (properties.observingCapabilities || []).map((capability) =>
        parseLegacyObservingCapability(capability, (properties.programAffiliations || []).map(parseProgramAffiliation))
      );
  return {
    id: record.id || "",
    latitude: coordinates[1] != null ? String(coordinates[1]) : "",
    longitude: coordinates[0] != null ? String(coordinates[0]) : "",
    height: coordinates[2] != null ? String(coordinates[2]) : "",
    time: parseTime(record.time),
    title: properties.title || "",
    description: properties.description || "",
    additionalTitles: properties.additionalTitles?.length ? properties.additionalTitles : [""],
    additionalIds: properties.additionalIds ?? [],
    facilityType: parseConcept(properties.facilityType),
    wmoRegion: parseConcept(properties.wmoRegion),
    contacts: (properties.contacts || []).map(parseContact),
    // Kept as stored: it isn't shown in the form, only written back.
    created: properties.created || "",
    territories: (properties.territories || []).map((t) => ({
      territory: parseConcept(t.territory),
      ...parseDates(t.dates),
    })),
    externalIds: (properties.externalIds || []).map((e) => ({ scheme: e.scheme || "", value: e.value || "" })),
    observations,
    // The self link isn't edited: buildWmdrRecord writes it.
    links: (record.links || []).filter((link) => link?.rel !== "self").map(parseLink),
  };
}
