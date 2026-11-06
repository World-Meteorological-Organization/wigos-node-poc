import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
// Copy of backend/api/schemas/wmdr2-bundled.json (wmo-im/wmdr2 schemas/wmdr2-bundled.json).
// The frontend container only mounts ./frontend, so it can't import the backend copy.
import schema from "./schemas/wmdr2-bundled.json";

// strict: false because the bundled schema uses the non-standard "example" keyword.
const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
const validate = ajv.compile(schema);

// "/properties/contacts/0/phones/0/value" -> "contacts[1].phones[1].value".
// Indices are 1-based to match the "Contact 1" style labels in the form, and
// the leading "properties" segment is dropped since that's where most fields live.
const COORDINATE_NAMES = ["longitude", "latitude", "height"];

function formatPath(instancePath, missingProperty) {
  const segments = instancePath.split("/").filter(Boolean);
  if (missingProperty) segments.push(missingProperty);
  if (segments[0] === "properties" && segments.length > 1) segments.shift();
  const last = segments.length - 1;
  if (segments[last - 1] === "coordinates" && COORDINATE_NAMES[segments[last]]) {
    segments.splice(last - 1, 2, COORDINATE_NAMES[segments[last]]);
  }
  return segments.reduce(
    (path, segment) => (/^\d+$/.test(segment) ? `${path}[${Number(segment) + 1}]` : path ? `${path}.${segment}` : segment),
    ""
  ) || "record";
}

function isNoise(error) {
  // Combinators only report "must match a schema"; the useful error is the
  // branch-specific one alongside it.
  if (["oneOf", "anyOf", "allOf"].includes(error.keyword)) return true;
  // Concepts and times are `oneOf: [object, null]`, so every invalid object
  // also fails the null branch - that failure isn't worth showing.
  if (error.keyword === "enum" && error.params.allowedValues?.length === 1 && error.params.allowedValues[0] === null) {
    return true;
  }
  return false;
}

function formatMessage(error) {
  if (error.keyword === "required") return "is required";
  if (error.keyword === "pattern") return "has an invalid format";
  if (error.keyword === "minItems") return `needs at least ${error.params.limit} item(s)`;
  if (error.keyword === "contains") return "is missing a required value";
  return error.message;
}

// Returns a list of human-readable errors, empty when the record is valid.
export function validateWmdrRecord(record) {
  if (validate(record)) return [];
  const messages = validate.errors
    .filter((error) => !isNoise(error))
    .map((error) => `${formatPath(error.instancePath, error.params.missingProperty)} ${formatMessage(error)}`);
  return [...new Set(messages)];
}
