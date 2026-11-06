"""Builds publishers from config dicts, e.g. the backend's settings.PUBLISHERS:

    {
        "NAME": "wis2",                                   # unique
        "CLASS": "publishing.base.DefaultPublisher",      # optional, this default
        "STEPS": [                                        # run in this order
            {
                "NAME": "storage",                        # unique in the publisher
                "GENERATOR": {"CLASS": "...", "OPTIONS": {...}},  # OPTIONS optional
                "TRANSPORT": {"CLASS": "...", "OPTIONS": {...}},
                "ENABLED": True,                          # optional
            },
        ],
        "ENABLED": True,                                  # optional
    }

Classes are dotted paths, so a plugin can live in any importable package.
Disabled publishers and steps are skipped without importing their classes (their
dependencies may not be installed)."""

from importlib import import_module

from .base import MessageGenerator, Publisher, Step, TransportLayer

DEFAULT_PUBLISHER = "publishing.base.DefaultPublisher"


class ConfigurationError(Exception):
    """The publisher configs are invalid. `errors` lists every problem."""

    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def import_class(path):
    module_path, _, class_name = path.rpartition(".")
    if not module_path:
        raise ImportError(f"'{path}' is not a dotted path")
    module = import_module(module_path)
    try:
        return getattr(module, class_name)
    except AttributeError:
        raise ImportError(f"module '{module_path}' has no attribute '{class_name}'") from None


def _load_class(label, path, base, errors):
    """The class at `path` if it subclasses `base`, else None after recording
    what is wrong."""
    if not isinstance(path, str):
        errors.append(f"{label}: CLASS is required")
        return None
    try:
        cls = import_class(path)
    except ImportError as e:
        errors.append(f"{label}: cannot import {path}: {e}")
        return None
    if not (isinstance(cls, type) and issubclass(cls, base)):
        errors.append(f"{label}: {path} is not a {base.__name__}")
        return None
    return cls


def _create(label, cls, errors, *args, **kwargs):
    try:
        return cls(*args, **kwargs)
    except Exception as e:  # e.g. an abstract class or a missing option
        errors.append(f"{label}: {cls.__name__} could not be created: {e}")
        return None


def _plugin(label, config, base, errors):
    """The generator or transport described by `config` ({CLASS, OPTIONS})."""
    config = config if isinstance(config, dict) else {}
    cls = _load_class(label, config.get("CLASS"), base, errors)
    options = config.get("OPTIONS", {})
    if not isinstance(options, dict):
        errors.append(f"{label}: OPTIONS must be a dict")
        return None
    return cls and _create(label, cls, errors, **options)


def _steps(label, configs, errors):
    """The enabled steps described by `configs`, in order."""
    if not isinstance(configs, list) or not configs:
        errors.append(f"{label}: STEPS must be a non-empty list")
        return []
    steps = []
    names = set()
    for index, config in enumerate(configs):
        name = config.get("NAME") if isinstance(config, dict) else None
        if not isinstance(name, str) or not name:
            errors.append(f"{label} step {index}: NAME is required")
            continue
        if name in names:
            errors.append(f"{label} step '{name}': NAME is used more than once")
            continue
        names.add(name)
        if not config.get("ENABLED", True):
            continue
        step_label = f"{label} step '{name}'"
        generator = _plugin(f"{step_label} GENERATOR", config.get("GENERATOR"), MessageGenerator, errors)
        transport = _plugin(f"{step_label} TRANSPORT", config.get("TRANSPORT"), TransportLayer, errors)
        if generator and transport:
            steps.append(Step(name, generator, transport))
    return steps


def build_publishers(configs):
    """Publishers for the enabled entries of `configs`, in order. Raises
    ConfigurationError listing every problem found."""
    errors = []
    publishers = []
    names = set()
    for index, config in enumerate(configs):
        name = config.get("NAME") if isinstance(config, dict) else None
        if not isinstance(name, str) or not name:
            errors.append(f"Publisher {index}: NAME is required")
            continue
        if name in names:
            errors.append(f"Publisher '{name}': NAME is used more than once")
            continue
        names.add(name)
        if not config.get("ENABLED", True):
            continue

        label = f"Publisher '{name}'"
        publisher_cls = _load_class(label, config.get("CLASS", DEFAULT_PUBLISHER), Publisher, errors)
        steps = _steps(label, config.get("STEPS"), errors)
        if publisher_cls and steps:
            publisher = _create(label, publisher_cls, errors, name, steps)
            if publisher:
                publishers.append(publisher)

    if errors:
        raise ConfigurationError(errors)
    return publishers
