import csv
import io
import re
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

# Codelist URLs referenced via $comment in wmdrRecordGeoJSON.yaml.
# The registry returns SKOS concepts as CSV by default (no Accept header
# needed).
#
# codes.wmo.int's bulk CSV export is unreliable for the ObservedVariable*
# collections: it's flaky (some requests return 200 OK with an empty body,
# others return data) and even when it does return data, it quotes numeric
# skos:notation values (e.g. '104' instead of 104). ObservingMethod* and unit
# have the same quoting, so they're fetched as turtle too. Two fallbacks are tried in order when the bulk
# CSV comes back empty:
#   1. member_codes: the CSV is assembled by fetching each known member
#      concept individually. Only practical for small collections.
#   2. turtle: the collection is re-fetched as text/turtle (which is not
#      flaky) and parsed into the same CSV shape. Used for large
#      collections (hundreds of concepts) where per-member fetches would
#      mean hundreds of requests.
# force_turtle skips the bulk attempt entirely so the cached file's shape
# doesn't depend on whether the flaky bulk endpoint happens to respond.
CODELISTS = {
    "FacilityType": {
        "url": "https://codes.wmo.int/wmdr/FacilityType",
        "member_codes": None,
    },
    "WMORegion": {
        "url": "https://codes.wmo.int/wmdr/WMORegion",
        "member_codes": [
            "africa",
            "antarctica",
            "asia",
            "europe",
            "northCentralAmericaCaribbean",
            "southAmerica",
            "southWestPacific",
            "inapplicable",
            "unknown",
        ],
    },
    "ObservedVariableAtmosphere": {
        "url": "https://codes.wmo.int/wmdr/_ObservedVariableAtmosphere",
        "member_codes": None,
        "force_turtle": True,
    },
    "ObservedVariableOcean": {
        "url": "https://codes.wmo.int/wmdr/_ObservedVariableOcean",
        "member_codes": None,
        "force_turtle": True,
    },
    "ObservedVariableTerrestrial": {
        "url": "https://codes.wmo.int/wmdr/_ObservedVariableTerrestrial",
        "member_codes": None,
        "force_turtle": True,
    },
    "ObservedVariableOuterSpace": {
        "url": "https://codes.wmo.int/wmdr/_ObservedVariableOuterSpace",
        "member_codes": None,
        "force_turtle": True,
    },
    "ObservedVariableEarth": {
        "url": "https://codes.wmo.int/wmdr/_ObservedVariableEarth",
        "member_codes": None,
        "force_turtle": True,
    },
    # Most of these 404 at the URL given in the schema's $comment; the
    # registry serves them under the "_"-prefixed collection instead.
    "TerritoryName": {
        "url": "https://codes.wmo.int/wmdr/_TerritoryName",
        "member_codes": None,
    },
    "Geometry": {
        "url": "https://codes.wmo.int/wmdr/_Geometry",
        "member_codes": None,
    },
    "ProgramAffiliation": {
        "url": "https://codes.wmo.int/wmdr/_ProgramAffiliation",
        "member_codes": None,
    },
    "ReportingStatus": {
        "url": "https://codes.wmo.int/wmdr/_ReportingStatus",
        "member_codes": None,
    },
    "ObservingMethodAtmosphere": {
        "url": "https://codes.wmo.int/wmdr/_ObservingMethodAtmosphere",
        "member_codes": None,
        "force_turtle": True,
    },
    "ObservingMethodTerrestrial": {
        "url": "https://codes.wmo.int/wmdr/_ObservingMethodTerrestrial",
        "member_codes": None,
        "force_turtle": True,
    },
    "ObservingMethodOcean": {
        "url": "https://codes.wmo.int/wmdr/_ObservingMethodOcean",
        "member_codes": None,
        "force_turtle": True,
    },
    "InstrumentOperatingStatus": {
        "url": "https://codes.wmo.int/wmdr/_InstrumentOperatingStatus",
        "member_codes": None,
    },
    "SourceOfObservation": {
        "url": "https://codes.wmo.int/wmdr/_SourceOfObservation",
        "member_codes": None,
    },
    "ReferenceSurfaceType": {
        "url": "https://codes.wmo.int/wmdr/_ReferenceSurfaceType",
        "member_codes": None,
    },
    "unit": {
        "url": "https://codes.wmo.int/wmdr/_unit",
        "member_codes": None,
        "force_turtle": True,
    },
    # ISO3166 is intentionally not listed here: it has no codes.wmo.int
    # registry to refresh from. api/codelists/ISO3166.csv is a static seed
    # (ISO 3166-1 numeric codes, plus the WIGOS-specific "Legacy" issuer
    # code 20000) maintained by hand and served as-is by the codelist view.
}

TURTLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "'": "'"}


class Command(BaseCommand):
    help = (
        "Best-effort update of the locally cached WMDR codelist CSVs from "
        "codes.wmo.int. Committed seed files under api/codelists/ are kept "
        "in place whenever the live update fails, so a network or upstream "
        "issue never breaks the app."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "schemes",
            nargs="*",
            choices=sorted(CODELISTS),
            metavar="scheme",
            help="Only update these codelists (default: all).",
        )

    def handle(self, *args, **options):
        codelists_dir = Path(settings.BASE_DIR) / "api" / "codelists"
        codelists_dir.mkdir(parents=True, exist_ok=True)

        for scheme in options["schemes"] or CODELISTS:
            config = CODELISTS[scheme]
            dest = codelists_dir / f"{scheme}.csv"
            self.stdout.write(f"Updating {scheme} from {config['url']}...")

            url, member_codes = config["url"], config["member_codes"]
            text = None if config.get("force_turtle") else self._fetch_bulk(url)
            if not text and member_codes:
                text = self._fetch_by_member(url, member_codes)
            if not text:
                text = self._fetch_bulk_turtle(url, scheme)

            if not text:
                msg = f"  update failed, keeping existing {dest.name}"
                self.stderr.write(self.style.WARNING(msg))
                continue

            dest.write_text(text, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"  wrote {dest}"))

    def _fetch_bulk(self, url):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            msg = f"  bulk fetch failed: {exc}"
            self.stderr.write(self.style.WARNING(msg))
            return None
        # The registry doesn't declare a charset on text/csv responses, so
        # requests falls back to Latin-1 and mangles non-ASCII text (e.g.
        # "Ångström" -> "ÃngstrÃ¶m"). The body is actually UTF-8.
        response.encoding = "utf-8"
        if not response.text.strip():
            msg = "  bulk fetch returned empty body; trying fallback"
            self.stderr.write(self.style.WARNING(msg))
            return None
        return response.text

    def _fetch_by_member(self, base_url, codes):
        header = None
        rows = []
        for code in codes:
            try:
                response = requests.get(f"{base_url}/{code}", timeout=15)
                response.raise_for_status()
                response.encoding = "utf-8"
                lines = response.text.strip().splitlines()
                if len(lines) < 2:
                    raise ValueError("no data row returned")
            except (requests.RequestException, ValueError) as exc:
                msg = f"  concept {code!r} failed: {exc}"
                self.stderr.write(self.style.WARNING(msg))
                continue
            header = header or lines[0]
            rows.append(lines[1])

        if not header or not rows:
            return None
        return "\n".join([header] + rows) + "\n"

    def _fetch_bulk_turtle(self, base_url, scheme):
        try:
            response = requests.get(
                base_url, headers={"Accept": "text/turtle"}, timeout=30
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            msg = f"  turtle fetch failed: {exc}"
            self.stderr.write(self.style.WARNING(msg))
            return None
        if not response.text.strip():
            msg = "  turtle fetch returned empty body"
            self.stderr.write(self.style.WARNING(msg))
            return None

        rows = self._parse_turtle_concepts(response.text, scheme)
        if not rows:
            msg = "  turtle fetch returned no parseable concepts"
            self.stderr.write(self.style.WARNING(msg))
            return None

        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["@id", "dct:description", "rdf:type", "rdfs:label", "skos:notation"])
        writer.writerows(rows)
        return output.getvalue()

    @staticmethod
    def _parse_turtle_concepts(text, scheme):
        # Concept blocks look like:
        #   <http://codes.wmo.int/wmdr/<scheme>/<code>>
        #           a                skos:Concept ;
        #           rdfs:label       "..." ;
        #           dct:description  "..."@en ;
        #           skos:notation    "..." .
        prefix = f"<http://codes.wmo.int/wmdr/{scheme}/"
        rows = []
        for block in re.split(r"\n\n+", text):
            block = block.strip()
            if not block.startswith(prefix):
                continue
            uri_match = re.match(r"<([^>]+)>", block)
            label_match = re.search(r'rdfs:label\s+"((?:[^"\\]|\\.)*)"', block)
            desc_match = re.search(r'dct:description\s+"((?:[^"\\]|\\.)*)"@en', block)
            notation_match = re.search(r'skos:notation\s+"((?:[^"\\]|\\.)*)"', block)
            if not (uri_match and label_match and notation_match):
                continue
            label = Command._unescape_turtle(label_match.group(1))
            desc = Command._unescape_turtle(desc_match.group(1)) if desc_match else ""
            notation = Command._unescape_turtle(notation_match.group(1))
            rows.append((f"<{uri_match.group(1)}>", f"'{desc}'@en", "skos:Concept", label, notation))
        rows.sort(key=lambda r: r[0])
        return rows

    @staticmethod
    def _unescape_turtle(s):
        out = []
        i = 0
        while i < len(s):
            c = s[i]
            if c == "\\" and i + 1 < len(s) and s[i + 1] in TURTLE_ESCAPES:
                out.append(TURTLE_ESCAPES[s[i + 1]])
                i += 2
                continue
            out.append(c)
            i += 1
        return "".join(out)
