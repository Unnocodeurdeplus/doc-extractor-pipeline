"""
title: Doc Extractor
author: OpenWebUI
version: 1.1
description: Extract documentation URLs to Markdown, with optional full site crawling
"""

from typing import List, Union, Generator, Iterator, Optional, Set
from urllib.parse import urlparse, urljoin, urlunparse
from datetime import datetime
from collections import deque
import re
import time
import os
import zipfile
import io

import httpx
from bs4 import BeautifulSoup
import trafilatura
from pydantic import BaseModel, Field


class Pipe:
    class Valves(BaseModel):
        REQUEST_TIMEOUT: int = 10
        USER_AGENT: str = "DocExtractor/1.0 (OpenWebUI)"
        INCLUDE_COMMENTS: bool = False
        
        CRAWL_ENABLED: bool = False
        MAX_PAGES: int = 50
        DELAY_SECONDS: float = 1.0
        INCLUDE_PATTERN: str = ""
        EXCLUDE_PATTERN: str = ""

    def __init__(self):
        self.type = "pipe"
        self.id = "doc-extractor"
        self.name = "Doc Extractor/"
        self.valves = self.Valves()

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
            with httpx.Client(timeout=self.valves.REQUEST_TIMEOUT, verify=False) as client:
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

    def should_crawl(self, url: str, base_url: str) -> bool:
        """Check if URL should be crawled based on patterns."""
        parsed_url = urlparse(url)
        path = parsed_url.path
        
        if not path or path == '/':
            return True
            
        if parsed_url.netloc != urlparse(base_url).netloc:
            return False
            
        if self.valves.INCLUDE_PATTERN:
            if not re.search(self.valves.INCLUDE_PATTERN, path):
                return False
                
        if self.valves.EXCLUDE_PATTERN:
            if re.search(self.valves.EXCLUDE_PATTERN, path):
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

    def crawl_site(self, start_url: str) -> tuple[bool, Optional[str], Optional[dict]]:
        """Crawl entire site starting from start_url."""
        base_url = start_url.rstrip("/")
        visited: Set[str] = set()
        to_visit = deque([base_url])
        pages: List[dict] = []
        
        headers = {
            "User-Agent": self.valves.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        
        progress_msg = f"🌐 **Crawl Started**\n\nScanning: `{start_url}`\n\n"
        
        with httpx.Client(timeout=self.valves.REQUEST_TIMEOUT, verify=False) as client:
            page_num = 0
            while to_visit and len(visited) < self.valves.MAX_PAGES:
                url = to_visit.popleft()
                
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
                        "toc": toc,
                        "content": content,
                    })
                    
                    if page_num <= 5:
                        progress_msg += f"✓ Scraped: {title[:50]}...\n"
                    elif page_num == 6:
                        progress_msg += f"... and {len(visited) - 5} more pages\n"
                    
                    new_links = self.extract_links(response.text, base_url)
                    for link in new_links:
                        if link not in visited and self.should_crawl(link, base_url):
                            to_visit.append(link)
                    
                    time.sleep(self.valves.DELAY_SECONDS)
                    
                except Exception as e:
                    continue
        
        if not pages:
            return False, None, {"error": "No pages could be scraped"}
        
        progress_msg += f"\n✅ **Crawl Complete!**\n\n{len(pages)} pages extracted\n\nGenerating ZIP..."
        
        return True, pages, {"progress": progress_msg, "base_url": base_url}

    def build_crawl_output(self, pages: List[dict], base_url: str) -> str:
        """Build output for crawled site - returns text with info about ZIP file."""
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        output = [
            "---",
            f"**Site**: {base_url}",
            f"**Pages**: {len(pages)}",
            f"**Crawled**: {date}",
            "---\n",
            f"## 📑 Pages Crawled\n",
        ]
        
        for i, page in enumerate(pages[:20], 1):
            output.append(f"{i}. [{page['title']}]({page['url']})")
        
        if len(pages) > 20:
            output.append(f"\n... and {len(pages) - 20} more pages")
        
        output.append("\n\n## 📦 Export\n")
        output.append("To download all pages as Markdown files, use the Files API.")
        output.append("Each page is available as a separate .md file.")
        
        return "\n".join(output)

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
            return "❌ **Erreur**\n\nAucune URL fournie. Veuillez fournir une URL de documentation."

        url = user_message
        
        crawl_mode = self.valves.CRAWL_ENABLED
        if user_message.lower().startswith(("crawl:", "site:", "full:")):
            parts = user_message.split(" ", 1)
            if len(parts) > 1:
                url = parts[1].strip()
                crawl_mode = True

        is_valid, error_msg = self.validate_url(url)
        if not is_valid:
            return f"❌ **Erreur de validation**\n\n{error_msg}\n\nVeuillez fournir une URL valide (ex: `https://docs.example.com/page`)."

        if crawl_mode:
            success, pages, crawl_metadata = self.crawl_site(url)
            if not success:
                return f"❌ **Erreur lors du crawl**\n\n{crawl_metadata.get('error', 'Unknown error')}"
            
            base_url = crawl_metadata.get("base_url", url)
            return self.build_crawl_output(pages, base_url)

        success, html, metadata = self.fetch_page(url)
        if not success:
            return f"❌ **Erreur lors de la récupération**\n\n{metadata.get('error', 'Unknown error')}\n\nVérifiez l'URL et réessayez."

        headings = self.extract_structure(html)
        toc = self.build_toc(headings)
        content = self.extract_content(html)

        return self.build_output(url, metadata, toc, content)
