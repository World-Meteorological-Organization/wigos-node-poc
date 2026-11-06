"""Fixed JSON output for the WMDR2 record endpoint.

The endpoint answers the same bytes whatever the client asks for, so a link
to it (e.g. from a WNM, whose integrity is computed over what is served)
keeps matching."""

from rest_framework.renderers import JSONRenderer


class CompactJSONRenderer(JSONRenderer):
    """DRF's compact JSON, ignoring the Accept header's indent parameter."""

    def get_indent(self, accepted_media_type, renderer_context):
        return None
