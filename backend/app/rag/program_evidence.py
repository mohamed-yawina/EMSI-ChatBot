"""Extract program names and durations from explicitly structured PDF passages."""

import re
import unicodedata

_CYCLE_MARKER = re.compile(
    r"\b(?P<years>\d+)\s+ann(?:\u00e9e|ee)s?\s+cycle\s+d['\u2019]?\s*"
    r"ing(?:\u00e9|e)nieur\b",
    re.IGNORECASE,
)
_PREPARATORY_MARKER = re.compile(
    r"\b(?P<years>\d+)\s+ann(?:\u00e9e|ee)s?\s+"
    r"pr(?:\u00e9|e)paratoires?\s+pour\s+"
    r"(?P<targets>.+?)(?=\b\d+\s+ann(?:\u00e9e|ee)s?\s+|"
    r"\boption\s+\d+\b|$)",
    re.IGNORECASE,
)
_NEXT_SECTION = re.compile(
    r"\b\d+\s+ann(?:\u00e9e|ee)s?\s+(?:cycle\s+d['\u2019]?\s*"
    r"ing(?:\u00e9|e)nieur|pr(?:\u00e9|e)paratoires?)\b|"
    r"\boption\s+\d+\b",
    re.IGNORECASE,
)


def _normalized(value: str) -> str:
    from app.rag.ranking_policy import repair_common_mojibake

    text = unicodedata.normalize(
        "NFKD", repair_common_mojibake(str(value or "").lower())
    )
    return "".join(character for character in text if not unicodedata.combining(character))


def _groups(documents: list[dict]) -> list[dict]:
    grouped = {}
    for position, document in enumerate(documents):
        source = str(document.get("source", "")).strip()
        page = document.get("page")
        if not source or page in (None, "", "?"):
            continue
        key = (source, str(page))
        group = grouped.setdefault(key, {"source": source, "page": page, "documents": []})
        group["documents"].append((position, document))

    result = []
    for group in grouped.values():
        ordered = sorted(
            group["documents"],
            key=lambda item: (
                item[1].get("chunk_index") is None,
                item[1].get("chunk_index", item[0]),
                item[0],
            ),
        )
        unique_content = []
        seen_content = set()
        for _, document in ordered:
            content = str(document.get("content", "")).strip()
            if content and content not in seen_content:
                unique_content.append(content)
                seen_content.add(content)
        group["content"] = "\n".join(unique_content)
        group["documents"] = [document for _, document in ordered]
        result.append(group)
    return result


def _acronym_for_title(content: str, title: str) -> str | None:
    words = re.findall(r"\S+", title.strip())
    if not words:
        return None
    title_pattern = r"\s+".join(re.escape(word) for word in words)
    match = re.search(
        rf"(?<!\w){title_pattern}\s*\(([A-Z][A-Z0-9]{{1,7}})\)",
        content,
        re.IGNORECASE,
    )
    return match.group(1).upper() if match else None


def _initialism_alias(left: str, right: str) -> bool:
    """Match a short final initialism to the expanded words in another title."""
    for short, long in ((left, right), (right, left)):
        short_tokens = re.findall(r"[a-z0-9]+", _normalized(short))
        long_tokens = re.findall(r"[a-z0-9]+", _normalized(long))
        if len(short_tokens) < 3 or len(long_tokens) <= len(short_tokens):
            continue
        if short_tokens[:-1] != long_tokens[: len(short_tokens) - 1]:
            continue
        abbreviation = short_tokens[-1]
        expanded = long_tokens[len(short_tokens) - 1 :]
        if len(abbreviation) >= 2 and abbreviation == "".join(
            token[0] for token in expanded
        ):
            return True
    return False


def extract_structured_programs(documents: list[dict]) -> list[dict]:
    """Parse each named program following an explicit engineering-cycle marker."""
    from app.rag.ranking_policy import repair_common_mojibake

    programs = []
    for group in _groups(documents):
        content = repair_common_mojibake(group["content"])
        for match in _CYCLE_MARKER.finditer(content):
            tail_start = match.end()
            boundary = _NEXT_SECTION.search(content, tail_start)
            tail_end = boundary.start() if boundary else len(content)
            title = re.sub(r"\s+", " ", content[tail_start:tail_end]).strip(
                " \t\r\n:;,.\u2022-\u2013\u2014"
            )
            if not title or len(title) > 140 or re.match(
                r"^(?:pour|les cursus|des cursus|cursus)\b", _normalized(title)
            ):
                continue

            acronym = _acronym_for_title(content, title)
            preparatory_years = {}
            for prep_match in _PREPARATORY_MARKER.finditer(content):
                years = int(prep_match.group("years"))
                target_text = prep_match.group("targets")
                codes = re.findall(r"\b[A-Z]{2,8}\b", target_text)
                for code in codes:
                    preparatory_years[code.upper()] = years

            program = {
                "title": title,
                "acronym": acronym,
                "cycle_years": int(match.group("years")),
                "preparatory_years": preparatory_years.get(acronym),
                "source": group["source"],
                "page": group["page"],
            }

            duplicate = None
            for existing in programs:
                same_source_page = (
                    existing["source"] == program["source"]
                    and str(existing["page"]) == str(program["page"])
                )
                same_acronym = (
                    program["acronym"]
                    and existing["acronym"] == program["acronym"]
                )
                same_title = _normalized(existing["title"]) == _normalized(title)
                alias_title = same_source_page and _initialism_alias(
                    existing["title"], title
                )
                if same_acronym or (same_source_page and (same_title or alias_title)):
                    duplicate = existing
                    break

            if duplicate is None:
                programs.append(program)
            elif len(title) > len(duplicate["title"]):
                duplicate.update(program)

    return programs


def _reference_for_program(program: dict, references: dict[str, dict]) -> str | None:
    for reference_id, entry in references.items():
        if (
            entry.get("source") == program["source"]
            and str(entry.get("page")) == str(program["page"])
        ):
            return reference_id
    return None


def structured_program_list_answer(
    documents: list[dict], references: dict[str, dict]
) -> str | None:
    programs = extract_structured_programs(documents)
    if len(programs) < 2:
        return None
    entries = []
    for program in programs:
        reference_id = _reference_for_program(program, references)
        if reference_id is None:
            return None
        label = program["title"]
        if program["acronym"]:
            label += f" ({program['acronym']})"
        entries.append(f"{label} [[REF:{reference_id}]]")
    return "La brochure pr\u00e9sente les fili\u00e8res suivantes : " + "; ".join(entries) + "."


def structured_program_duration_answer(
    question: str,
    documents: list[dict],
    references: dict[str, dict],
) -> str | None:
    query = _normalized(question)
    programs = extract_structured_programs(documents)
    matching = []
    for program in programs:
        normalized_title = _normalized(program["title"])
        title_prefix = re.split(r"[,;:]", normalized_title, maxsplit=1)[0].strip()
        acronym = (program.get("acronym") or "").lower()
        acronym_match = bool(acronym and re.search(rf"\b{re.escape(acronym)}\b", query))
        if (
            normalized_title in query
            or (len(title_prefix) >= 8 and title_prefix in query)
            or acronym_match
        ):
            matching.append(program)
    if len(matching) != 1:
        return None

    program = matching[0]
    prep_years = program.get("preparatory_years")
    cycle_years = program.get("cycle_years")
    reference_id = _reference_for_program(program, references)
    if not prep_years or not cycle_years or reference_id is None:
        return None
    total_years = prep_years + cycle_years
    return (
        f"La brochure indique {prep_years} ann\u00e9es pr\u00e9paratoires, suivies de "
        f"{cycle_years} ann\u00e9es de cycle ing\u00e9nieur pour la fili\u00e8re "
        f"{program['title']} : {total_years} ann\u00e9es au total. [[REF:{reference_id}]]"
    )
