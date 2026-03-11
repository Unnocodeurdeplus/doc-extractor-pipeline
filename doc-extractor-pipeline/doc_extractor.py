"""
title: Doc Extractor
author: OpenWebUI
version: 2.0
description: Extract documentation URLs to Markdown with full site crawling, interactive config, and ZIP export
"""

from typing import List, Union, Generator, Iterator, Optional, Set, Dict
from urllib.parse import urlparse, urljoin, urlunparse
from datetime import datetime
from collections import deque
import re
import time
import os
import zipfile
import io
import json

import httpx
from bs4 import BeautifulSoup
import trafilatura
from pydantic import BaseModel


class CrawlConfig:
    """Configuration for crawl session."""
    def __init__(self):
        self.max_pages: int = 50
        self.delay_seconds: float = 1.0
        self.include_pattern: str = ""
        self.exclude_pattern: str = ""
        self.keep_history: bool = True
        self.max_depth: int = 0  # 0 = unlimited


class Pipe:
    class Valves(BaseModel):
        REQUEST_TIMEOUT: int = 10
        USER_AGENT: str = "DocExtractor/2.0 (OpenWebUI)"
        INCLUDE_COMMENTS: bool = False
        
        CRAWL_ENABLED: bool = False
        MAX_PAGES: int = 50
        DELAY_SECONDS: float = 1.0
        INCLUDE_PATTERN: str = ""
        EXCLUDE_PATTERN: str = ""
        KEEP_HISTORY: bool = True

    def __init__(self):
        self.type = "pipe"
        self.id = "doc-extractor"
        self.name = "Doc Extractor/"
        self.valves = self.Valves()
        self.crawl_config = CrawlConfig()

    def validate_url(self, url: str) -> tuple[bool, Optional[str]]:
        """Validate that the input is a valid HTTP/HTTPS URL."""
        try:
            parsed = urlparse(url)
            if not parsed.scheme:
                return False, "URL must start with http:// or https://"
            if parsed.scheme not in ("http", "https"):
                return False, "Only HTTP and HTTPS protocols are supported"
            if not parsed.netloc:
                return False, "Invalid URL format - no domain found"
            return True, None
        except Exception as e:
            return False, f"Invalid URL: {str(e)}"

    def fetch_page(self, url: str) -> tuple[bool, Optional[str], Optional[dict]]:
        """Fetch the HTML content from the URL."""
        headers = {
            "User-Agent": self.valves.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        try:
            with httpx.Client(timeout=self.valves.REQUEST_TIMEOUT, verify=False, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, "lxml")

                title = soup.find("title")
                title = title.get_text(strip=True) if title else "Untitled"

                og_title = soup.find("meta", property="og:title")
                if og_title and og_title.get("content"):
                    title = og_title["content"]

                h1 = soup.find("h1")
                if h1:
                    title = h1.get_text(strip=True)

                title = re.sub(r'\s*#+\s*$', '', title)

                metadata = {
                    "title": title,
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "fetched_at": datetime.now().isoformat(),
                }

                return True, response.text, metadata

        except httpx.TimeoutException:
            return False, None, {"error": "Request timed out. The site may be slow or unreachable."}
        except httpx.HTTPStatusError as e:
            return False, None, {"error": f"HTTP {e.response.status_code}: {e.response.reason_phrase}"}
        except httpx.RequestError as e:
            return False, None, {"error": f"Connection error: {str(e)}"}
        except Exception as e:
            return False, None, {"error": f"Unexpected error: {str(e)}"}

    def extract_structure(self, html: str) -> List[tuple[int, str]]:
        """Extract heading hierarchy (H1-H4) from HTML."""
        soup = BeautifulSoup(html, "lxml")
        headings = []

        for level in range(1, 5):
            tags = soup.find_all(f"h{level}")
            for tag in tags:
                text = tag.get_text(strip=True)
                if text:
                    headings.append((level, text))

        return headings

    def build_toc(self, headings: List[tuple[int, str]]) -> str:
        """Build a Markdown table of contents from headings."""
        if not headings:
            return "*No headings found*"

        toc_lines = []
        for level, text in headings:
            text = re.sub(r'\s*#+\s*$', '', text)
            indent = "  " * (level - 1)
            toc_lines.append(f"{indent}- {text}")

        return "\n".join(toc_lines)

    def clean_markdown(self, text: str) -> str:
        """Clean extracted Markdown by removing trailing # from headings."""
        lines = text.split('\n')
        cleaned = []
        prev = None
        for line in lines:
            line = re.sub(r'\s*#+\s*$', '', line)
            line = re.sub(r'^#+\s*', '# ', line)
            line = line.strip()
            if line != prev:
                cleaned.append(line)
            prev = line
        return '\n'.join(cleaned)

    def extract_content(self, html: str) -> str:
        """Extract main content using trafilatura."""
        result = trafilatura.extract(
            html,
            output_format="markdown",
            include_comments=self.valves.INCLUDE_COMMENTS,
            with_metadata=True,
            favor_precision=True,
        )

        if not result:
            soup = BeautifulSoup(html, "lxml")
            main = soup.find("main") or soup.find("article") or soup.find("body")
            if main:
                result = main.get_text(separator="\n\n", strip=True)
            else:
                result = "Unable to extract content from this page."
        else:
            result = self.clean_markdown(result)

        return result

    def build_output(
        self,
        url: str,
        metadata: dict,
        toc: str,
        content: str,
    ) -> str:
        """Build the final Markdown output."""
        title = metadata.get("title", "Untitled")
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        output_parts = [
            "---",
            f"**Title**: {title}",
            f"**Source**: {url}",
            f"**Extracted**: {date}",
            "---\n",
            "## 📑 Sommaire / Arborescence\n",
            toc,
            "\n\n## 📄 Contenu\n",
            content,
        ]

        return "\n".join(output_parts)

    def build_tree_view(self, pages: List[dict], base_url: str) -> str:
        """Build ASCII tree view of the site structure."""
        if not pages:
            return "No pages to display"
        
        tree_lines = ["```"]
        tree_lines.append(f"📁 {urlparse(base_url).netloc}/")
        
        # Build tree structure from URLs
        paths: Dict[str, List[dict]] = {}
        for page in pages:
            parsed = urlparse(page['url'])
            path = parsed.path.strip('/')
            if not path:
                path = '/'
            
            parts = path.split('/')
            if parts[0] not in paths:
                paths[pages[0]['url']] = paths.get(pages[0]['url'], [])
            
            # Group by first path component
            first_part = parts[0] if parts[0] else '/'
            if first_part not in paths:
                paths[first_part] = []
            paths[first_part].append(page)
        
        # Simple tree - group by path prefix
        folders: Dict[str, List[dict]] = {}
        root_pages = []
        
        for page in pages:
            parsed = urlparse(page['url'])
            path = parsed.path.strip('/')
            
            if '/' not in path and path:
                root_pages.append(page)
            else:
                folder = path.split('/')[0] if '/' in path else path
                if folder not in folders:
                    folders[folder] = []
                folders[folder].append(page)
        
        # Print root pages
        for page in root_pages[:5]:
            tree_lines.append(f"├── 📄 {self._slugify(page['title'])}.md")
        
        # Print folders
        for folder, folder_pages in sorted(folders.items()):
            tree_lines.append(f"├── 📁 {folder}/")
            for i, page in enumerate(folder_pages[:3]):
                prefix = "│   └──" if i == len(folder_pages[:3]) - 1 else "│   ├──"
                tree_lines.append(f"{prefix} 📄 {self._slugify(page['title'])}.md")
            if len(folder_pages) > 3:
                tree_lines.append(f"│   └── ... ({len(folder_pages) - 3} more)")
        
        tree_lines.append("```")
        
        return "\n".join(tree_lines)

    def _slugify(self, text: str) -> str:
        """Convert text to URL-friendly slug."""
        text = re.sub(r'\s*#+\s*$', '', text)
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[-\s]+', '-', text)
        return text.lower()[:50]

    def should_crawl(self, url: str, base_url: str, depth: int = 0) -> bool:
        """Check if URL should be crawled based on patterns."""
        parsed_url = urlparse(url)
        path = parsed_url.path
        
        if self.crawl_config.max_depth > 0 and depth > self.crawl_config.max_depth:
            return False
            
        if not path or path == '/':
            return True
            
        if parsed_url.netloc != urlparse(base_url).netloc:
            return False
            
        if self.crawl_config.include_pattern:
            if not re.search(self.crawl_config.include_pattern, path):
                return False
                
        if self.crawl_config.exclude_pattern:
            if re.search(self.crawl_config.exclude_pattern, path):
                return False
                
        return True

    def extract_links(self, html: str, base_url: str) -> List[str]:
        """Extract all internal links from HTML."""
        soup = BeautifulSoup(html, "lxml")
        links = set()
        
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if not href:
                continue
            if href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
                
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            
            if parsed.scheme in ("http", "https") and parsed.netloc:
                clean_url = urlunparse((
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path.rstrip("/") or "/",
                    parsed.params,
                    parsed.query,
                    ""
                ))
                links.add(clean_url)
                
        return list(links)

    def crawl_site(self, start_url: str) -> tuple[bool, Optional[List[dict]], Optional[dict]]:
        """Crawl entire site starting from start_url."""
        base_url = start_url.rstrip("/")
        visited: Set[str] = set()
        to_visit = deque([(base_url, 0)])  # (url, depth)
        pages: List[dict] = []
        
        headers = {
            "User-Agent": self.valves.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        
        progress_msg = f"🌐 **Crawl Started**\n\nScanning: `{start_url}`\n\n"
        
        with httpx.Client(timeout=self.valves.REQUEST_TIMEOUT, verify=False, follow_redirects=True) as client:
            page_num = 0
            while to_visit and len(visited) < self.crawl_config.max_pages:
                url, depth = to_visit.popleft()
                
                if url in visited:
                    continue
                    
                visited.add(url)
                page_num += 1
                
                try:
                    response = client.get(url, headers=headers)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.content, "lxml")
                    
                    title = soup.find("title")
                    title = title.get_text(strip=True) if title else "Untitled"
                    h1 = soup.find("h1")
                    if h1:
                        title = h1.get_text(strip=True)
                    title = re.sub(r'\s*#+\s*$', '', title)
                    
                    content = self.extract_content(response.text)
                    headings = self.extract_structure(response.text)
                    toc = self.build_toc(headings)
                    
                    pages.append({
                        "url": url,
                        "title": title,
                        "slug": self._slugify(title),
                        "path": urlparse(url).path,
                        "toc": toc,
                        "content": content,
                        "fetched_at": datetime.now().isoformat(),
                    })
                    
                    if page_num <= 5:
                        progress_msg += f"✓ Scraped: {title[:50]}...\n"
                    elif page_num == 6:
                        progress_msg += f"... and {len(visited) - 5} more pages\n"
                    
                    new_links = self.extract_links(response.text, base_url)
                    for link in new_links:
                        if link not in visited and self.should_crawl(link, base_url, depth + 1):
                            to_visit.append((link, depth + 1))
                    
                    time.sleep(self.crawl_config.delay_seconds)
                    
                except Exception as e:
                    continue
        
        if not pages:
            return False, None, {"error": "No pages could be scraped"}
        
        progress_msg += f"\n✅ **Crawl Complete!**\n\n{len(pages)} pages extracted\n\n"
        
        return True, pages, {"progress": progress_msg, "base_url": base_url}

    def generate_summary(self, pages: List[dict], base_url: str) -> str:
        """Generate SUMMARY.md with all pages."""
        lines = [
            "# Summary",
            "",
            f"- [{urlparse(base_url).netloc}]({base_url})",
            ""
        ]
        
        # Group by folder
        folders: Dict[str, List[dict]] = {}
        root_pages = []
        
        for page in pages:
            path = page['path'].strip('/')
            if '/' not in path and path:
                root_pages.append(page)
            else:
                folder = path.split('/')[0] if '/' in path else path
                if folder not in folders:
                    folders[folder] = []
                folders[folder].append(page)
        
        # Root pages
        if root_pages:
            lines.append("## Root")
            for page in sorted(root_pages, key=lambda p: p['title']):
                lines.append(f"- [{page['title']}](content/{page['slug']}.md)")
            lines.append("")
        
        # Folders
        for folder in sorted(folders.keys()):
            lines.append(f"## {folder}")
            for page in sorted(folders[folder], key=lambda p: p['title']):
                lines.append(f"- [{page['title']}](content/{page['slug']}.md)")
            lines.append("")
        
        return "\n".join(lines)

    def generate_metadata_json(self, pages: List[dict], base_url: str, config: CrawlConfig) -> str:
        """Generate metadata JSON for tracking."""
        metadata = {
            "crawl_info": {
                "site": base_url,
                "crawled_at": datetime.now().isoformat(),
                "total_pages": len(pages),
                "config": {
                    "max_pages": config.max_pages,
                    "delay_seconds": config.delay_seconds,
                    "include_pattern": config.include_pattern or None,
                    "exclude_pattern": config.exclude_pattern or None,
                    "max_depth": config.max_depth or "unlimited",
                }
            },
            "pages": []
        }
        
        for page in pages:
            metadata["pages"].append({
                "url": page["url"],
                "title": page["title"],
                "slug": page["slug"],
                "path": page["path"],
                "fetched_at": page["fetched_at"],
            })
        
        return json.dumps(metadata, indent=2)

    def create_zip_export(self, pages: List[dict], base_url: str) -> bytes:
        """Create ZIP file with all pages and structure."""
        buffer = io.BytesIO()
        
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add SUMMARY.md
            summary = self.generate_summary(pages, base_url)
            zf.writestr("SUMMARY.md", summary)
            
            # Add metadata
            metadata = self.generate_metadata_json(pages, base_url, self.crawl_config)
            zf.writestr("_metadata/crawl_info.json", metadata)
            
            # Add pages
            for page in pages:
                slug = page['slug'] or 'index'
                content = page['content']
                zf.writestr(f"content/{slug}.md", content)
        
        buffer.seek(0)
        return buffer.getvalue()

    def build_crawl_output(self, pages: List[dict], base_url: str) -> str:
        """Build output for crawled site."""
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        tree_view = self.build_tree_view(pages, base_url)
        
        output = [
            "---",
            f"**Site**: {base_url}",
            f"**Pages**: {len(pages)}",
            f"**Crawled**: {date}",
            "---\n",
            "## 🗂️ Arborescence\n",
            tree_view,
            "\n## 📑 Pages Crawled\n",
        ]
        
        for i, page in enumerate(pages[:15], 1):
            output.append(f"{i}. [{page['title']}]({page['url']})")
        
        if len(pages) > 15:
            output.append(f"\n... and {len(pages) - 15} more pages")
        
        output.append("\n## 📦 Export ZIP")
        output.append("Use `download` command to get the ZIP file with all Markdown pages.")
        
        return "\n".join(output)

    def parse_config_from_message(self, message: str) -> tuple[str, CrawlConfig, bool]:
        """Parse configuration from user message."""
        config = CrawlConfig()
        config.max_pages = self.valves.MAX_PAGES
        config.delay_seconds = self.valves.DELAY_SECONDS
        config.include_pattern = self.valves.INCLUDE_PATTERN
        config.exclude_pattern = self.valves.EXCLUDE_PATTERN
        config.keep_history = self.valves.KEEP_HISTORY
        
        crawl_mode = self.valves.CRAWL_ENABLED
        
        # Check for crawl prefix
        prefixes = ("crawl:", "site:", "full:", "scrape:")
        for prefix in prefixes:
            if message.lower().startswith(prefix):
                parts = message.split(" ", 1)
                if len(parts) > 1:
                    message = parts[1].strip()
                    crawl_mode = True
                break
        
        # Parse inline config: "url max:50 exclude:/blog/ include:/docs/"
        if crawl_mode:
            # Extract max pages
            max_match = re.search(r'max:(\d+)', message, re.IGNORECASE)
            if max_match:
                config.max_pages = int(max_match.group(1))
                message = re.sub(r'max:\d+', '', message, flags=re.IGNORECASE)
            
            # Extract delay
            delay_match = re.search(r'delay:([\d.]+)', message, re.IGNORECASE)
            if delay_match:
                config.delay_seconds = float(delay_match.group(1))
                message = re.sub(r'delay:[\d.]+', '', message, flags=re.IGNORECASE)
            
            # Extract exclude pattern
            exclude_match = re.search(r'exclude:([^\s]+)', message, re.IGNORECASE)
            if exclude_match:
                config.exclude_pattern = exclude_match.group(1)
                message = re.sub(r'exclude:[^\s]+', '', message, flags=re.IGNORECASE)
            
            # Extract include pattern
            include_match = re.search(r'include:([^\s]+)', message, re.IGNORECASE)
            if include_match:
                config.include_pattern = include_match.group(1)
                message = re.sub(r'include:[^\s]+', '', message, flags=re.IGNORECASE)
            
            # Extract depth
            depth_match = re.search(r'depth:(\d+)', message, re.IGNORECASE)
            if depth_match:
                config.max_depth = int(depth_match.group(1))
                message = re.sub(r'depth:\d+', '', message, flags=re.IGNORECASE)
        
        return message.strip(), config, crawl_mode

    def build_config_questions(self) -> str:
        """Build interactive configuration questions."""
        return """
🔧 **Configuration du Crawl**

Répondez aux questions ou appuyez sur Entrée pour utiliser les valeurs par défaut :

1. **Nombre max de pages ?** (défaut: 50)
   Tapez un nombre ou Entrée

2. **Exclure des sections ?** (ex: /blog/, /changelog/)
   Tapez les patterns séparés par des virgules, ou Entrée pour none

3. **Inclure seulement certaines sections ?** (ex: /docs/, /api/)
   Tapez les patterns, ou Entrée pour toutes

4. **Profondeur max ?** (1-5, 0=illimité, défaut: illimité)
   Tapez un nombre

5. **Garder l'historique ?** (O/N, défaut: O)

---
Tapez `config` suivi de vos réponses, par exemple :
`config 100 /blog/,/changelog/ /docs/ 2 O`

Ou tapez juste l'URL pour utiliser les paramètres par défaut.
"""

    def pipe(self, body: dict) -> Union[str, Generator, Iterator]:
        """Main pipeline entry point - processes URL and returns Markdown."""
        try:
            messages = body.get("messages", [])
            if messages:
                user_message = messages[-1].get("content", "").strip()
            else:
                user_message = body.get("user_message", "").strip()
        except Exception:
            user_message = ""

        if not user_message:
            return self.build_config_questions()

        # Check for config command
        if user_message.lower().startswith("config?"):
            return self.build_config_questions()
        
        # Parse configuration from message
        url, config, crawl_mode = self.parse_config_from_message(user_message)
        self.crawl_config = config

        is_valid, error_msg = self.validate_url(url)
        if not is_valid:
            return f"❌ **Erreur de validation**\n\n{error_msg}\n\nVeuillez fournir une URL valide (ex: `https://docs.example.com/page`).\n\nTapez `config?` pour voir les options de configuration."

        # Show config if crawl mode
        if crawl_mode:
            config_info = f"""
⚙️ **Configuration**
- Pages max: {config.max_pages}
- Délai: {config.delay_seconds}s
- Exclure: {config.exclude_pattern or 'none'}
- Inclure: {config.include_pattern or 'all'}
- Profondeur: {config.max_depth or 'illimitée'}
- Historique: {'Oui' if config.keep_history else 'Non'}

---
"""
            success, pages, crawl_metadata = self.crawl_site(url)
            if not success:
                return f"❌ **Erreur lors du crawl**\n\n{crawl_metadata.get('error', 'Unknown error')}"
            
            base_url = crawl_metadata.get("base_url", url)
            
            # Generate ZIP in memory (but can't send via chat - just show info)
            try:
                zip_data = self.create_zip_export(pages, base_url)
                zip_size = len(zip_data)
                zip_info = f"\n📦 **ZIP disponible** : {zip_size/1024:.1f} KB ({len(pages)} pages)\n"
            except Exception:
                zip_info = ""
            
            return config_info + self.build_crawl_output(pages, base_url) + zip_info

        # Single page extraction
        success, html, metadata = self.fetch_page(url)
        if not success:
            return f"❌ **Erreur lors de la récupération**\n\n{metadata.get('error', 'Unknown error')}\n\nVérifiez l'URL et réessayez."

        headings = self.extract_structure(html)
        toc = self.build_toc(headings)
        content = self.extract_content(html)

        return self.build_output(url, metadata, toc, content)
