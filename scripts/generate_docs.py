"""Seeded synthetic document corpus generator: five templates (revenue
reports, stories, FAQs, meeting notes, how-tos) chosen to give the corpus
numeric and narrative variety for the RAG demo. Deterministic so re-running
it doesn't silently drift the corpus."""

import random
import re
from pathlib import Path

QUARTERS = ["Q1", "Q2", "Q3", "Q4"]
YEARS = [2022, 2023, 2024, 2025]
REGIONS = ["North America", "EMEA", "APAC", "Latin America"]
PRODUCTS = ["Atlas", "Nimbus", "Vertex", "Solace", "Quill"]

CHARACTERS = ["Mira", "Owen", "Priya", "Teodor", "Lin", "Amara"]
SETTINGS = [
    "a lighthouse on the edge of a cliff",
    "an abandoned observatory",
    "a river town after the flood",
    "a workshop above a bakery",
    "a train stalled between stations",
]
OBJECTS = [
    "a brass compass",
    "a locked journal",
    "a jar of stormlight",
    "an unopened letter",
    "a key with no lock",
]

FEATURES = ["billing", "single sign-on", "data export", "rate limits", "webhooks"]

ATTENDEES = ["Dana", "Miguel", "Sofia", "Ken", "Aisha", "Robert"]
TOPICS = ["Q4 roadmap", "incident postmortem", "hiring plan", "vendor renewal", "pricing changes"]

TASKS = [
    "rotate an API key",
    "configure retries",
    "set up a webhook",
    "back up the database",
    "scale a worker pool",
]


def generate_revenue_report(rng: random.Random, index: int) -> tuple[str, str]:
    quarter = rng.choice(QUARTERS)
    year = rng.choice(YEARS)
    region = rng.choice(REGIONS)
    revenue = rng.randint(800_000, 9_500_000)
    growth = rng.uniform(-8.5, 32.0)
    product_lines = rng.sample(PRODUCTS, k=3)

    rows = []
    remaining = revenue
    for i, product in enumerate(product_lines):
        share = remaining // (len(product_lines) - i) if i < len(product_lines) - 1 else remaining
        rows.append((product, share))
        remaining -= share

    title = f"{quarter} {year} Revenue Report - {region} ({index})"
    lines = [
        f"# {title}",
        "",
        f"Total revenue for {region} in {quarter} {year} reached **${revenue:,}**, "
        f"a {growth:+.1f}% change from the prior quarter.",
        "",
        "| Product | Revenue |",
        "|---|---|",
    ]
    lines += [f"| {product} | ${share:,} |" for product, share in rows]
    lines += [
        "",
        f"Regional headcount stood at {rng.randint(40, 900)} employees, "
        f"with an average deal size of ${rng.randint(1_200, 85_000):,}.",
    ]
    return title, "\n".join(lines)


def generate_story(rng: random.Random, index: int) -> tuple[str, str]:
    who = rng.choice(CHARACTERS)
    where = rng.choice(SETTINGS)
    what = rng.choice(OBJECTS)
    days = rng.randint(3, 90)

    title = f"The {what.split()[-1].capitalize()} of {where.split()[-1].capitalize()} ({index})"
    body = (
        f"# {title}\n\n"
        f"{who} had been living in {where} for {days} days when {what} turned up "
        f"under the floorboards. Nobody in town would say how long it had been there, "
        f"only that {rng.randint(2, 40)} others had looked for it before and never came back "
        f"with an answer.\n\n"
        f"By the {rng.randint(2, 12)}th night, {who} stopped asking why, and started asking "
        f"what it opened."
    )
    return title, body


def generate_faq(rng: random.Random, index: int) -> tuple[str, str]:
    feature = rng.choice(FEATURES)
    limit = rng.choice([100, 500, 1000, 5000, 10000])
    price = rng.choice([9, 29, 49, 99, 199])

    title = f"FAQ: {feature.title()} ({index})"
    body = (
        f"# {title}\n\n"
        f"**Q: What's the default limit for {feature}?**\n"
        f"A: {limit:,} requests per day on the standard plan.\n\n"
        f"**Q: How much does the {feature} add-on cost?**\n"
        f"A: ${price}/month, billed annually at a {rng.randint(5, 20)}% discount.\n\n"
        f"**Q: Who do I contact for {feature} issues?**\n"
        f"A: Support responds within {rng.choice([1, 2, 4, 24])} hours on business days."
    )
    return title, body


def generate_meeting_notes(rng: random.Random, index: int) -> tuple[str, str]:
    topic = rng.choice(TOPICS)
    attendees = rng.sample(ATTENDEES, k=rng.randint(2, 4))
    action_items = rng.randint(1, 5)

    title = f"Meeting Notes: {topic.title()} ({index})"
    lines = [f"# {title}", "", f"Attendees: {', '.join(attendees)}", "", "## Discussion", ""]
    lines.append(
        f"The team reviewed {topic} and agreed budget impact was roughly "
        f"${rng.randint(5_000, 250_000):,}, affecting {rng.randint(1, 12)} teams."
    )
    lines += ["", "## Action items"]
    for _ in range(action_items):
        owner = rng.choice(attendees)
        lines.append(f"- [ ] {owner} to follow up within {rng.randint(1, 14)} days")
    return title, "\n".join(lines)


def generate_howto(rng: random.Random, index: int) -> tuple[str, str]:
    task = rng.choice(TASKS)
    steps = rng.randint(3, 6)

    title = f"How to {task} ({index})"
    lines = [f"# {title}", ""]
    for i in range(1, steps + 1):
        lines.append(
            f"{i}. {task.capitalize()} step {i}: run the command and confirm the "
            f"response code is {rng.choice([200, 201, 204])}."
        )
    lines += [
        "",
        f"Typical completion time is under {rng.randint(1, 30)} minutes; "
        f"rollback window is {rng.randint(5, 60)} minutes.",
    ]
    return title, "\n".join(lines)


GENERATORS = [
    generate_revenue_report,
    generate_story,
    generate_faq,
    generate_meeting_notes,
    generate_howto,
]


def generate_corpus(output_dir: Path, seed: int = 42, per_template: int = 20) -> int:
    rng = random.Random(seed)
    output_dir.mkdir(exist_ok=True)

    count = 0
    for generator in GENERATORS:
        prefix = generator.__name__.removeprefix("generate_")
        for i in range(per_template):
            title, body = generator(rng, i)
            slug = re.sub(r"[^a-z0-9_-]", "", title.lower().replace(" ", "_"))[:40]
            path = output_dir / f"{prefix}_{i:02d}_{slug}.md"
            path.write_text(body)
            count += 1
    return count


if __name__ == "__main__":
    total = generate_corpus(Path("documents"))
    print(f"Generated {total} documents in documents/")
