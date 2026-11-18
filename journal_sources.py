"""Crossref journal harvest, by ISSN and publisher-reported publication date."""
from __future__ import annotations

import gzip
import html
import json
import os
import re
import time
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

if __package__:
    from .peer_review import peer_reviewed
else:
    from peer_review import peer_reviewed

JOURNALS = {
    'Nature': '0028-0836', 'Nature Physics': '1745-2473', 'Science': '0036-8075',
    'Physical Review Letters': '0031-9007', 'Physical Review A': '2469-9926',
    'Physical Review B': '2469-9950', 'Physical Review C': '2469-9985',
    'Physical Review D': '2470-0010', 'Physical Review E': '2470-0045',
    'Physical Review X': '2160-3308', 'PRX Quantum': '2691-3399',
    'Physical Review Applied': '2331-7019', 'Physical Review Research': '2643-1564',
    'Physical Review Fluids': '2469-990X', 'Physical Review Materials': '2475-9953',
    'PRX Energy': '2768-5608', 'PRX Life': '2831-2856',
}
FIELDS = 'DOI,title,author,published,abstract,relation,container-title'
PAGE_SIZE = 100
MAX_PAGES = 50  # 5,000 records per journal per window; partial results survive a limit/error.


def fetch_page(issn, start, end, cursor, rows):
    params = {'filter': f'type:journal-article,from-pub-date:{start},until-pub-date:{end}',
              'rows': rows, 'cursor': cursor, 'select': FIELDS}
    if os.environ.get('CROSSREF_MAILTO'):
        params['mailto'] = os.environ['CROSSREF_MAILTO']
    req = Request(f'https://api.crossref.org/journals/{issn}/works?' + urlencode(params),
                  headers={'User-Agent': 'PersonalPhysicsDigest/1.0 (https://github.com/liuk-08/arxiv-daily)',
                           'Accept-Encoding': 'gzip'})
    for attempt in range(2):
        time.sleep(1)
        try:
            with urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if resp.headers.get('Content-Encoding') == 'gzip':
                    raw = gzip.decompress(raw)
                return json.loads(raw)['message']
        except HTTPError as exc:
            retry = exc.headers.get('Retry-After', '5')
            if attempt or exc.code not in (429, 500, 502, 503, 504) or not retry.isdigit() or int(retry) > 60:
                raise
            time.sleep(max(5, int(retry)))
        except (TimeoutError, URLError):
            if attempt:
                raise
            time.sleep(3)


def iter_items(issn, start, end, rows=PAGE_SIZE):
    cursor = '*'
    seen = set()
    for _ in range(MAX_PAGES):
        message = fetch_page(issn, start, end, cursor, rows)
        items = message['items']
        # Crossref cursors may repeat even when the page advances; compare actual records.
        fresh = [item for item in items if item.get('DOI', '').lower() not in seen]
        for item in fresh:
            seen.add(item.get('DOI', '').lower())
            yield item
        if len(items) < rows or len(seen) >= message['total-results']:
            return
        if not fresh or not message.get('next-cursor'):
            raise RuntimeError('Incomplete Crossref result: pagination stopped advancing')
        cursor = message['next-cursor']
    raise RuntimeError(f'Crossref cap of {MAX_PAGES * rows} records reached')


def text(value):
    value = re.sub(r'</?(?:jats:)?(?:p|title|sec)\b[^>]*>', ' ', value or '', flags=re.I)
    return ' '.join(html.unescape(re.sub(r'</?[A-Za-z][^>]*>', '', value)).split())


def journal_entry(item, journal, start, end, classify):
    parts = item.get('published', {}).get('date-parts', [[]])[0]
    if len(parts) != 3:  # Do not invent exact days from month/year-only metadata.
        return None
    try:
        day = date(*parts)
    except (TypeError, ValueError):
        return None
    doi = item.get('DOI', '').strip().lower()
    title = text(next(iter(item.get('title', [])), ''))
    if not (start <= day <= end and re.fullmatch(r'10\.\d{4,9}/\S+', doi) and title):
        return None
    summary = text(item.get('abstract', ''))
    topics = classify(title, summary, [])
    if not topics:
        return None
    authors = item.get('author') or []
    names = [a.get('name') or ' '.join(filter(None, (a.get('given'), a.get('family')))) for a in authors[:20]]
    entry = {'source': 'journal', 'journal': journal, 'doi': doi, 'id': 'doi:' + doi,
             'url': 'https://doi.org/' + quote(doi, safe='/'), 'published': day.isoformat(),
             'title': title, 'summary': summary, 'authors': ', '.join(filter(None, names)) + (' et al.' if len(authors) > 20 else ''),
             'topics': topics, 'categories': []}
    if peer_reviewed(item, journal):
        entry['peerReviewed'] = True
    return entry


def journal_papers(start, end, classify):
    for journal, issn in JOURNALS.items():
        scanned = matched = 0
        try:
            for item in iter_items(issn, start, end):
                scanned += 1
                paper = journal_entry(item, journal, start, end, classify)
                if paper:
                    matched += 1
                    yield paper
        except Exception as exc:
            print(f'Crossref incomplete for {journal}: {exc}', flush=True)
        print(f'Crossref {journal}: {matched} matches / {scanned} records', flush=True)
