"""Evidence for the review badge on published journal records."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from urllib.parse import urlsplit

import requests

APS_API = 'https://harvest.aps.org/v2/journals/articles'
REVIEWED_APS_TYPES = {'article', 'letter', 'rapid', 'rapid-communication', 'research-article'}


@lru_cache(maxsize=1)
def aps_research_dois():
    """Read the publisher's article types for the digest's recent APS papers."""
    today = datetime.now(timezone(timedelta(hours=8))).date()
    url = APS_API
    params = {'from': (today - timedelta(days=29)).isoformat(), 'until': today.isoformat(), 'per_page': 100}
    verified = set()
    try:
        with requests.Session() as session:
            for _ in range(65):
                response = session.get(url, params=params, timeout=20)
                response.raise_for_status()
                for work in response.json()['data']:
                    if work.get('articleType') in REVIEWED_APS_TYPES:
                        verified.add(work['id'].lower())
                url = response.links.get('next', {}).get('url')
                if not url or urlsplit(url).hostname != 'harvest.aps.org':
                    break
                params = None
    except (requests.RequestException, KeyError, ValueError) as exc:
        print(f'APS review metadata incomplete: {exc}', flush=True)
    return verified


def peer_reviewed(item, journal):
    doi = item.get('DOI', '').lower()
    relations = item.get('relation') or {}
    if any(r.get('id') for r in relations.get('is-reviewed-by', [])):
        return True
    return doi.startswith('10.1103/') and doi in aps_research_dois()
