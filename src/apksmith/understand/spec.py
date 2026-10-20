"""
The behaviour spec -- the artefact M2 exists to produce.

This is the bridge between "a pile of decompiled Java" and "a working
reimplementation". Everything downstream (M3 code generation) consumes only
this, so it is deliberately declarative and free of Android-implementation
detail: we describe *what the app does*, not *how Android does it*.

Design rules:

- Every field is either a string or a list of strings. Nested objects make
  free-form model output harder to validate for no benefit here.
- Fields a model might reasonably omit are optional with a default. A missing
  screen list should not fail the run.
- ``confidence`` is recorded per section. The model is told to mark anything
  it inferred rather than read, so later stages know what to double-check.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScreenSpec(BaseModel):
    """One user-visible screen."""

    name: str = Field(description="Short human name, e.g. 'App list'")
    purpose: str = Field(default="", description="What the user does here")
    shows: list[str] = Field(default_factory=list, description="Visible elements")
    actions: list[str] = Field(default_factory=list, description="Things the user can do")
    evidence: list[str] = Field(
        default_factory=list,
        description="Class names this was inferred from",
    )
    confidence: str = Field(default="medium", description="high | medium | low")


class DataSpec(BaseModel):
    """Something the app stores or persists."""

    name: str
    kind: str = Field(
        default="unknown", description="preferences | database | file | cache"
    )
    description: str = ""


class NetworkSpec(BaseModel):
    """An outbound request the app makes."""

    purpose: str = Field(default="", description="Why the app calls this")
    endpoint: str = Field(default="", description="URL or path template")
    method: str = Field(default="", description="GET | POST | unknown")
    evidence: list[str] = Field(default_factory=list)


class FeatureSpec(BaseModel):
    """A capability of the app, above the level of any single screen."""

    name: str
    description: str = ""
    implemented: bool = Field(
        default=True,
        description="False if it looks stubbed, disabled or dead code",
    )


class BehaviourSpec(BaseModel):
    """The complete description of what an app does."""

    app_name: str = ""
    package: str = ""
    purpose: str = Field(
        default="",
        description="One or two sentences: what this app is for and who it is for",
    )
    target_users: str = ""
    screens: list[ScreenSpec] = Field(default_factory=list)
    features: list[FeatureSpec] = Field(default_factory=list)
    data_stored: list[DataSpec] = Field(default_factory=list)
    network_calls: list[NetworkSpec] = Field(default_factory=list)
    permissions_justified: dict[str, str] = Field(
        default_factory=dict,
        description="permission -> why the app needs it, from observed behaviour",
    )
    platform_dependencies: list[str] = Field(
        default_factory=list,
        description="Things the app needs from the OS or hardware",
    )
    caveats: list[str] = Field(
        default_factory=list,
        description="What the analysis could not determine",
    )

    def to_markdown(self) -> str:
        """Render as Markdown, for a README or a review."""
        out: list[str] = []
        a = out.append

        a(f"# {self.app_name or self.package}")
        a("")
        if self.purpose:
            a(f"**Purpose.** {self.purpose}")
            a("")
        if self.target_users:
            a(f"**For.** {self.target_users}")
            a("")

        if self.screens:
            a("## Screens")
            a("")
            for s in self.screens:
                a(f"### {s.name}")
                if s.purpose:
                    a(s.purpose)
                    a("")
                if s.shows:
                    a("**Shows:** " + ", ".join(s.shows))
                if s.actions:
                    a("**Actions:** " + ", ".join(s.actions))
                a("")
                if s.evidence:
                    a(
                        f"<sub>inferred from: {', '.join(s.evidence[:4])} "
                        f"(confidence: {s.confidence})</sub>"
                    )
                    a("")

        if self.features:
            a("## Features")
            a("")
            for f in self.features:
                mark = "" if f.implemented else " *(appears stubbed)*"
                a(
                    f"- **{f.name}**{mark}"
                    + (f" — {f.description}" if f.description else "")
                )
            a("")

        if self.network_calls:
            a("## Network calls")
            a("")
            for n in self.network_calls:
                a(
                    f"- `{n.endpoint or 'unknown'}`"
                    + (f" — {n.purpose}" if n.purpose else "")
                )
            a("")

        if self.data_stored:
            a("## Data stored")
            a("")
            for d in self.data_stored:
                a(
                    f"- **{d.name}** ({d.kind})"
                    + (f" — {d.description}" if d.description else "")
                )
            a("")

        if self.permissions_justified:
            a("## Permissions, justified by observed behaviour")
            a("")
            for perm, why in self.permissions_justified.items():
                a(f"- `{perm}` — {why}")
            a("")

        if self.platform_dependencies:
            a("## Platform dependencies")
            a("")
            a(", ".join(self.platform_dependencies))
            a("")

        if self.caveats:
            a("## Caveats")
            a("")
            for c in self.caveats:
                a(f"- {c}")
            a("")

        return "\n".join(out)


#: Partial result from analysing one chunk of classes.
class PartialSpec(BaseModel):
    """What a single extraction pass over a batch of classes returns."""

    purpose_hint: str = Field(
        default="", description="What this batch suggests the app does"
    )
    screens: list[ScreenSpec] = Field(default_factory=list)
    features: list[FeatureSpec] = Field(default_factory=list)
    data_stored: list[DataSpec] = Field(default_factory=list)
    network_calls: list[NetworkSpec] = Field(default_factory=list)
    platform_dependencies: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
