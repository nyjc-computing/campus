"""yapper_python/base.py

Base classes and interfaces for yapper-python.
"""
from abc import ABC, abstractmethod
from typing import Callable, Protocol

# Type Aliases
ClientId = str  # A unique identifier for the client.
EventLabel = str  # A namedspaced label for the event.
EventData = dict  # Metadata associated with the event.


class Event(ABC):
    """Base class for events.

    This class is used to define the structure of an event.
    Extend from this base class to create specific event types if required.

    Users are encouraged not to initialize this class directly.
    Instead, create a subclass or use the Yapper.emit() method.
    """
    label: str
    data: dict

    def __init__(self, label: EventLabel, data: EventData):
        self.label = label
        self.data = data

    def __repr__(self):
        return f"Event(label={self.label!r}, data={self.data!r})"


class EventHandler(Protocol):
    """Protocol for event handlers.

    This protocol defines the structure of an event handler.
    Handlers should accept an Event object as a parameter.
    """

    def __call__(self, event: Event) -> None:
        """Handle the event without returning a value."""
        pass


class YapperInterface(ABC):
    """Interface for Yapper class.

    This interface defines the methods that the Yapper class must implement.
    """
    client_id: ClientId

    def __init__(self, client_id: ClientId, *args, **kwargs):
        self.client_id = client_id
        self._running = False
        self._handlers: dict[EventLabel, Callable[[Event], None]] = {}

    @property
    def running(self) -> bool:
        """Check if the Yapper instance is running."""
        return self._running

    def on_event(self, label: EventLabel) -> Callable[[EventHandler], EventHandler]:
        """Decorator to register an event handler for a specific event label."""
        def decorator(handler: EventHandler) -> EventHandler:
            self._handlers[label] = handler
            return handler
        self.subscribe(label)
        return decorator

    def handle_event(self, event: Event) -> None:
        """Handle an event by calling the registered handler."""
        # Subclasses should override this method to implement custom event handling.
        if event.label in self._handlers:
            callback = self._handlers[event.label]
            callback(event)

    @abstractmethod
    def emit(self, label: EventLabel, data: EventData | None = None) -> None:
        """Emit an event to the message broker."""
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    def subscribe(self, label: EventLabel) -> None:
        """Notify the backend of client's subscription to an event label."""
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    def unsubscribe(self, label: EventLabel) -> None:
        """Notify the backend of client's unsubscription from an event label."""
        # Subclasses should override this method to implement unsubscription logic.
        raise NotImplementedError("Subclasses must implement this method.")

    @abstractmethod
    def listen(self) -> list[Event]:
        """Listen for events from the message broker."""
        raise NotImplementedError("Subclasses must implement this method.")

    def run(self, *args, **kwargs) -> None:
        """Receive events from the message broker, calling any registered
        handlers.
        """
        self.start()
        while self.running:
            for event in self.listen():
                self.handle_event(event)

    def start(self) -> None:
        """Start the Yapper instance."""
        # Subclasses should override this method to implement startup logic.
        self._running = True

    def stop(self) -> None:
        """Stop the Yapper instance."""
        # Subclasses should override this method to implement shutdown logic.
        self._running = False
