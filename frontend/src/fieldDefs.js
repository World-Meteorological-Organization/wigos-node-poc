// Form field definitions shared between the station, observation and contact
// editors. Shapes follow wmo-im/wmdr2 schemas/wmdr2-bundled.json.

// An interval field (IntervalField) edits two keys of its item, `start` and
// `end`. Time intervals accept years, months, days, UTC timestamps and times of
// day; an open bound is ".." (and an empty one is written as ".." too).
export const TIME_FIELDS = [
  { name: "date", label: "Date", type: "date" },
  { name: "timestamp", label: "Timestamp", type: "datetime-local" },
  { name: "interval", label: "Interval", type: "interval", start: "intervalStart", end: "intervalEnd" },
  { name: "resolution", label: "Resolution", type: "duration" },
];

// The station's own time is only its interval; others are dropped on save.
export const STATION_TIME_FIELDS = TIME_FIELDS.filter((field) => field.name === "interval");

// Programme affiliation and territory `dates`: full days only, per the schema.
export const DATES_FIELD = { name: "dates", label: "Dates", type: "interval", start: "dateStart", end: "dateEnd", daysOnly: true };

export const GEOMETRY_FIELDS = [
  { name: "latitude", label: "Latitude", type: "text" },
  { name: "longitude", label: "Longitude", type: "text" },
  { name: "height", label: "Height (m)", type: "text" },
];

// Record-level links: rel and href are required. `length` (the target's size
// in bytes) isn't offered on any link; a stored value is still written back.
export const LINK_FIELDS = [
  { name: "href", label: "URL", type: "text", required: true, placeholder: "https://..." },
  { name: "rel", label: "Relation", type: "text", required: true, default: "about", placeholder: "e.g. about, alternate" },
  { name: "type", label: "Media type", type: "text", placeholder: "e.g. text/html" },
  { name: "hreflang", label: "Language", type: "text", placeholder: "e.g. en" },
  { name: "title", label: "Title", type: "text" },
];

// Contact links (the OGC Records link shape): href and type are required,
// and profile/created/updated are also allowed.
const CONTACT_LINK_BASE_FIELDS = [
  { name: "type", label: "Media type", type: "text", placeholder: "e.g. text/html" },
  { name: "hreflang", label: "Language", type: "text", placeholder: "e.g. en" },
  { name: "title", label: "Title", type: "text" },
  { name: "profile", label: "Profiles", type: "array-string" },
  { name: "created", label: "Created", type: "datetime-local" },
  { name: "updated", label: "Updated", type: "datetime-local" },
];

export const CONTACT_LINK_FIELDS = [
  { name: "href", label: "URL", type: "text", required: true, placeholder: "https://..." },
  { name: "rel", label: "Relation", type: "text", default: "about", placeholder: "e.g. about" },
  ...CONTACT_LINK_BASE_FIELDS.map((field) => (field.name === "type" ? { ...field, required: true } : field)),
];

// The logo is optional, so nothing is marked required here (it would block
// the contact's "Done" button); the schema check reports a half-filled logo.
// `rel` is always "icon" and is added when the record is built.
export const LOGO_FIELDS = [
  { name: "href", label: "Image URL", type: "text", placeholder: "https://.../logo.png" },
  ...CONTACT_LINK_BASE_FIELDS.map((field) => (field.name === "type" ? { ...field, placeholder: "e.g. image/png" } : field)),
];
