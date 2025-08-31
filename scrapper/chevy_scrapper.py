import os
from urllib.parse import urljoin

from scrapper.scrapper import Scrapper


class ChevyScapper(Scrapper):
    @property
    def spider_name(self) -> str:
        return "chevy_spider" + "_DEV" if self.DEV_MODE else "_PROD"

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
        self.logger.info(f"Local URL: {self.local_url}")
        self.logger.info(f"Prod URL: {self.prod_url}")

        # Save HTML content if save_html is True and we're in production mode
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
                self.chevy_website
                tree = [
                    n
                    for n in (
                        self.dfs(ch, self.chevy_website) for ch in root[0].xpath("./*")
                    )
                    if n is not None
                ]
                if parent_name == "body":
                    return self.build_heading_outline(tree)
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

    EXCLUDE = {
        "script",
        "style",
        "noscript",
        "template",
        "gb-adv-grid",
        "gb-wrapper",
        "gb-responsive-image",
        "adv-col",
        "gb-tab-nav",  # usually just adds nodes in tree, wraps an unordered list
        "gb-adv-grid",
        "adv-col",  # adds a column, we just need the main grid
        "section",
        "nav",
        "article",
        # "adv-grid",
        "br",
        "gb-sub-flyout",
        "gb-sublinks",
        "gb-main-flyout",
        "div",
        "gb-flyout",
    }

    # Inline elements that can be merged into parent when they
    # carry no semantic weight (i.e., are purely stylistic wrappers)
    INLINE_MERGE = {
        "span",
        "em",
        "strong",
        "b",
        "i",
        "u",
        "small",
        "sup",
        "sub",
        "mark",
        "abbr",
        "code",
        "kbd",
        "samp",
        "var",
        "wbr",
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
        parts = [t.strip() for t in el.xpath("./text()").getall()]
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

    def _has_semantic_weight(self, el) -> bool:
        # Treat inline nodes as structural only if they carry meaningful attributes.
        if not el.attrib:
            return False
        for k in el.attrib.keys():
            if k in (
                "id",
                "role",
                "aria-label",
                "aria-labelledby",
                "aria-describedby",
                "itemprop",
            ):
                return True
            if k.startswith("data-"):
                return True
        return False

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
        return self.all_text(el)

    # -------- serializers  --------
    #

    def serialize_gb_region_selector(self, el, _base, children):
        attrs = {k: self.parse_json(v) for k, v in el.attrib.items()}
        out = {"gb-region-selector": attrs}
        if children:
            out["gb-region-selector"]["content"] = children
        return out

    def serialize_a(self, el, base, children):
        href = el.attrib.get("href")

        return {
            "a": {
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
        }

    def serialize_button_like(self, el, base, children):
        act = el.attrib.get("href") or el.attrib.get("formaction")
        return (
            {
                "button": {
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
            }
            if act
            else None
        )

    def serialize_img(self, el, base, _children):
        src = el.attrib.get("src")
        return {
            "img": {
                "src": self._norm_url(base, src),
                "alt": el.attrib.get("alt"),
                "title": el.attrib.get("title"),
                "link_type": (
                    "internal" if self.is_internal_link(src, base) else "external"
                )
                if src
                else None,
                **(
                    {"loading": el.attrib.get("loading")}
                    if "loading" in el.attrib
                    else {}
                ),
                **({k: el.attrib[k] for k in el.attrib if k.startswith("data-")}),
            }
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
        tag = (el.root.tag or "").lower()
        lvl = None
        if tag.startswith("h") and len(tag) > 1 and tag[1].isdigit():
            try:
                lvl = int(tag[1])
            except Exception:
                lvl = None
        return {f"heading_{lvl}": self.all_text(el)}

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

    # def _serialize_list(self, kind, el, base, children):
    #     texts = []
    #     for ch in children or []:
    #         if isinstance(ch, dict) and "item" in ch:
    #             val = ch["item"]
    #             if isinstance(val, str) and val:
    #                 texts.append(val)
    #             elif isinstance(val, dict):
    #                 t = val.get("text", "")
    #                 if t:
    #                     texts.append(t)

    # return {kind: texts}

    # def serialize_ul(self, el, base, children):
    #     return self._serialize_list("ul", el, base, children)

    # def serialize_ol(self, el, base, children):
    #     return self._serialize_list("ol", el, base, children)

    def serialize_p(self, el, base, children):
        attrs = self._attrs_copy(el) if el.attrib else {}
        cls = attrs.pop("class", None)
        txt = self.all_text(el)

        clean_children = []
        for ch in children or []:
            if isinstance(ch, dict) and ch.get("tag") == "br":
                continue
            self._append(clean_children, ch)

        if not txt and not clean_children and not cls and not attrs:
            return None

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
                el for el in "".join(e for e in d.split("\t")).split("\n")
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
        pass

    def get_native(self):
        return {
            "a": self.serialize_a,
            "button": self.serialize_button_like,
            "input": self.serialize_button_like,
            "img": self.serialize_img,
            "source": self.serialize_source,
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

    def serialize_generic(self, el, children):
        node = {"tag": el.root.tag.lower()}
        txt = self.own_text(el)
        if txt:
            node["text"] = txt
        if children:
            node["content"] = children
        return node

    # -------- heading-based outline helpers --------
    def _node_children(self, node):
        if isinstance(node, list):
            return node
        if not isinstance(node, dict):
            return None
        ch = node.get("content")
        if isinstance(ch, list):
            return ch
        for v in node.values():
            if isinstance(v, dict):
                c = v.get("content")
                if isinstance(c, list):
                    return c
        return None

    def _node_is_heading(self, node) -> bool:
        return isinstance(node, dict) and "heading" in node

    def _extract_heading_info(self, node):
        if not self._node_is_heading(node):
            return None, None
        h = node.get("heading")
        if isinstance(h, dict):
            return h.get("level"), h.get("text")
        return None, h

    def _contains_heading(self, node) -> bool:
        if self._node_is_heading(node):
            return True
        ch = self._node_children(node)
        if not ch:
            return False
        for c in ch:
            if self._contains_heading(c):
                return True
        return False

    def _flatten_for_outline(self, node, out_tokens):
        if node is None:
            return
        if isinstance(node, list):
            for it in node:
                self._flatten_for_outline(it, out_tokens)
            return
        if not isinstance(node, dict):
            return

        if self._node_is_heading(node):
            lvl, txt = self._extract_heading_info(node)
            if (txt or "").strip():
                out_tokens.append(
                    {"type": "heading", "level": lvl, "text": txt.strip()}
                )
            return

        if self._contains_heading(node):
            ch = self._node_children(node)
            if ch:
                for it in ch:
                    self._flatten_for_outline(it, out_tokens)
            return

        out_tokens.append({"type": "content", "node": node})

    def _merge_consecutive_headings(self, tokens):
        merged = []
        pending = None
        for t in tokens:
            if t.get("type") == "heading":
                if pending is None:
                    pending = dict(t)
                else:
                    if pending.get("level") == t.get("level"):
                        ptxt = (pending.get("text") or "").strip()
                        ttxt = (t.get("text") or "").strip()
                        pending["text"] = (ptxt + " " + ttxt).strip()
                    else:
                        merged.append(pending)
                        pending = dict(t)
            else:
                if pending is not None:
                    merged.append(pending)
                    pending = None
                merged.append(t)
        if pending is not None:
            merged.append(pending)
        return merged

    def build_heading_outline(self, nodes):
        tokens = []
        self._flatten_for_outline(nodes, tokens)
        tokens = self._merge_consecutive_headings(tokens)

        top_sections = []
        preamble = []
        stack = []

        def new_section(level, text):
            return {"heading": text, "level": level, "content": [], "sections": []}

        for t in tokens:
            if t["type"] == "heading":
                lvl = t.get("level") or 1
                txt = t.get("text") or ""
                while stack and stack[-1]["level"] >= lvl:
                    stack.pop()
                sec = new_section(lvl, txt)
                if stack:
                    stack[-1]["sections"].append(sec)
                else:
                    top_sections.append(sec)
                stack.append(sec)
            else:
                node = t.get("node")
                if stack:
                    stack[-1]["content"].append(node)
                else:
                    preamble.append(node)

        if preamble:
            top_sections.insert(
                0, {"heading": None, "level": 0, "content": preamble, "sections": []}
            )

        return top_sections

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

        # Inline-leaf collapsing: bubble inline containers (like <span>) into the parent,
        # unless they carry meaningful attributes or have a native serializer.
        if (
            tag in self.INLINE_MERGE
            and tag not in NATIVE
            and not self._has_semantic_weight(el)
        ):
            return children or None

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
            if not cls and not self.own_text(el):
                return children or None

        return self.serialize_generic(el, children)
