#!/usr/bin/env python3
"""Fetch recent arXiv Atom entries and rebuild the static daily digest."""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

try:
    import requests
except ImportError:
    requests = None
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "daily.js"
API = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
CST = timezone(timedelta(hours=8))
RETENTION_DAYS = 30

# Search broad source categories first; the local rules below assign topic labels.
PARTICLE_CATEGORIES = ("hep-ph", "hep-ex", "hep-lat")
CATEGORIES = ["quant-ph", "cs.CC", "physics.atom-ph", "physics.ins-det", "astro-ph.CO",
              "gr-qc", "astro-ph.HE", "astro-ph.GA", *PARTICLE_CATEGORIES, "hep-th"]
RSS_CATEGORIES = CATEGORIES
RULES = {
    "sensing": re.compile(r"\b(quantum metrolog\w*|quantum sens\w*|atomic magnetometr\w*|magnetometr\w*|serf|spin squeez\w*|optically pumped|precision measurement|sensitivity enhancement|atomic clock\w*|spin-exchange relaxation)\b", re.I),
    "dark": re.compile(
        r"\b(dark[ -](?:matter|photons?|sectors?|halos?)|axion\w*|ALPs?|WIMPs?|"
        r"ultralight dark|haloscope\w*|direct detection|hidden photons?|"
        r"relic (?:abundance|density)|thermal relics?|galactic rotation curves?|"
        r"halo substructure|self[ -]interacting DM|(?:Lambda[ -]?|Λ)CDM)\b", re.I),
    "foundations": re.compile(r"\b(quantum foundation\w*|measurement problem|quantum measurement\w*|Bell inequalities?|Bell nonlocal\w*|nonlocality|contextuality|quantum interpretation\w*|wave function collapse|collapse model\w*|ψ-ontology|born rule|quantum ontology)\b", re.I),
    "computing": re.compile(
        r"\b(quantum[ -](?:comput\w*|algorithms?|circuits?|processors?|gates?|"
        r"error[ -]correction|advantage|anneal\w*)|logical qubits?|qubit gates?|"
        r"fault[ -]tolerant qubits?|variational quantum eigensolver\w*)\b", re.I),
    "qgravity": re.compile(
        r"\b(quantum[ -](?:gravity|gravitational|spacetime|geometry|cosmology)|"
        r"gravit(?:y|ational) quantization|gravitons?|spin[ -]foams?|causal sets?|"
        r"causal dynamical triangulations?|asymptotically safe gravity|"
        r"string theor(?:y|ies)|AdS\s*/\s*CFT|gauge[ -]gravity duality|holographic duality|"
        r"black[ -]hole information paradox)\b", re.I),
    "particle": re.compile(
        r"\b(particle physics|elementary particles?|quarks?|leptons?|neutrinos?|"
        r"Higgs(?: bosons?)?|particle colliders?|large hadron collider|lattice QCD|"
        r"quantum chromodynamics|beyond the standard model)\b", re.I),
}

def normalize_entry(paper_id: str, title: str, summary: str, authors: str, published: str, categories: list[str]) -> dict | None:
    haystack = f"{title} {summary}"
    topics = [key for key, pattern in RULES.items() if pattern.search(haystack)]
    if "particle" not in topics and any(cat in PARTICLE_CATEGORIES for cat in categories):
        topics.append("particle")
    if not topics:
        return None
    return {"id": paper_id, "title": title, "summary": summary, "authors": authors,
            "published": published[:10], "categories": categories, "topics": topics,
            "url": f"https://arxiv.org/abs/{paper_id}"}

def request_rss(category: str) -> list[dict]:
    url = f"https://export.arxiv.org/rss/{category}"
    if requests:
        response = requests.get(url, timeout=45, headers={"User-Agent": "PersonalArxivDailyDigest/1.0"})
        response.raise_for_status()
        raw = response.content
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "PersonalArxivDailyDigest/1.0"})
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read()
    root = ET.fromstring(raw)
    entries = []
    for node in root.findall("./channel/item"):
        link = node.findtext("link", default="")
        paper_id = link.rstrip("/").rsplit("/", 1)[-1].split("v")[0]
        description = node.findtext("description", default="")
        abstract_match = re.search(r"Abstract:\s*(.*)", description, flags=re.I | re.S)
        summary = abstract_match.group(1).strip() if abstract_match else description
        summary = re.split(r"\s+Journal-ref:|\s+Comments:", summary, maxsplit=1)[0]
        summary = re.sub(r"\s+", " ", summary)
        published_raw = node.findtext("pubDate", default="")
        try:
            published = datetime.strptime(published_raw, "%a, %d %b %Y %H:%M:%S %z").astimezone(CST).date().isoformat()
        except ValueError:
            published = datetime.now(CST).date().isoformat()
        creators = [x.text or "" for x in node.findall("{http://purl.org/dc/elements/1.1/}creator")]
        categories = [term for x in node.findall("category") for term in (x.text or "").split()] or [category]
        paper = normalize_entry(paper_id, node.findtext("title", default=""), summary, ", ".join(creators), published, categories)
        if paper:
            entries.append(paper)
    return entries

def request_feed(category: str, start: int, count: int) -> list[dict]:
    params = {"search_query": f"cat:{category}", "start": str(start), "max_results": str(count),
              "sortBy": "submittedDate", "sortOrder": "descending"}
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "PersonalArxivDailyDigest/1.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        root = ET.fromstring(response.read())
    entries = []
    for node in root.findall("a:entry", NS):
        paper_id = node.findtext("a:id", default="", namespaces=NS).rsplit("/", 1)[-1].split("v")[0]
        title = " ".join(node.findtext("a:title", default="", namespaces=NS).split())
        summary = " ".join(node.findtext("a:summary", default="", namespaces=NS).split())
        authors = ", ".join(a.findtext("a:name", default="", namespaces=NS) for a in node.findall("a:author", NS))
        published = node.findtext("a:published", default="")[:10]
        categories = [c.attrib.get("term", "") for c in node.findall("a:category", NS)]
        paper = normalize_entry(paper_id, title, summary, authors, published, categories)
        if paper:
            entries.append(paper)
    return entries

def main() -> None:
    # arXiv API limits request frequency; fetch a rolling window by source category.
    by_id: dict[str, dict] = {}
    per_category = 180
    source_errors = []
    for index, category in enumerate(RSS_CATEGORIES):
        print(f"Fetching RSS {category} ({index + 1}/{len(RSS_CATEGORIES)})", flush=True)
        try:
            entries = request_rss(category)
        except Exception as exc:
            source_errors.append((category, str(exc)))
            print(f"RSS failed {category}: {exc}", flush=True)
            continue
        for paper in entries:
            previous = by_id.get(paper["id"])
            if previous:
                previous["topics"] = sorted(set(previous["topics"] + paper["topics"]))
                previous["categories"] = sorted(set(previous["categories"] + paper["categories"]))
            else:
                by_id[paper["id"]] = paper
        if index < len(RSS_CATEGORIES) - 1:
            time.sleep(1.2)

    if not by_id:
        print("RSS did not return matching entries; trying Atom API as fallback.", flush=True)
        for category in CATEGORIES:
            try:
                for paper in request_feed(category, 0, per_category):
                    by_id[paper["id"]] = paper
            except Exception as exc:
                print(f"Atom failed {category}: {exc}", flush=True)

    if not by_id:
        raise SystemExit("No arXiv entries were fetched; existing daily.js was left unchanged.")

    today = datetime.now(CST).date()
    batches: dict[str, dict] = {}
    # Keep prior generated batches so the six-date history grows across daily runs.
    if DATA_FILE.exists():
        try:
            old_text = DATA_FILE.read_text(encoding="utf-8")
            match = re.search(r"window\.DSH_DAILY_DATA\s*=\s*(\{.*\});?\s*$", old_text, flags=re.S)
            if match:
                old_data = json.loads(match.group(1))
                batches.update(old_data.get("batches", {}))
        except (OSError, json.JSONDecodeError):
            pass

    current_batches: dict[str, dict] = {}
    for paper in by_id.values():
        try:
            day = datetime.fromisoformat(paper["published"].replace("Z", "+00:00")).astimezone(CST).date()
        except ValueError:
            continue
        age = (today - day).days
        if not 0 <= age < RETENTION_DAYS:
            continue
        date = day.isoformat()
        current_batches.setdefault(date, {"papers": []})["papers"].append(paper)

    for date, batch in current_batches.items():
        merged = {p["id"]: p for p in batches.get(date, {}).get("papers", [])}
        for paper in batch["papers"]:
            merged[paper["id"]] = paper
        batches[date] = {"papers": list(merged.values())}

    batches = {date: batch for date, batch in batches.items() if 0 <= (today - datetime.fromisoformat(date).date()).days < RETENTION_DAYS}
    dates = sorted(batches, reverse=True)
    batches = {date: batches[date] for date in dates}
    for batch in batches.values():
        batch["papers"].sort(key=lambda paper: paper["published"], reverse=True)
    payload = {"updatedAt": datetime.now(CST).strftime("%Y-%m-%d %H:%M CST"), "dates": dates, "batches": batches}
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text("window.DSH_DAILY_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"Wrote {sum(len(v['papers']) for v in batches.values())} papers across {len(dates)} daily batches to {DATA_FILE}")

if __name__ == "__main__":
    main()
