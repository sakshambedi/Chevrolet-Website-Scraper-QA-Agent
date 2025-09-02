"""
GM embedder base that normalizes page data and emits embedding-ready docs.
Covers metadata, prices, sections, assets, links, trims, related models, awards.
Subclasses may define TRIM_NAMES.
"""

from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import re
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple
from urllib.parse import urlparse

from embedding.embedding import BaseEmbedder, Record


class GMBaseEmbedder(BaseEmbedder):
    """Base embedder for GM websites using a shared JSON shape."""

    # Known GM brands (used to parse title -> model name)
    BRANDS: List[str] = ["Chevrolet", "GMC", "Buick", "Cadillac"]
    # Heading label that precedes the trims/models slider
    MODELS_HEADING: str = "Models"
    # Default currency used in price blocks
    DEFAULT_CURRENCY: str = "CAD"

    # Sections of interest to emit as content docs
    INTERESTING_SECTIONS = re.compile(
        r"towing|trailering|performance|interior|safety|technology|capability|award|awards|accolades|dependabil",
        re.I,
    )

    # Optional: subclasses may provide a static list of known trims
    TRIM_NAMES: List[str] = []

    def extract_records(self, item: Dict[str, Any], index: int) -> Iterable[Record]:
        norm = self._normalize_item(item)
        docs = self._build_docs(norm)
        for d in docs:
            yield Record(id=d["id"], text=d["text"], metadata=d["metadata"])

    def _normalize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        meta = item.get("metadata", {})
        canonical = meta.get("canonical") or item.get("url")
        locale = meta.get("language") or "en-CA"
        title = (meta.get("title") or "").strip()
        description = (meta.get("description") or "").strip()

        year, model_name = self._parse_year_and_model(title)
        model_id = self._slug(model_name)

        disc_map: Dict[str, str] = {}

        def reg_disc(text: Optional[str], key: Optional[str] = None) -> Optional[str]:
            if not text:
                return None
            disc_id = f"disc:{self._short_hash((key or '') + '|' + text)}"
            if disc_id not in disc_map:
                disc_map[disc_id] = str(text).strip()
            return disc_id

        prices, _ = self._extract_prices(
            item, canonical, model_id, reg_disc
        )

        sections = self._extract_sections(item, model_id, canonical, reg_disc)

        assets = self._extract_assets(item)

        trims = self._extract_trims(item, model_id)
        trims = self._enrich_trims(item, model_id, trims, reg_disc)

        related_models = self._extract_related_models(item, reg_disc)

        links_global = self._collect_links(item)
        model_links = self._select_links_for_model(
            links_global, model_id, model_name, canonical
        )
        for rm in related_models:
            rm["links"] = self._select_links_for_model(
                links_global, rm.get("id"), rm.get("name"), canonical
            )

        awards: List[Dict[str, Any]] = []
        for s in sections:
            title_s = (s.get("title") or "").strip()
            if not title_s:
                continue
            if re.search(r"award|awards|accolade|dependabil", title_s, re.I):
                awd_id = f"awd:{self._slug(title_s)}"
                awards.append(
                    {
                        "id": awd_id,
                        "model_id": model_id,
                        "title": title_s,
                        "summary": s.get("body") or "",
                        "disclosure_ids": list(s.get("disclosure_ids") or []),
                        "source_url": s.get("source_url") or canonical,
                    }
                )

        models = [
            {
                "id": model_id,
                "name": model_name,
                "year": year,
                "canonical_url": canonical,
                "locale": locale,
                "trim_ids": [t["id"] for t in trims],
                "section_ids": [s["id"] for s in sections],
                "asset_ids": [a["id"] for a in assets],
                "award_ids": [a["id"] for a in awards],
                "title": title,
                "description": description,
                "links": model_links,
            }
        ]

        disclosures = [
            {"id": k, "text": v}
            for k, v in sorted(disc_map.items(), key=lambda x: x[0])
        ]

        return {
            "models": models,
            "prices": prices,
            "disclosures": disclosures,
            "assets": assets,
            "sections": sections,
            "trims": trims,
            "related_models": related_models,
            "awards": awards,
        }

    def _parse_year_and_model(self, title: str) -> Tuple[Optional[int], str]:
        year_match = re.search(r"(19|20)\d{2}", title)
        year = int(year_match.group(0)) if year_match else None
        model = title
        for brand in self.BRANDS:
            if brand in title:
                after = title.split(brand, 1)[1].strip()
                model = after.split("|")[0].strip()
                break
        model = re.sub(r"\s+", " ", model)
        return year, model
    
    def _extract_prices(
        self,
        item: Dict[str, Any],
        canonical: Optional[str],
        model_id: str,
        reg_disc,
    ) -> tuple[list[Dict[str, Any]], list[str]]:
        price_entries: List[Dict[str, Any]] = []
        price_disc_ids: List[str] = []

        for node, _parent in self._iter_nodes_with_parent(item):
            if not (isinstance(node, dict) and node.get("type") == "a link"):
                continue
            href = node.get("href")
            if not href or not canonical or href.strip() != str(canonical).strip():
                continue

            content = node.get("content") or []
            gbd_nodes = [
                c.get("gb-dynamic-text")
                for c in content
                if isinstance(c, dict) and c.get("gb-dynamic-text")
            ]
            if not gbd_nodes:
                continue

            from_map: Dict[str, str] = {}
            shown_map: Dict[str, str] = {}
            disc_ids_local: List[str] = []
            for gbd in gbd_nodes:
                ri = (gbd or {}).get("regional_information") or {}
                text_nodes = (gbd or {}).get("content") or []
                # inline disclosures
                for t in text_nodes:
                    if not isinstance(t, dict):
                        continue
                    for ch in t.get("content") or []:
                        if isinstance(ch, dict) and ch.get("gb-disclosure"):
                            dt = ch["gb-disclosure"]
                            disc_text = dt if isinstance(dt, str) else dt.get("text")
                            disc_id = reg_disc(disc_text, key="price")
                            if disc_id:
                                disc_ids_local.append(disc_id)
                # block template cues
                p_texts = [
                    t.get("p") for t in text_nodes if isinstance(t, dict) and t.get("p")
                ]
                para = " ".join(p_texts).lower()
                if "from:" in para or "starting" in para:
                    for region, vals in ri.items():
                        sp = self._normalize_price((vals or {}).get("startingPrice"))
                        if sp:
                            from_map[region] = sp
                if "as shown" in para or "as configured" in para:
                    for region, vals in ri.items():
                        ap = self._normalize_price((vals or {}).get("asShownPrice"))
                        if ap:
                            shown_map[region] = ap

            regions = sorted(set(from_map.keys()) | set(shown_map.keys()))
            for r in regions:
                entry = {
                    "id": f"price:{model_id}:{r}",
                    "model_id": model_id,
                    "region": r,
                    "from_price": from_map.get(r),
                    "as_shown_price": shown_map.get(r),
                    "currency": self.DEFAULT_CURRENCY,
                    "disclosure_ids": list(dict.fromkeys(disc_ids_local))
                    if disc_ids_local
                    else [],
                    "source": "navbar",
                }
                price_entries.append(entry)
            price_disc_ids.extend(disc_ids_local)

        best: Dict[str, Dict[str, Any]] = {}
        for e in price_entries:
            r = e["region"]
            if r not in best:
                best[r] = e
                continue
            cur = best[r]

            def has_both(x: Dict[str, Any]) -> bool:
                return bool(x.get("from_price")) and bool(x.get("as_shown_price"))

            if has_both(cur):
                continue
            if has_both(e):
                best[r] = e
                continue
            if not cur.get("from_price") and e.get("from_price"):
                cur["from_price"] = e["from_price"]
            if not cur.get("as_shown_price") and e.get("as_shown_price"):
                cur["as_shown_price"] = e["as_shown_price"]
            cur["disclosure_ids"] = list(
                dict.fromkeys(
                    (cur.get("disclosure_ids") or []) + (e.get("disclosure_ids") or [])
                )
            )

        return list(best.values()), list(dict.fromkeys(price_disc_ids))

    def _extract_sections(
        self,
        item: Dict[str, Any],
        model_id: str,
        canonical: Optional[str],
        reg_disc,
    ) -> List[Dict[str, Any]]:
        body = item.get("main_body_content") or []

        sections: List[Dict[str, Any]] = []

        def collect_from_node(n: Any) -> tuple[list[str], list[str]]:
            texts: List[str] = []
            discs: List[str] = []
            if not isinstance(n, (dict, list)):
                return texts, discs
            for node in self._iter_nodes(n):
                if isinstance(node, dict) and node.get("p"):
                    pt = (node.get("p") or "").strip()
                    if pt:
                        texts.append(pt)
                if isinstance(node, dict) and node.get("gb-dynamic-text"):
                    for t in node["gb-dynamic-text"].get("content") or []:
                        if isinstance(t, dict) and t.get("p"):
                            pt = (t.get("p") or "").strip()
                            if pt:
                                texts.append(pt)
                        for ch in t.get("content") or []:
                            if isinstance(ch, dict) and ch.get("gb-disclosure"):
                                dt = ch["gb-disclosure"]
                                disc_text = (
                                    dt if isinstance(dt, str) else dt.get("text")
                                )
                                disc_id = reg_disc(disc_text, key="section")
                                if disc_id:
                                    discs.append(disc_id)
                if isinstance(node, dict) and node.get("gb-disclosure"):
                    dt = node["gb-disclosure"]
                    disc_text = dt if isinstance(dt, str) else dt.get("text")
                    disc_id = reg_disc(disc_text, key="section")
                    if disc_id:
                        discs.append(disc_id)
            return texts, list(dict.fromkeys(discs))

        seen: set[str] = set()
        for node, parent in self._iter_nodes_with_parent(body):
            if not (isinstance(node, dict) and node.get("heading")):
                continue
            heading = (node.get("heading") or "").strip()
            if not self.INTERESTING_SECTIONS.search(heading):
                continue
            sec_id = f"sec:{self._slug(heading)}"
            if sec_id in seen:
                continue
            seen.add(sec_id)

            current = {
                "id": sec_id,
                "model_id": model_id,
                "title": heading,
                "body": "",
                "disclosure_ids": [],
                "source_url": canonical,
                "_parts": [],
            }

            if isinstance(parent, list):
                start_idx = None
                for idx, el in enumerate(parent):
                    if el is node:
                        start_idx = idx
                        break
                if start_idx is not None:
                    j = start_idx + 1
                    while j < len(parent):
                        sib = parent[j]
                        if isinstance(sib, dict) and sib.get("heading"):
                            break
                        texts, discs = collect_from_node(sib)
                        if texts:
                            current["_parts"].extend(texts)
                        if discs:
                            current.setdefault("disclosure_ids", []).extend(discs)
                        j += 1

            texts, discs = collect_from_node(node)
            if texts:
                current["_parts"].extend(texts)
            if discs:
                current.setdefault("disclosure_ids", []).extend(discs)

            body_text = "\n".join(
                t.strip() for t in current.get("_parts", []) if t and t.strip()
            ).strip()
            if body_text:
                current["body"] = body_text
                current.pop("_parts", None)
                sections.append(current)

        for s in sections:
            s["disclosure_ids"] = list(dict.fromkeys(s.get("disclosure_ids") or []))

        return sections

    def _extract_assets(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        assets: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for node in self._iter_nodes(item):
            if isinstance(node, dict) and node.get("type") == "image":
                url = node.get("src")
                if not url or url in seen:
                    continue
                seen.add(url)
                aid = f"img:{self._short_hash(url)}"
                assets.append(
                    {"id": aid, "type": "image", "url": url, "alt": node.get("alt")}
                )
        return assets

    def _find_models_slider(self, item: Dict[str, Any]) -> Any:
        body = item.get("main_body_content") or []
        for i, n in enumerate(body):
            if isinstance(n, dict) and n.get("heading") == self.MODELS_HEADING:
                for j in range(i + 1, min(i + 8, len(body))):
                    cand = body[j]
                    if isinstance(cand, (dict, list)):
                        return cand
        return body

    def _extract_trims(
        self, item: Dict[str, Any], model_id: str
    ) -> List[Dict[str, Any]]:
        if not self.TRIM_NAMES:
            return []
        found: Dict[str, Dict[str, Any]] = {}
        candidates = set(self.TRIM_NAMES)
        slider = self._find_models_slider(item)
        for node in self._iter_nodes(slider):
            name: Optional[str] = None
            if isinstance(node, dict) and "p" in node and isinstance(node["p"], str):
                text = node.get("p", "").strip()
                if text in candidates:
                    name = text
            elif (
                isinstance(node, dict)
                and "heading" in node
                and isinstance(node["heading"], str)
            ):
                text = node.get("heading", "").strip()
                if text in candidates:
                    name = text
            if name:
                sid = f"{model_id}:{self._slug(name)}"
                found.setdefault(sid, {"id": sid, "model_id": model_id, "name": name})
        return list(found.values())

    def _enrich_trims(
        self,
        item: Dict[str, Any],
        model_id: str,
        trims: List[Dict[str, Any]],
        reg_disc,
    ) -> List[Dict[str, Any]]:
        if not self.TRIM_NAMES:
            return trims

        by_name = {t["name"].lower(): dict(t) for t in trims}

        def canon_name(n: str) -> Optional[str]:
            n = (n or "").strip()
            for nm in self.TRIM_NAMES:
                if nm.lower() == n.lower():
                    return nm
            return None

        def detect_from_text(s: str) -> Optional[str]:
            if not s:
                return None
            s_low = s.lower()
            for nm in sorted(self.TRIM_NAMES, key=lambda x: -len(x)):
                patt = re.compile(r"\b" + re.escape(nm.lower()) + r"\b")
                if patt.search(s_low):
                    return nm
            return None

        current_trim: Optional[str] = None
        in_models_section = False
        body = item.get("main_body_content") or []

        def ensure_trim(nm: str) -> Dict[str, Any]:
            key = nm.lower()
            if key not in by_name:
                tid = f"{model_id}:{self._slug(nm)}"
                by_name[key] = {"id": tid, "model_id": model_id, "name": nm}
            return by_name[key]

        def flatten_ul_items(lst: List[Any]) -> List[str]:
            out: List[str] = []
            for el in lst:
                if el is None:
                    continue
                if isinstance(el, str):
                    s = el.strip()
                    if s:
                        out.append(s)
                    continue
                if isinstance(el, dict):
                    base = (el.get("text") or el.get("p") or "").strip()
                    tails: List[str] = []
                    for ch in el.get("content") or []:
                        if isinstance(ch, dict) and ch.get("gb-disclosure"):
                            dt = ch["gb-disclosure"]
                            frag = dt if isinstance(dt, str) else (dt.get("text") or "")
                            if frag:
                                tails.append(str(frag))
                    if tails:
                        first = tails[0]
                        rest = tails[1:]
                        if base.endswith("-"):
                            combined = base + first.lstrip()
                            if rest:
                                combined = combined + " " + " ".join(rest)
                        else:
                            combined = base + " " + " ".join(tails)
                        text = combined.strip()
                    else:
                        text = base
                    if text:
                        out.append(text)
            return [t for t in (s.strip() for s in out) if t]

        for node in self._iter_nodes(body):
            if isinstance(node, dict) and node.get("heading") == self.MODELS_HEADING:
                in_models_section = True
                continue
            if in_models_section and isinstance(node, dict) and node.get("heading"):
                if node.get("heading") not in (None, ""):
                    in_models_section = False
            if not in_models_section:
                continue
            if isinstance(node, dict) and node.get("gb-dynamic-text"):
                gbd = node["gb-dynamic-text"]
                text_nodes = (gbd or {}).get("content") or []
                if (
                    text_nodes
                    and isinstance(text_nodes[0], dict)
                    and text_nodes[0].get("p")
                ):
                    name = canon_name(text_nodes[0].get("p") or "")
                    if name:
                        current_trim = name
                        ensure_trim(name)
                        continue
                if current_trim:
                    name = current_trim
                    para = " ".join(
                        [
                            t.get("p")
                            for t in text_nodes
                            if isinstance(t, dict) and t.get("p")
                        ]
                    ).lower()
                    ri = (gbd or {}).get("regional_information") or {}
                    disc_ids_local: List[str] = []
                    for t in text_nodes:
                        for ch in t.get("content") or []:
                            if isinstance(ch, dict) and ch.get("gb-disclosure"):
                                dt = ch["gb-disclosure"]
                                disc_text = (
                                    dt if isinstance(dt, str) else dt.get("text")
                                )
                                disc_id = reg_disc(disc_text, key="trimprice")
                                if disc_id:
                                    disc_ids_local.append(disc_id)
                    disc_ids_local = list(dict.fromkeys(disc_ids_local))
                    tr = ensure_trim(name)
                    if "starting" in para:
                        prices = tr.setdefault("prices", [])
                        for r, vals in ri.items():
                            sp = self._normalize_price(
                                (vals or {}).get("startingPrice")
                            )
                            if not sp:
                                continue
                            prices.append(
                                {
                                    "region": r,
                                    "from_price": sp,
                                    "as_shown_price": None,
                                    "currency": self.DEFAULT_CURRENCY,
                                    "disclosure_ids": disc_ids_local,
                                    "source": "models",
                                }
                            )
                    if "as configured" in para or "as shown" in para:
                        prices = tr.setdefault("prices", [])
                        for r, vals in ri.items():
                            ap = self._normalize_price((vals or {}).get("asShownPrice"))
                            if not ap:
                                continue
                            match = next(
                                (p for p in prices if p.get("region") == r), None
                            )
                            if match:
                                match["as_shown_price"] = ap
                                match["disclosure_ids"] = list(
                                    dict.fromkeys(
                                        (match.get("disclosure_ids") or [])
                                        + disc_ids_local
                                    )
                                )
                            else:
                                prices.append(
                                    {
                                        "region": r,
                                        "from_price": None,
                                        "as_shown_price": ap,
                                        "currency": self.DEFAULT_CURRENCY,
                                        "disclosure_ids": disc_ids_local,
                                        "source": "models",
                                    }
                                )

        current_trim = None
        pending_tagline: Optional[str] = None
        in_trim_block = False
        slider = self._find_models_slider(item)
        for node in self._iter_nodes(slider):
            if isinstance(node, dict) and node.get("type") == "image":
                alt = node.get("alt") or ""
                nm = detect_from_text(alt)
                if nm:
                    current_trim = nm
                    pending_tagline = None
                    in_trim_block = True
                    ensure_trim(nm)
                    continue
            if isinstance(node, dict) and node.get("gb-dynamic-text"):
                gbd = node["gb-dynamic-text"]
                text_nodes = (gbd or {}).get("content") or []
                if (
                    text_nodes
                    and isinstance(text_nodes[0], dict)
                    and text_nodes[0].get("p")
                ):
                    nm = canon_name(text_nodes[0].get("p") or "")
                    if nm:
                        current_trim = nm
                        pending_tagline = None
                        in_trim_block = True
                        ensure_trim(nm)
                        continue
                    ptext = (text_nodes[0].get("p") or "").strip()
                    if (
                        in_trim_block
                        and current_trim
                        and ptext
                        and ":" not in ptext.lower()
                    ):
                        pending_tagline = ptext
                        tr = ensure_trim(current_trim)
                        if "tagline" not in tr:
                            tr["tagline"] = pending_tagline
                if in_trim_block and current_trim:
                    for t in text_nodes:
                        if isinstance(t, dict) and isinstance(t.get("ul"), list):
                            items = flatten_ul_items(t["ul"])  # type: ignore[index]
                            if items:
                                tr = ensure_trim(current_trim)
                                existing = tr.setdefault("features", [])
                                existing.extend(x for x in items if x not in existing)
                                in_trim_block = False
                                current_trim = None
                                break

        out: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        for t in trims:
            nt = by_name.get(t["name"].lower()) or t  # type: ignore[index]
            out.append(nt)
            seen_ids.add(nt["id"])
        for key, t in by_name.items():  # type: ignore[name-defined]
            if t["id"] not in seen_ids:
                out.append(t)
        return out

    def _extract_related_models(
        self, item: Dict[str, Any], reg_disc
    ) -> List[Dict[str, Any]]:
        related: List[Dict[str, Any]] = []
        seen: set[str] = set()

        def parse_prices(gbd_nodes: List[Dict[str, Any]]):
            from_map: Dict[str, str] = {}
            shown_map: Dict[str, str] = {}
            disc_ids: List[str] = []
            for gbd in gbd_nodes:
                ri = (gbd or {}).get("regional_information") or {}
                text_nodes = (gbd or {}).get("content") or []
                for t in text_nodes:
                    if not isinstance(t, dict):
                        continue
                    for ch in t.get("content") or []:
                        if isinstance(ch, dict) and ch.get("gb-disclosure"):
                            dt = ch["gb-disclosure"]
                            disc_text = dt if isinstance(dt, str) else dt.get("text")
                            disc_id = reg_disc(disc_text, key="price")
                            if disc_id:
                                disc_ids.append(disc_id)
                p_texts = [
                    t.get("p") for t in text_nodes if isinstance(t, dict) and t.get("p")
                ]
                para = " ".join(p_texts).lower()
                if "from:" in para or "starting" in para:
                    for r, vals in ri.items():
                        sp = (vals or {}).get("startingPrice")
                        if sp:
                            from_map[r] = sp
                if "as shown" in para or "as configured" in para:
                    for r, vals in ri.items():
                        ap = (vals or {}).get("asShownPrice")
                        if ap:
                            shown_map[r] = ap
            return from_map, shown_map, list(dict.fromkeys(disc_ids))

        for node, _parent in self._iter_nodes_with_parent(item):
            if not (isinstance(node, dict) and node.get("type") == "a link"):
                continue
            href = node.get("href") or ""
            text = (node.get("text") or "").lower()
            has_price_markers = ("from:" in text and "as shown" in text) or any(
                isinstance(c, dict) and c.get("gb-dynamic-text")
                for c in (node.get("content") or [])
            )
            if not has_price_markers:
                continue

            content = node.get("content") or []
            headings = [
                c.get("heading")
                for c in content
                if isinstance(c, dict) and c.get("heading")
            ]
            name = None
            if headings:
                name = str(headings[0]).strip()
            slug = None
            try:
                if "/en/" in href:
                    slug = href.split("/en/", 1)[1].rstrip("/").split("/")[-1]
            except Exception:
                slug = None
            slug = slug or self._slug(name or href.rsplit("/", 1)[-1])
            rel_id = slug
            if not rel_id or rel_id in seen:
                continue

            gbd_nodes = [
                c.get("gb-dynamic-text")
                for c in content
                if isinstance(c, dict) and c.get("gb-dynamic-text")
            ]
            from_map, shown_map, disc_ids = parse_prices([g for g in gbd_nodes if g])
            prices = []
            for r in sorted(set(from_map.keys()) | set(shown_map.keys())):
                prices.append(
                    {
                        "region": r,
                        "from_price": self._normalize_price(from_map.get(r)),
                        "as_shown_price": self._normalize_price(shown_map.get(r)),
                        "currency": self.DEFAULT_CURRENCY,
                        "disclosure_ids": disc_ids,
                        "source": "navbar",
                    }
                )

            related.append(
                {
                    "id": rel_id,
                    "name": name or rel_id,
                    "canonical_url": href,
                    "prices": prices,
                }
            )
            seen.add(rel_id)

        return related

    def _collect_links(self, item: Dict[str, Any]) -> Dict[str, Any]:
        find_dealer_url: Optional[str] = None
        build_price_links: List[str] = []
        inventory_links: List[str] = []

        for node in self._iter_nodes(item):
            if not isinstance(node, dict) or node.get("type") != "a link":
                continue
            txt = (node.get("text") or "").strip().lower()
            href = node.get("href") or ""
            if not href:
                continue
            if "find a dealer" in txt and not find_dealer_url:
                find_dealer_url = href
            if "build" in txt and "price" in txt:
                build_price_links.append(href)
            if (
                "inventory" in txt or "view inventory" in txt
            ) or "SearchResults" in href:
                inventory_links.append(href)

        return {
            "find_dealer_url": find_dealer_url,
            "build_and_price_urls": list(dict.fromkeys(build_price_links)),
            "inventory_urls": list(dict.fromkeys(inventory_links)),
        }

    def _select_links_for_model(
        self,
        links: Dict[str, Any],
        model_id: str,
        model_name: Optional[str],
        base_url: Optional[str] = None,
    ) -> Dict[str, Dict[str, Optional[str]]]:
        slug = model_id
        build = None
        for u in links.get("build_and_price_urls", []):
            if slug in u:
                build = u
                break
        inv = None
        name = (model_name or slug) or ""
        base = name.lower()
        tokens = {base, base.replace(" ", "+"), base.replace(" ", "%20")}
        for u in links.get("inventory_urls", []):
            if "SearchResults" not in u:
                continue
            lu = u.lower()
            if (
                any(t in lu for t in tokens)
                or f"model={name.replace(' ', '+')}".lower() in lu
            ):
                inv = u
                break
        dealer = links.get("find_dealer_url")
        return {
            "build_and_price": {"url": build, "type": self._link_type(build, base_url)},
            "inventory": {"url": inv, "type": self._link_type(inv, base_url)},
            "find_dealer": {"url": dealer, "type": self._link_type(dealer, base_url)},
        }

    def _build_docs(self, norm: Dict[str, Any]) -> List[Dict[str, Any]]:
        model = norm["models"][0]
        model_id = model["id"]
        model_name = model["name"]
        year = model.get("year")
        canonical = model.get("canonical_url")
        locale = model.get("locale")
        model_asset_ids = model.get("asset_ids") or []

        disc_map = {d["id"]: d["text"] for d in norm.get("disclosures", [])}
        prices = norm.get("prices", [])
        sections = norm.get("sections", [])
        awards = norm.get("awards", [])

        regions = sorted({p["region"] for p in prices}) or ["ON"]

        docs: List[Dict[str, Any]] = []

        # Helper: basic cleaners/formatters for text/metadata
        def _dedupe_lines(text: str) -> str:
            seen = set()
            out: List[str] = []
            for ln in (text or "").split("\n"):
                t = ln.strip()
                if not t:
                    continue
                key = t
                if key in seen:
                    continue
                seen.add(key)
                out.append(t)
            return "\n".join(out)

        def _strip_asterisks(text: str) -> tuple[str, bool]:
            # Remove stray asterisks used as footnote markers
            had = False

            def repl(m):
                nonlocal had
                had = True
                return " "

            cleaned = re.sub(r"\s*\*+\s*", repl, text or "")
            # Also trim duplicated whitespace
            cleaned = re.sub(r"[ \t]+", " ", cleaned)
            return cleaned.strip(), had

        def _format_price_value(v: Optional[str]) -> str:
            if not v:
                return "n/a"
            s = str(v).strip()
            if s.lower() == "n/a":
                return s
            # Only add currency if looks numeric
            if re.search(r"\d", s):
                return f"CAD ${s}"
            return s

        def _convert_units(text: str) -> str:
            # Add kg for lb and vice versa when missing
            def lbs_to_kg(m: re.Match) -> str:
                num = m.group("num")
                unit = m.group("unit")
                try:
                    val = float(
                        num.replace(",", "").replace("\u202f", "").replace("\u00a0", "")
                    )
                except Exception:
                    return m.group(0)
                kg = val * 0.45359237
                kg_disp = f"{kg:,.0f}" if kg >= 100 else f"{kg:,.1f}"
                # Avoid double annotation if already has kg nearby
                tail = m.group(0)
                if re.search(r"\(.*kg.*\)", tail, re.I):
                    return tail
                return f"{num} {unit} ({kg_disp} kg)"

            def kg_to_lbs(m: re.Match) -> str:
                num = m.group("num")
                unit = m.group("unit")
                try:
                    val = float(
                        num.replace(",", "").replace("\u202f", "").replace("\u00a0", "")
                    )
                except Exception:
                    return m.group(0)
                lbs = val / 0.45359237
                lbs_disp = f"{lbs:,.0f}" if lbs >= 100 else f"{lbs:,.1f}"
                tail = m.group(0)
                if re.search(r"\(.*lb\.?s?.*\)", tail, re.I):
                    return tail
                return f"{num} {unit} ({lbs_disp} lb)"

            text = re.sub(
                r"(?P<num>\d{1,3}(?:[,\u00a0\u202f]\d{3})*(?:\.\d+)?)\s*(?P<unit>lb|lbs|pounds)\b",
                lbs_to_kg,
                text,
                flags=re.I,
            )
            text = re.sub(
                r"(?P<num>\d{1,3}(?:[,\u00a0\u202f]\d{3})*(?:\.\d+)?)\s*(?P<unit>kg|kilograms)\b",
                kg_to_lbs,
                text,
                flags=re.I,
            )
            return text

        def _clean_text(text: str, disclosure_ids: Optional[List[str]] = None) -> str:
            t0 = text or ""
            t1 = _dedupe_lines(t0)
            t2, had_star = _strip_asterisks(t1)
            t3 = _convert_units(t2)
            # Append a short cue for disclosures if present
            if (disclosure_ids or had_star) and "[See disclosures]" not in t3:
                t3 = f"{t3}\n\n[See disclosures]"
            return t3.strip()

        def _hash_text(text: str) -> str:
            return _hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:12]

        def _now_iso() -> str:
            return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

        # Overview
        overview_text = "\n".join(
            t for t in [model.get("title"), model.get("description")] if t
        )
        if overview_text:
            ov_text = _clean_text(overview_text)
            docs.append(
                {
                    "id": f"doc:{model_id}:overview",
                    "text": ov_text,
                    "metadata": {
                        "model_id": model_id,
                        "model_name": model_name,
                        "year": year,
                        "section_id": "sec:overview",
                        "section_title": "Overview",
                        "doc_type": "overview",
                        "locale": locale,
                        "asset_ids": model_asset_ids,
                        "last_scraped_at": _now_iso(),
                        "content_hash": _hash_text(ov_text),
                        "source_url": canonical,
                    },
                }
            )

        # Pricing per region
        prices_by_region: Dict[str, List[Dict[str, Any]]] = {}
        for p in prices:
            prices_by_region.setdefault(p["region"], []).append(p)
        for r in regions:
            plist = prices_by_region.get(r, [])
            if not plist:
                continue
            lines = []
            disc_ids: List[str] = []
            for p in plist:
                fp = p.get("from_price")
                ap = p.get("as_shown_price")
                if fp or ap:
                    lines.append(
                        f"Pricing — From: {_format_price_value(fp)}; As shown: {_format_price_value(ap)}."
                    )
                disc_ids.extend(p.get("disclosure_ids") or [])
            disc_ids = list(dict.fromkeys(disc_ids))
            # Add short cue instead of inlining disclosure text
            if disc_ids:
                lines.append("[See disclosures]")
            if lines:
                p_text = _clean_text("\n".join(lines), disc_ids)
                docs.append(
                    {
                        "id": f"doc:{model_id}:pricing:{r}",
                        "text": p_text,
                        "metadata": {
                            "model_id": model_id,
                            "model_name": model_name,
                            "year": year,
                            "section_id": "sec:pricing",
                            "section_title": "Pricing",
                            "region": r,
                            "doc_type": "pricing",
                            "locale": locale,
                            "asset_ids": model_asset_ids,
                            "price_ids": [p["id"] for p in plist],
                            "disclosure_ids": disc_ids,
                            "last_scraped_at": _now_iso(),
                            "content_hash": _hash_text(p_text),
                            "source_url": canonical,
                        },
                    }
                )

        # Sections (region-agnostic; avoid multiplying by region)
        for s in sections:
            base_text = f"{s.get('title') or ''}\n{s.get('body') or ''}".strip()
            dis_ids = s.get("disclosure_ids") or []
            # Clean and normalize text; use short disclosure cue
            base_text = _clean_text(base_text, dis_ids)
            sec_id = s.get("id")
            sec_title = s.get("title")
            # Detect trim-limited mentions and attach trim_id(s)
            trim_matches: List[str] = []
            if self.TRIM_NAMES:
                low = base_text.lower()
                for nm in sorted(self.TRIM_NAMES, key=lambda x: -len(x)):
                    patt = re.compile(r"\b(" + re.escape(nm.lower()) + r")\b")
                    if (
                        re.search(r"available on\s+" + patt.pattern, low)
                        or re.search(r"only on\s+" + patt.pattern, low)
                        or re.search(r"standard on\s+" + patt.pattern, low)
                    ):
                        trim_matches.append(nm)

            # Chunk long sections into 200–350 token pieces
            def chunk_text(
                text: str, target_tokens: int = 280, overlap: int = 40
            ) -> List[str]:
                parts = [t.strip() for t in text.split("\n") if t.strip()]
                chunks: List[str] = []
                cur: List[str] = []
                cur_tokens = 0

                def token_count(s: str) -> int:
                    return max(1, len(s.split()))

                for p in parts:
                    t = token_count(p)
                    if cur_tokens + t > target_tokens and cur:
                        chunks.append("\n".join(cur).strip())
                        # start new chunk with overlap from end of previous
                        if overlap and chunks[-1]:
                            tail_tokens = 0
                            tail: List[str] = []
                            for ln in reversed(chunks[-1].split("\n")):
                                tail_tokens += token_count(ln)
                                tail.insert(0, ln)
                                if tail_tokens >= overlap:
                                    break
                            cur = tail + [p]
                            cur_tokens = token_count(" ".join(tail)) + t
                        else:
                            cur = [p]
                            cur_tokens = t
                    else:
                        cur.append(p)
                        cur_tokens += t
                if cur:
                    chunks.append("\n".join(cur).strip())
                # Further split if any chunk is > 350 tokens by naive word count
                out: List[str] = []
                for ch in chunks:
                    if len(ch.split()) > 350:
                        words = ch.split()
                        for i in range(0, len(words), 300):
                            out.append(" ".join(words[i : i + 320]))
                    else:
                        out.append(ch)
                return out

            sec_slug = sec_id.split(":", 1)[1] if isinstance(sec_id, str) else "section"
            section_chunks = chunk_text(base_text)
            for idx, chunk in enumerate(section_chunks, start=1):
                c_hash = _hash_text(chunk)
                meta = {
                    "model_id": model_id,
                    "model_name": model_name,
                    "year": year,
                    "section_id": sec_id,
                    "section_title": sec_title,
                    "region": None,
                    "doc_type": "feature",
                    "locale": locale,
                    "asset_ids": model_asset_ids,
                    "disclosure_ids": dis_ids,
                    "last_scraped_at": _now_iso(),
                    "content_hash": c_hash,
                    "source_url": s.get("source_url") or canonical,
                }
                if trim_matches:
                    ids = [f"{model_id}:{self._slug(n)}" for n in trim_matches]
                    meta["trim_id"] = ids[0]
                    meta["trim_ids"] = ids
                docs.append(
                    {
                        "id": f"doc:{model_id}:{sec_slug}:ch{idx}",
                        "text": chunk,
                        "metadata": meta,
                    }
                )

        for a in awards:
            a_text = f"{a.get('title') or ''}\n{a.get('summary') or ''}".strip()
            dis_ids = a.get("disclosure_ids") or []
            a_text = _clean_text(a_text, dis_ids)
            a_hash = _hash_text(a_text)
            docs.append(
                {
                    "id": f"doc:{model_id}:{a['id'].split(':',1)[1]}",
                    "text": a_text,
                    "metadata": {
                        "model_id": model_id,
                        "model_name": model_name,
                        "year": year,
                        "section_id": a.get("id"),
                        "section_title": "Awards",
                        "region": None,
                        "doc_type": "award",
                        "locale": locale,
                        "asset_ids": model_asset_ids,
                        "disclosure_ids": dis_ids,
                        "last_scraped_at": _now_iso(),
                        "content_hash": a_hash,
                        "source_url": a.get("source_url") or canonical,
                    },
                }
            )

        return docs

    def _iter_nodes(self, obj: Any) -> Iterator[Any]:
        if isinstance(obj, dict):
            yield obj
            for v in obj.values():
                yield from self._iter_nodes(v)
        elif isinstance(obj, list):
            for el in obj:
                yield from self._iter_nodes(el)

    def _iter_nodes_with_parent(
        self, obj: Any, parent: Any = None
    ) -> Iterator[tuple[Any, Any]]:
        if isinstance(obj, dict):
            yield obj, parent
            for v in obj.values():
                yield from self._iter_nodes_with_parent(v, obj)
        elif isinstance(obj, list):
            for el in obj:
                yield from self._iter_nodes_with_parent(el, obj)

    @staticmethod
    def _slug(s: str) -> str:
        s = (s or "").strip().lower()
        s = re.sub(r"[^a-z0-9]+", "-", s)
        s = re.sub(r"-+", "-", s).strip("-")
        return s or "item"

    @staticmethod
    def _short_hash(s: str, n: int = 10) -> str:
        import hashlib as _h

        return _h.sha1((s or "").encode("utf-8")).hexdigest()[:n]

    @staticmethod
    def _normalize_price(value: Any) -> Optional[str]:
        if value is None:
            return None
        s = str(value)
        if not s:
            return None
        # strip currency symbol and common spacing
        s = s.replace("$", "")
        # Remove common NBSPs without touching commas/periods
        for sp in ("\u00a0", "\u202f", "\u2007"):
            s = s.replace(sp, "")
        return s.strip()

    @staticmethod
    def _link_type(url: Optional[str], base_url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        try:
            u = urlparse(url)
            if not u.netloc:
                return "internal"  # relative link
            if not base_url:
                # Heuristic: treat GM brand domains as internal if host contains known brands
                host = u.hostname or ""
                return (
                    "internal"
                    if any(
                        b.lower() in host.lower()
                        for b in ["chevrolet", "gmc", "buick", "cadillac", "gm."]
                    )
                    else "external"
                )
            b = urlparse(base_url)
            host = (u.hostname or "").lower()
            bhost = (b.hostname or "").lower()
            if host == bhost or host.endswith("." + bhost.split(":")[0].lstrip(".")):
                return "internal"
            # consider same registrable domain as internal (e.g., subdomains)
            if bhost and bhost.split(".")[-2:] == host.split(".")[-2:]:
                return "internal"
            return "external"
        except Exception:
            return None

    def normalize_all(self, data: Any) -> Dict[str, List[Dict[str, Any]]]:
        """Normalize items into a consolidated, de-duplicated graph by id."""
        buckets: Dict[str, Dict[str, Dict[str, Any]]] = {
            "models": {},
            "prices": {},
            "disclosures": {},
            "assets": {},
            "sections": {},
            "trims": {},
            "related_models": {},
            "awards": {},
        }

        def _merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
            out = dict(a)
            for k, v in b.items():
                if k not in out or out[k] in (None, "", [], {}):
                    out[k] = v
                elif isinstance(v, list) and isinstance(out.get(k), list):
                    out[k] = list(dict.fromkeys([*out[k], *v]))
                elif k == "body":
                    out[k] = max(str(out[k] or ""), str(v or ""), key=len)
            return out

        items: List[Dict[str, Any]]
        if isinstance(data, list):
            items = [d for d in data if isinstance(d, dict)]
        elif isinstance(data, dict):
            items = [data]
        else:
            items = []

        for it in items:
            g = self._normalize_item(it)
            for key in buckets:
                for obj in g.get(key, []) or []:
                    oid = obj.get("id")
                    if not oid:
                        continue
                    if oid in buckets[key]:
                        buckets[key][oid] = _merge(buckets[key][oid], obj)
                    else:
                        buckets[key][oid] = obj

        return {k: list(v.values()) for k, v in buckets.items()}
