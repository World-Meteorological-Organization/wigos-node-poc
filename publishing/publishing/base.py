"""Plugin interfaces.

A MessageGenerator turns an Event into Messages and a TransportLayer delivers
them. A Publisher is one publishing process from start to end: an ordered list
of Steps, each pairing a generator with a transport. Each step gets the
Deliveries (receipts) of the steps before it in the same publisher. Publishers
know nothing about each other, and one failing doesn't affect the others.

Byte-level consistency: a storage transport returns the Location of what it
stored, and later steps get the message it stored, body included. A WNM's
integrity is computed over those bytes, so it describes the stored file.

Each worker process has its own instance of each plugin and runs one job at a
time, so plugins don't have to be thread-safe."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Operation(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass(frozen=True)
class Event:
    """A station's current record, to publish. Plugins only see this snapshot and
    never read or write stations themselves."""

    operation: Operation
    station_id: int
    wigos_identifier: str
    wmdrv2: dict
    occurred_at: datetime  # the version of the record, the same on every retry


@dataclass(frozen=True)
class Message:
    body: bytes | None  # None in a receipt read back from the database: it isn't kept
    media_type: str
    name: str | None = None  # file name for storage transports
    topic: str | None = None  # overrides the transport's default topic
    headers: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Location:
    """Where a storage transport put a message."""

    url: str  # public link, e.g. a WNM href


@dataclass(frozen=True)
class Delivery:
    """Receipt of one sent message, handed to the later steps of its publisher.
    message.body is what was sent; a receipt read back from the database has
    none."""

    publisher: str  # name of the publisher that sent it
    message: Message
    location: Location | None = None  # storage transports only
    step: str | None = None  # name of the step that sent it


class PublishError(Exception):
    """A message could not be delivered. The job marks the station failed;
    retrying it is up to a user."""


class MessageGenerator(ABC):
    def __init__(self, **options):
        self.options = options

    @abstractmethod
    def generate(self, event: Event, deliveries: list[Delivery]) -> list[Message]:
        """Messages for this event; [] if this generator ignores it (e.g. a
        record file generator on DELETE). `deliveries` are the receipts of
        the steps that ran before this one in the same publisher."""


class TransportLayer(ABC):
    def __init__(self, **options):
        self.options = options

    def open(self):
        """Connect. Called once per worker process before the first send."""

    def close(self):
        """Disconnect. Called once when the worker process stops."""

    @abstractmethod
    def send(self, message: Message) -> Location | None:
        """Deliver one message and return where it is stored, if anywhere
        (storage transports); raise PublishError on failure.

        All or nothing: either the message is delivered completely, or
        nothing is left behind (e.g. write a temp file, then rename). A
        transport that can't promise this removes its partial output before
        raising."""

    def remove(self, location: Location) -> None:
        """Remove what send() stored at `location`, when a failed attempt is
        undone. Default: nothing to remove (e.g. notification transports)."""

    def send_many(self, messages: list[Message]) -> list[Location | None]:
        """Deliver messages in order. Override to send in bulk."""
        return [self.send(message) for message in messages]


@dataclass(frozen=True)
class Step:
    """One stage of a publisher: what to generate, and how to deliver it."""

    name: str  # unique within its publisher
    generator: MessageGenerator
    transport: TransportLayer


class Publisher(ABC):
    """One publishing process from start to end, and the coordinating instance
    of its steps: it runs them in order and feeds each generator what it needs.
    Subclasses decide which events they publish, and may override publish() for
    special flows."""

    def __init__(self, name: str, steps: list[Step]):
        self.name = name
        self.steps = list(steps)

    @abstractmethod
    def should_publish(self, event: Event) -> bool:
        """Whether this publisher handles the event at all."""

    def open(self):
        for step in self.steps:
            step.transport.open()

    def close(self):
        for step in reversed(self.steps):
            step.transport.close()

    def run_step(self, step: Step, event: Event, deliveries: list[Delivery]) -> list[Delivery]:
        """Run one generator and its transport; returns the step's receipts."""
        messages = step.generator.generate(event, deliveries)
        if any(message.body is None for message in messages):
            raise PublishError(f"Step {step.name} made a message without a body, e.g. from a read-back receipt")
        locations = step.transport.send_many(messages)
        return [Delivery(self.name, m, location, step=step.name) for m, location in zip(messages, locations)]

    def publish(self, event: Event, *, previous=(), on_step=None) -> list[Delivery]:
        """Run the steps in order, stopping at the first error, and return this
        publisher's receipts for the event.

        `previous` are its receipts from the station's last publication;
        on_step(step, receipts) is called after each step, so that a failure can
        undo what was stored so far."""
        if not self.should_publish(event):
            return []
        deliveries = []
        # a deletion stores nothing: it refers to what the last publication stored
        earlier = list(previous) if event.operation == Operation.DELETE else []
        for step in self.steps:
            deliveries += self.run_step(step, event, earlier + deliveries)
            if on_step:
                on_step(step, deliveries)
        return deliveries

    def undo(self, event: Event, deliveries: list[Delivery]) -> None:
        """Remove what this publisher stored in a failed attempt, newest first.
        Errors are left to the caller to record."""
        transports = {step.name: step.transport for step in self.steps}
        for delivery in reversed(deliveries):
            if delivery.publisher == self.name and delivery.location:
                transports[delivery.step].remove(delivery.location)


class DefaultPublisher(Publisher):
    """Publishes every event."""

    def should_publish(self, event: Event) -> bool:
        return True
