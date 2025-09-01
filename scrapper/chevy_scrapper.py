import os
from urllib.parse import urljoin

from scrapper.scrapper import Scrapper


class ChevyScapper(Scrapper):
    @property
    def spider_name(self) -> str:
        # Ensure full name in both modes
        return "chevy_spider" + ("_DEV" if self.DEV_MODE else "_PROD")

    @property
    def local_url(self) -> str:
        # Use a properly formatted local file path
        # Get the absolute path to the samples directory
        samples_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples"
        )
        return os.path.join(samples_dir, "silverado1500.html")

    @property
    def prod_url(self) -> str:
        return self.chevy_website + "/en/trucks/silverado-1500"

    def parse(self, response):
        self.logger.info(f"DEV_MODE: {self.DEV_MODE}")
        self.logger.info(f"Processing {response.url} in ChevyScapper")
        self.logger.info(
            f"Local URL: {self.local_url}"
            if self.DEV_MODE
            else f"Prod URL: {self.prod_url}"
        )

        if self.save_html and not self.DEV_MODE:
            self.save_response_html(response, self.prod_url)

        if not self.DEV_MODE and "playwright_page" in response.meta:
            page = response.meta["playwright_page"]
            page.close()

        metadata = self.extract_metadata(response)
        navbar = self.parse_content(
            response, "//gb-global-nav/template[@id='gb-global-nav-content']", "navbar"
        )
        body_content = self.parse_content(
            response, "//main[@id='gb-main-content']", "body"
        )
        footer = self.parse_content(response, "//gb-global-footer", "footer")

        yield {
            "url": response.url,
            "metadata": metadata,
            "navbar": navbar,
            "main_body_content": body_content,
            "footer": footer,
        }

    def parse_content(self, response, parent_search, parent_name):
        try:
            root = response.xpath(parent_search)
            if root:
                # Build tree while flattening any list returned by dfs
                tree = []
                for ch in root[0].xpath("./*"):
                    self._append(tree, self.dfs(ch, self.chevy_website))
                return tree
            else:
                return {
                    parent_name: f"Unable to parse {parent_name} content by {self.spider_name}"
                }
        except Exception as e:
            self.logger.error(f"Error parsing {parent_name}: {str(e)}")
            return {
                "error": f"{parent_name} parsing failed: {str(e)}",
                "status": "error",
            }

    # EXCLUDE tags are flattened: only their children are traversed.
    # Note: The following broad tags are intentionally excluded to reduce
    # structural noise: 'div', 'nav', 'section', 'article'. If richer
    # structure is needed later, consider moving them to WRAPPERS instead.
    EXCLUDE = {
        "script",
        "style",
        "noscript",
        "template",
        "gb-adv-grid",
        "gb-wrapper",
        "gb-responsive-image",
        "adv-col",  # adds a column; keep only grid content
        "gb-tab-nav",  # wraps an unordered list; structural only
        "section",
        "nav",
        "article",
        # "adv-grid",
        "br",
        "gb-sub-flyout",
        "gb-sublinks",
        "gb-main-flyout",
        "div",
        # "span",
        "gb-flyout",
    }

    WRAPPERS = {
        "header",
        "gb-secondary-nav",
        "main",
        "footer",
        "aside",
        "picture",
        "gb-dynamic-text",
        "adv-grid",
    }

    def own_text(self, el):
        # Include direct text plus descendant span text, but exclude other tags.
        parts = [t.strip() for t in el.xpath("./text() | .//span//text()").getall()]
        text = " ".join(p for p in parts if p)
        return " ".join(text.split()) if text else ""

    def all_text(self, el):
        return " ".join(" ".join(el.css("::text").getall()).split())

    def _append(self, kids, node):
        if node is None:
            return
        if isinstance(node, list):
            kids.extend(node)
        else:
            kids.append(node)

    def is_internal_link(self, u: str | None, base: str) -> bool:
        if not u:
            return False
        u = u.strip().split()[0]
        return u.startswith("/") or u.startswith(base)

    def _norm_url(self, base, u):
        if not u:
            return None

        return urljoin(base, u.strip().split()[0])

    def parse_json(self, raw):
        import html
        import json

        del_json = ["asShownPriceDisclosure", "startingPriceDisclosure"]
        if not raw:
            return None
        s = html.unescape(raw).replace("\\/", "/")
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            try:
                data = json.loads(s.replace("\u00a0", " ").replace("\xa0", " "))
            except json.JSONDecodeError:
                return s

        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, dict):
                    for dk in del_json:
                        value.pop(dk, None)

        return data

    def serialize_span(self, el, _base, _child):
        # Merge span text into parent by not emitting a standalone node.
        # Parent serializers (like p) and serialize_generic can include span text via own_text.
        return None

    def serialize_gb_region_selector(self, el, _base, children):
        attrs = {k: self.parse_json(v) for k, v in el.attrib.items()}
        out = {"gb-region-selector": attrs}
        if children:
            out["gb-region-selector"]["content"] = children
        return out

    def serialize_a(self, el, base, children):
        href = el.attrib.get("href")
        return (
            {
                "type": "a link",
                "text": self.all_text(el),
                "href": self._norm_url(base, href),
                "link_type": (
                    "internal" if self.is_internal_link(href, base) else "external"
                )
                if href
                else None,
                "target": el.attrib.get("target"),
                **({"content": children} if children else {}),
            }
            if href
            else None
        )

    def serialize_button_like(self, el, base, children):
        act = el.attrib.get("href") or el.attrib.get("formaction")
        return (
            {
                "type": "button",
                "text": self.all_text(el),
                "url": self._norm_url(base, act),
                "link_type": (
                    "internal" if self.is_internal_link(act, base) else "external"
                )
                if act
                else None,
                # "classname": el.attrib.get("class", ""),
                "content": children or None,
                **({k: el.attrib[k] for k in el.attrib if k.startswith("data-")}),
                **(
                    {
                        k: el.attrib[k]
                        for k in ("title", "aria-haspopup", "aria-expanded")
                        if k in el.attrib
                    }
                ),
            }
            if act
            else None
        )

    def serialize_img(self, el, base, _children):
        src = el.attrib.get("src")
        return {
            "type": "image",
            "src": self._norm_url(base, src),
            "alt": el.attrib.get("alt"),
            "title": el.attrib.get("title"),
            "link_type": (
                "internal" if self.is_internal_link(src, base) else "external"
            )
            if src
            else None,
            "loading": el.attrib.get("loading"),
            **({k: el.attrib[k] for k in el.attrib if k.startswith("data-")}),
        }

    def serialize_source(self, el, base, _children):
        srcset = (el.attrib.get("srcset") or "").replace("\n", " ")
        urls = []
        for part in srcset.split(","):
            tok = part.strip().split()
            if tok:
                urls.append(self._norm_url(base, tok[0]))
        return {
            "source": {
                "media": el.attrib.get("media"),
                "height": el.attrib.get("height"),
                "width": el.attrib.get("width"),
                "srcset": [u for u in urls if u],
                "data_aspectratio": el.attrib.get("data-aspectratio"),
            }
        }

    def serialize_heading(self, el, _base, _children):
        return {"heading": self.all_text(el)}

    def serialize_gb_dynamic_text(self, el, _base, children):
        return {
            "gb-dynamic-text": {
                "country": el.attrib.get("country"),
                "regional_information": self.parse_json(
                    el.attrib.get("regional-information-json")
                ),
                **({"content": children} if children else {}),
            }
        }

    def serialize_myaccount_flyout(self, el, base, children):
        def _parse(attr):
            return self.parse_json(el.attrib.get(attr))

        return {
            "gb-myaccount-flyout": {
                "flyoutstate": el.attrib.get("flyoutstate"),
                "auth_flyout": _parse("authflyoutdata"),
                "auth_links": _parse("authlinkdata"),
                "fallback": _parse("fallbackdata"),
                "content": children or None,
            }
        }

    def _attrs_copy(self, el):
        return dict(el.attrib) if el.attrib else {}

    def _serialize_list(self, kind, el, base, children):
        # keep only LI entries; flatten to a list of strings
        texts = []
        for ch in children or []:
            if isinstance(ch, dict) and "item" in ch:
                val = ch["item"]
                if isinstance(val, str) and val:
                    texts.append(val)
                elif isinstance(val, dict):
                    t = val.get("text", "")
                    if t:
                        texts.append(t)

        return {kind: texts}

    def serialize_ul(self, el, base, children):
        return self._serialize_list("ul", el, base, children)

    def serialize_ol(self, el, base, children):
        return self._serialize_list("ol", el, base, children)

    def serialize_li(self, el, _base, _children):
        txt = self.all_text(el).strip()
        if not txt:
            return None
        return {"item": txt}

    def serialize_p(self, el, base, children):
        attrs = self._attrs_copy(el) if el.attrib else {}
        cls = attrs.pop("class", None)
        txt = self.all_text(el)

        # 'br' nodes are already excluded in DFS; no need to filter here
        clean_children = []
        for ch in children or []:
            self._append(clean_children, ch)

        if not txt and not clean_children and not cls and not attrs:
            return None

        if clean_children:
            return {"p": txt or None, "content": clean_children}
        return {"p": txt} if txt else None

    def _qualname(self, attr, el):
        if attr.startswith("{"):
            uri, local = attr[1:].split("}")
            for pref, u in (el.nsmap or {}).items():
                if u == uri:
                    return f"{pref}:{local}" if pref else local
            return local
        return attr

    def _serialize_path_flat(self, el):
        pa = dict(el.attrib) if el.attrib else {}
        out = {}
        d = pa.pop("d", None)
        if d is not None:
            out["d"] = "".join(
                el for el in "".join(e for e in d.split("\n")).split("\t")
            )
        for k, v in pa.items():
            out[self._qualname(k, el)] = v
        return out

    def serialize_path(self, el, _base, _children):
        return {"path": self._serialize_path_flat(el)}

    def serialize_svg(self, el, _base, children):
        attrs = dict(el.attrib) if el.attrib else {}
        nsmap = getattr(el.root, "nsmap", None)
        if nsmap:
            for pref, uri in nsmap.items():
                key = f"xmlns:{pref}" if pref else "xmlns"
                attrs.setdefault(key, uri)

        path_elems = el.xpath(".//*[local-name()='path']")
        paths = [self._serialize_path_flat(p) for p in path_elems]

        filtered_children = []
        for ch in children or []:
            if isinstance(ch, dict) and (
                "path" in ch or ch.get("tag", "").endswith("path")
            ):
                continue
            filtered_children.append(ch)

        return {
            "svg": {
                "attrs": attrs,
                "paths": paths,
                **({"content": filtered_children} if filtered_children else {}),
            }
        }

    def serialize_disclosure(self, el, _base, _children):
        # Capture disclosure marker and reference to disclosure content if present
        return {
            "gb-disclosure": {
                "text": self.all_text(el) or self.own_text(el) or None,
                "disclosure_id": el.attrib.get("data-disclosure-id"),
                "role": el.attrib.get("role"),
            }
        }

    def serialize_table(self, el, _base, _children):
        # Convert tables into a simple list of row arrays for embedding
        rows = []
        for tr in el.xpath(".//tr"):
            cells = tr.xpath("./th | ./td")
            row = [self.all_text(c) for c in cells]
            if any(cell for cell in row):
                rows.append(row)
        return {"table": {"rows": rows}}

    def get_native(self):
        # Lazily cache the serializer map to avoid rebuilding it on every DFS call
        if not hasattr(self, "_native_serializers"):
            self._native_serializers = {
                "a": self.serialize_a,
                "button": self.serialize_button_like,
                "input": self.serialize_button_like,
                "img": self.serialize_img,
                "source": self.serialize_source,
                "table": self.serialize_table,
                "gb-dynamic-text": self.serialize_gb_dynamic_text,
                "h1": self.serialize_heading,
                "h2": self.serialize_heading,
                "h3": self.serialize_heading,
                "h4": self.serialize_heading,
                "h5": self.serialize_heading,
                "h6": self.serialize_heading,
                "ul": self.serialize_ul,
                "ol": self.serialize_ol,
                "li": self.serialize_li,
                "p": self.serialize_p,
                "gb-myaccount-flyout": self.serialize_myaccount_flyout,
                "gb-disclosure": self.serialize_disclosure,
                "span": self.serialize_span,
                "svg": self.serialize_svg,
                "path": self.serialize_path,
                "gb-region-selector": self.serialize_gb_region_selector,
            }
        return self._native_serializers

    def serialize_generic(self, el, children):
        node = {"tag": el.root.tag.lower()}
        txt = self.own_text(el)
        if txt:
            node["text"] = txt
        if children:
            node["content"] = children
        return node

    def dfs(self, el, base):
        tag = el.root.tag.lower()
        NATIVE = self.get_native()

        if tag in self.EXCLUDE:
            kids = []
            for ch in el.xpath("./*"):
                self._append(kids, self.dfs(ch, base))
            return kids or None

        children = []
        for ch in el.xpath("./*"):
            self._append(children, self.dfs(ch, base))

        if tag in NATIVE:
            if tag == "input" and el.attrib.get("type") not in {
                "button",
                "submit",
                "reset",
            }:
                pass
            else:
                try:
                    return NATIVE[tag](el, base, children)
                except Exception:
                    return self.serialize_generic(el, children)

        if tag in self.WRAPPERS and tag not in NATIVE:
            cls = el.attrib.get("class", "").strip()
            # Preserve all children for wrapper elements to avoid data loss
            if not cls and not self.own_text(el) and len(children) >= 1:
                return children

        return self.serialize_generic(el, children)
