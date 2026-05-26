# zataone jurisdiction router
"""
Routes a (domain, jurisdiction) pair to the correct policy YAML file.

Resolution order for jurisdiction J in domain D:
  1. policies/<base>_<j_lower>.yaml   (e.g. meta_ads_eu.yaml)
  2. policies/<domain>_<j_lower>.yaml
  3. policies/<base>.yaml             (US / default)
  4. policies/<domain>.yaml

where <base> is inferred from the first YAML file found in the policies/ directory.
"""

from __future__ import annotations

import os
from typing import Final

KNOWN_JURISDICTIONS: Final[frozenset[str]] = frozenset(
    {"US", "EU", "UK", "CA", "AU", "SG", "IN", "BR"}
)
_DEFAULT: Final[str] = "US"


class JurisdictionRouter:
    """Resolves a policy pack file path for a given domain + jurisdiction."""

    def normalize(self, jurisdiction: str | None) -> str:
        """Return upper-cased, validated jurisdiction code (falls back to 'US')."""
        if not jurisdiction:
            return _DEFAULT
        j = jurisdiction.strip().upper()
        return j if j in KNOWN_JURISDICTIONS else _DEFAULT

    def resolve_policy_path(
        self,
        domain_path: str,
        domain: str,
        jurisdiction: str,
    ) -> str | None:
        """
        Return absolute path to the policy YAML for the given jurisdiction, or
        None if no policy file exists at all.

        Args:
            domain_path: Absolute filesystem path to the domain package directory.
            domain:      Domain name (e.g. "ad_compliance").
            jurisdiction: Normalised jurisdiction code (e.g. "EU").
        """
        j = self.normalize(jurisdiction)
        policies_dir = os.path.join(domain_path, "policies")
        if not os.path.isdir(policies_dir):
            return None

        # Collect candidate bases (prefer meta_ads, then domain name)
        candidates: list[str] = []
        for base in ("meta_ads", domain):
            if j != _DEFAULT:
                candidates.append(os.path.join(policies_dir, f"{base}_{j.lower()}.yaml"))
            candidates.append(os.path.join(policies_dir, f"{base}.yaml"))

        for path in candidates:
            if os.path.isfile(path):
                return path
        return None

    def available_jurisdictions(self, domain_path: str, domain: str) -> list[str]:
        """Return sorted list of jurisdiction codes that have a dedicated policy file."""
        policies_dir = os.path.join(domain_path, "policies")
        if not os.path.isdir(policies_dir):
            return [_DEFAULT]

        found = [_DEFAULT]
        for j in sorted(KNOWN_JURISDICTIONS - {_DEFAULT}):
            for base in ("meta_ads", domain):
                p = os.path.join(policies_dir, f"{base}_{j.lower()}.yaml")
                if os.path.isfile(p):
                    found.append(j)
                    break
        return found
