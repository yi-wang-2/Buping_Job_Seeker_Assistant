"""Typography guardrails for resume HTML.

The harness keeps text readable without flattening the visual hierarchy of a
resume. It repairs only explicit sizes outside the range for their semantic
role; suitable template and user-selected values are preserved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag


_RULE_RE = re.compile(r"(?P<selector>[^{}]+)\{(?P<body>[^{}]*)\}", re.S)
_FONT_SIZE_RE = re.compile(
    r"(?P<prefix>font-size\s*:\s*)(?P<value>-?(?:\d+(?:\.\d*)?|\.\d+))"
    r"(?P<unit>px|pt|rem|em)(?P<suffix>\s*!important)?",
    re.I,
)
_FONT_VARIABLE_RE = re.compile(
    r"(?P<prefix>--[\w-]*(?:font|size)[\w-]*\s*:\s*)"
    r"(?P<value>-?(?:\d+(?:\.\d*)?|\.\d+))(?P<unit>px|pt|rem|em)",
    re.I,
)
_CSS_VARIABLE_RE = re.compile(
    r"(?P<name>--[\w-]+)\s*:\s*(?P<value>\d+(?:\.\d*)?|\.\d+)"
    r"(?P<unit>px|pt|rem|em)",
    re.I,
)
_BODY_SELECTOR_RE = re.compile(r"(?:^|[\s>,+~])body(?:$|[\s>,+~:\[])", re.I)


@dataclass(frozen=True)
class TypographyAdjustment:
    selector: str
    original: str
    adjusted: str
    source: str


@dataclass
class TypographyHarnessResult:
    html: str
    adjustments: list[TypographyAdjustment] = field(default_factory=list)
    content_width_px: float = 0.0
    target_cjk_chars_per_line: tuple[int, int] = (42, 52)

    @property
    def adjusted_count(self) -> int:
        return len(self.adjustments)


def _to_px(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit == "pt":
        return value * 96 / 72
    if unit in {"rem", "em"}:
        return value * 16
    return value


def _from_px(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit == "pt":
        return value * 72 / 96
    if unit in {"rem", "em"}:
        return value / 16
    return value


def _format_size(value: float, unit: str) -> str:
    rendered = f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{rendered}{unit}"


def _role_for_selector(selector: str) -> str:
    normalized = selector.lower()
    if re.search(r"(?:^|[\s>+~,.#])h1(?:$|[\s>+~,.#:\[])", normalized):
        return "name_heading"
    if re.search(r"(?:^|[\s>+~,.#])h2(?:$|[\s>+~,.#:\[])", normalized):
        return "section_heading"
    if re.search(r"(?:^|[\s>+~,.#])h[34](?:$|[\s>+~,.#:\[])", normalized) or "entry-header" in normalized:
        return "entry_heading"
    if any(token in normalized for token in (
        "contact", "entry-details", "metadata", "meta-info", "date", "period", "small",
    )):
        return "supporting"
    return "body"


def _role_for_element(element: Tag) -> str:
    heading = element if element.name in {"h1", "h2", "h3", "h4"} else element.find_parent(["h1", "h2", "h3", "h4"])
    if heading:
        return {
            "h1": "name_heading",
            "h2": "section_heading",
            "h3": "entry_heading",
            "h4": "entry_heading",
        }[heading.name]
    classes: list[str] = []
    for node in [element, *element.parents]:
        if isinstance(node, Tag):
            classes.extend(str(item).lower() for item in node.get("class", []))
    class_text = " ".join(classes)
    if any(token in class_text for token in (
        "contact", "entry-details", "metadata", "meta-info", "date", "period",
    )) or element.name == "small":
        return "supporting"
    return "body"


def _resolve_css_length(value: str, variables: dict[str, float]) -> float | None:
    value = value.strip()
    variable = re.fullmatch(r"var\((--[\w-]+)\)", value, re.I)
    if variable:
        return variables.get(variable.group(1).lower())
    numeric = re.fullmatch(r"(\d+(?:\.\d*)?|\.\d+)(px|pt|rem|em)", value, re.I)
    if not numeric:
        return None
    return _to_px(float(numeric.group(1)), numeric.group(2))


def _infer_content_width_px(soup: BeautifulSoup) -> float:
    """Estimate the PDF text measure, capped by A4 minus 0.5in margins."""
    css = "\n".join(style.get_text() for style in soup.find_all("style"))
    variables = {
        match.group("name").lower(): _to_px(float(match.group("value")), match.group("unit"))
        for match in _CSS_VARIABLE_RE.finditer(css)
    }
    widths: list[float] = []
    for rule in _RULE_RE.finditer(css):
        selector = rule.group("selector").strip()
        if not _BODY_SELECTOR_RE.search(selector):
            continue
        declarations = rule.group("body")
        for match in re.finditer(r"(?:max-)?width\s*:\s*([^;]+)", declarations, re.I):
            resolved = _resolve_css_length(match.group(1).replace("!important", ""), variables)
            if resolved:
                widths.append(resolved)

    # Chrome PDF uses A4 (794px) with 0.5in margins on both sides: ~698px.
    printable_width = 8.27 * 96 - 2 * 0.5 * 96
    declared_width = min(widths) if widths else printable_width
    return min(printable_width, max(520.0, declared_width))


def _bounds_for_role(role: str, content_width_px: float) -> tuple[float, float]:
    # A readable full-width body line is about 42–52 CJK ems. Latin glyphs
    # average roughly half an em, yielding about 75–95 Latin characters.
    body_min = max(12.0, content_width_px / 52)
    body_max = min(17.0, content_width_px / 42)
    return {
        "body": (body_min, body_max),
        "supporting": (max(32 / 3, body_min * 0.82), min(15.0, body_max * 0.92)),
        "entry_heading": (body_min, min(21.0, body_max * 1.25)),
        "section_heading": (max(14.0, body_min * 1.12), min(26.0, body_max * 1.6)),
        "name_heading": (max(24.0, body_min * 1.8), min(128 / 3, body_max * 2.7)),
    }[role]


def _repair_declarations(
    declarations: str,
    *,
    selector: str,
    role: str,
    source: str,
    content_width_px: float,
    adjustments: list[TypographyAdjustment],
) -> str:
    minimum, maximum = _bounds_for_role(role, content_width_px)

    def replace(match: re.Match[str]) -> str:
        original = f"{match.group('value')}{match.group('unit')}"
        px = _to_px(float(match.group("value")), match.group("unit"))
        adjusted_px = min(max(px, minimum), maximum)
        if abs(adjusted_px - px) < 0.25:
            return match.group(0)
        adjusted = _format_size(
            _from_px(adjusted_px, match.group("unit")),
            match.group("unit"),
        )
        adjustments.append(TypographyAdjustment(selector, original, adjusted, source))
        return f"{match.group('prefix')}{adjusted}{match.group('suffix') or ''}"

    return _FONT_SIZE_RE.sub(replace, declarations)


def enforce_resume_typography(html: str) -> TypographyHarnessResult:
    """Validate and repair unsuitable explicit font sizes in resume HTML."""

    if not html or not html.strip():
        return TypographyHarnessResult(html=html)

    soup = BeautifulSoup(html, "html.parser")
    adjustments: list[TypographyAdjustment] = []
    content_width_px = _infer_content_width_px(soup)

    for style_index, style in enumerate(soup.find_all("style")):
        css = style.string if style.string is not None else style.get_text()

        def repair_rule(match: re.Match[str]) -> str:
            selector = match.group("selector")
            declarations = match.group("body")
            repaired = _repair_declarations(
                declarations,
                selector=selector.strip(),
                role=_role_for_selector(selector),
                source=f"style[{style_index}]",
                content_width_px=content_width_px,
                adjustments=adjustments,
            )
            # Font-size custom properties are body defaults in the bundled
            # templates. Clamp them as well when a rule consumes var(...).
            if "font-size" in css and "var(" in css:
                repaired = _FONT_VARIABLE_RE.sub(
                    lambda variable: _repair_font_variable(
                        variable, selector.strip(), f"style[{style_index}]", content_width_px, adjustments
                    ),
                    repaired,
                )
            return f"{selector}{{{repaired}}}"

        style.string = _RULE_RE.sub(repair_rule, css)

    for element in soup.select("[style]"):
        inline_style = str(element.get("style", ""))
        if "font-size" not in inline_style.lower():
            continue
        descriptor = element.name
        if element.get("id"):
            descriptor += f"#{element['id']}"
        elif element.get("class"):
            descriptor += "." + ".".join(element.get("class", []))
        element["style"] = _repair_declarations(
            inline_style,
            selector=descriptor,
            role=_role_for_element(element),
            source="inline",
            content_width_px=content_width_px,
            adjustments=adjustments,
        )

    legacy_sizes = {1: 10.0, 2: 13.0, 3: 16.0, 4: 18.0, 5: 24.0, 6: 32.0, 7: 48.0}
    for font in soup.find_all("font", size=True):
        try:
            legacy_size = int(str(font.get("size", "")).strip())
        except ValueError:
            continue
        if legacy_size not in legacy_sizes:
            continue
        role = _role_for_element(font)
        minimum, maximum = _bounds_for_role(role, content_width_px)
        original_px = legacy_sizes[legacy_size]
        adjusted_px = min(max(original_px, minimum), maximum)
        if abs(adjusted_px - original_px) < 0.25:
            continue
        existing_style = str(font.get("style", "")).strip().rstrip(";")
        font["style"] = f"{existing_style + '; ' if existing_style else ''}font-size: {_format_size(adjusted_px, 'px')}"
        del font["size"]
        adjustments.append(TypographyAdjustment(
            selector="font[size]",
            original=f"legacy-size-{legacy_size}",
            adjusted=_format_size(adjusted_px, "px"),
            source="html-attribute",
        ))

    return TypographyHarnessResult(
        html=str(soup),
        adjustments=adjustments,
        content_width_px=content_width_px,
    )


def _repair_font_variable(
    match: re.Match[str],
    selector: str,
    source: str,
    content_width_px: float,
    adjustments: list[TypographyAdjustment],
) -> str:
    original = f"{match.group('value')}{match.group('unit')}"
    px = _to_px(float(match.group("value")), match.group("unit"))
    minimum, maximum = _bounds_for_role("body", content_width_px)
    adjusted_px = min(max(px, minimum), maximum)
    if abs(adjusted_px - px) < 0.25:
        return match.group(0)
    adjusted = _format_size(_from_px(adjusted_px, match.group("unit")), match.group("unit"))
    adjustments.append(TypographyAdjustment(selector, original, adjusted, source))
    return f"{match.group('prefix')}{adjusted}"
