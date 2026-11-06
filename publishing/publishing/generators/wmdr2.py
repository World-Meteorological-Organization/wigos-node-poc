from ..base import Message, MessageGenerator, Operation
from ..wmdr2 import MEDIA_TYPE, record_file_name, render_record


class RecordFileGenerator(MessageGenerator):
    """The record itself, as the file web storage serves. Every version is its
    own file, so a deletion writes nothing.

    Options: centre_id (this node's WIS2 centre id, part of the file name)."""

    def __init__(self, *, centre_id, **options):
        super().__init__(centre_id=centre_id, **options)
        self.centre_id = centre_id

    def generate(self, event, deliveries):
        if event.operation == Operation.DELETE:
            return []
        return [
            Message(
                body=render_record(event.wmdrv2),
                media_type=MEDIA_TYPE,
                name=record_file_name(event.wmdrv2, self.centre_id),
            )
        ]
