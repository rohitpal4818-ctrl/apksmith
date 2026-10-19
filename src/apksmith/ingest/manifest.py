"""
Manifest parsing: AndroidManifest.xml -> typed Python objects.

The binary XML format is already decoded by androguard into an lxml tree, so
this module is pure tree walking. It is deliberately defensive: APKs in the
wild have missing attributes, unusual namespaces, and obfuscated names, and a
parser that raises on one malformed element is useless in practice.
"""

from __future__ import annotations

from typing import Any

from ..models import AppIdentity, Component, Endpoint

ANDROID_NS = "http://schemas.android.com/apk/res/android"


def _attr(el: Any, name: str, default: str | None = None) -> str | None:
    """Read a namespaced Android attribute, tolerating absence."""
    try:
        value = el.get(f"{{{ANDROID_NS}}}{name}")
    except Exception:
        value = None
    return value if value is not None else default


def _bool_attr(el: Any, name: str) -> bool | None:
    raw = _attr(el, name)
    if raw is None:
        return None
    return raw.strip().lower() == "true"


def _int_attr(el: Any, name: str) -> int | None:
    raw = _attr(el, name)
    if raw is None:
        return None
    try:
        return int(raw, 0)
    except (TypeError, ValueError):
        return None


def parse_identity(loaded: Any) -> AppIdentity:
    """Extract app identity from the manifest root."""
    apk = loaded.apk
    xml = loaded.manifest_xml

    app_el = None
    try:
        app_el = xml.find("application")
    except Exception:
        app_el = None

    label = _attr(app_el, "label") if app_el is not None else None
    app_name = apk.get_app_name()

    return AppIdentity(
        package=apk.get_package() or "unknown",
        app_name=app_name,
        version_name=apk.get_androidversion_name(),
        version_code=apk.get_androidversion_code(),
        min_sdk=apk.get_min_sdk_version(),
        target_sdk=apk.get_target_sdk_version(),
        main_activity=apk.get_main_activity(),
        application_label=label,
    )


def _iter_component_elements(loaded: Any, tag: str) -> list[Any]:
    """Find every <tag> anywhere in the manifest tree.

    Components are nested inside <application>, not directly under <manifest>,
    so a direct-children ``findall`` finds nothing. Iterating the whole tree is
    both correct and tolerant of unusual nesting produced by some packers.
    """
    xml = loaded.manifest_xml
    try:
        return list(xml.iter(tag))
    except Exception:
        return []


def _extract_deeplinks(loaded: Any, element: Any) -> list[str]:
    """Pull `scheme`/`host` pairs out of an intent-filter's data tags."""
    schemes: list[str] = []
    try:
        for data in element.iterfind("intent-filter/data"):
            scheme = _attr(data, "scheme")
            host = _attr(data, "host")
            if scheme and host:
                schemes.append(f"{scheme}://{host}")
            elif scheme:
                schemes.append(f"{scheme}://")
    except Exception:
        pass
    return schemes


def parse_components(loaded: Any) -> list[Component]:
    """Collect every activity, service, receiver and provider.

    We walk the XML directly rather than using androguard's convenience
    getters, because we also need `exported`, `permission` and the intent
    filters -- none of which the simple getters expose.
    """
    components: list[Component] = []

    for kind, tag in (
        ("activity", "activity"),
        ("activity", "activity-alias"),
        ("service", "service"),
        ("receiver", "receiver"),
        ("provider", "provider"),
    ):
        for el in _iter_component_elements(loaded, tag):
            name = _attr(el, "name")
            if not name:
                continue

            # Fully-qualify the class name. Manifests use relative names for
            # classes in the app's own package.
            package = loaded.apk.get_package() or ""
            if name.startswith("."):
                name = package + name
            elif "." not in name:
                name = f"{package}.{name}"

            filters: list[str] = []
            links: list[str] = []
            try:
                for intent in el.iterfind("intent-filter"):
                    for action in intent.iterfind("action"):
                        aname = _attr(action, "name")
                        if aname:
                            filters.append(aname.rsplit(".", 1)[-1])
                    # Categories matter too: LAUNCHER is what marks the app's
                    # entry point on the home screen.
                    for cat in intent.iterfind("category"):
                        cname = _attr(cat, "name")
                        if cname:
                            filters.append(cname.rsplit(".", 1)[-1])
                    links.extend(_extract_deeplinks(loaded, intent))
            except Exception:
                pass

            components.append(
                Component(
                    kind=kind,
                    name=name,
                    exported=_bool_attr(el, "exported"),
                    permission=_attr(el, "permission"),
                    intent_filters=sorted(set(filters)),
                    deeplinks=sorted(set(links)),
                )
            )

    return components


def parse_manifest_deeplinks(loaded: Any) -> list[Endpoint]:
    """Deep links declared in the manifest, as Endpoint records."""
    out: list[Endpoint] = []
    seen: set[str] = set()

    for el in loaded.manifest_xml.iter("data"):
        scheme = _attr(el, "scheme")
        host = _attr(el, "host")
        path = _attr(el, "path") or _attr(el, "pathPrefix")
        if not scheme:
            continue

        url = f"{scheme}://{host or ''}{path or ''}"
        if url in seen:
            continue
        seen.add(url)

        out.append(
            Endpoint(
                value=url,
                scheme=scheme,
                host=host,
                path=path,
                source="manifest",
                confidence="high",  # type: ignore[arg-type]
            )
        )

    return out