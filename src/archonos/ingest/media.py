#!/usr/bin/env python3
"""
ArchonOS Media Ingestion Module
Downloads, transcribes, and chunks various media types for knowledge base ingestion.

Usage:
    python -m archonos.ingest.media youtube <url> [--name "Title"]
    python -m archonos.ingest.media batch <file.txt>
    python -m archonos.ingest.media pdf <file.pdf>
"""

import os
import json
import subprocess
import re
import sys
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

# Try to import optional dependencies
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    YOUTUBE_TRANSCRIPT_AVAILABLE = True
except ImportError:
    YOUTUBE_TRANSCRIPT_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class MediaIngestor:
    """Ingests various media types into ArchonOS knowledge base."""
    
    def __init__(self, output_dir="kb/media"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def is_youtube_url(self, url):
        """Check if URL is a YouTube video or playlist."""
        parsed = urlparse(url)
        return 'youtube.com' in parsed.netloc or 'youtu.be' in parsed.netloc
    
    def extract_youtube_id(self, url):
        """Extract YouTube video ID from URL."""
        parsed = urlparse(url)
        if 'youtu.be' in parsed.netloc:
            return parsed.path[1:]
        elif parsed.netloc in ['www.youtube.com', 'youtube.com']:
            if parsed.path == '/watch':
                for param in parsed.query.split('&'):
                    if param.startswith('v='):
                        return param[2:]
            elif parsed.path.startswith('/embed/'):
                return parsed.path.split('/')[-1]
            elif parsed.path.startswith('/v/'):
                return parsed.path.split('/')[-1]
        return None
    
    def get_youtube_transcript(self, video_url):
        """Download YouTube transcript with timestamps."""
        if not YOUTUBE_TRANSCRIPT_AVAILABLE:
            return {"error": "youtube-transcript-api not installed"}
        
        video_id = self.extract_youtube_id(video_url)
        if not video_id:
            return None
        
        try:
            api = YouTubeTranscriptApi()
            transcript = api.fetch(video_id=video_id)
            data = list(transcript)
            
            # Convert to plain dicts
            transcript_list = []
            for item in data:
                transcript_list.append({
                    "text": item.text,
                    "start": item.start,
                    "duration": item.duration
                })
            
            return {
                'video_id': video_id,
                'url': video_url,
                'transcript': transcript_list
            }
        except Exception as e:
            return {'error': str(e)}
    
    def chunk_by_topics(self, transcript_data, min_chunk_duration=120):
        """Chunk transcript by topics or time segments."""
        if 'transcript' not in transcript_data or not transcript_data['transcript']:
            return [transcript_data]
        
        chunks = []
        current_chunk = {
            'topics': [],
            'segments': [],
            'start_time': 0,
            'duration': 0
        }
        
        for segment in transcript_data['transcript']:
            text = segment.get('text', '')
            start = segment.get('start', 0)
            duration = segment.get('duration', 0)
            
            # Simple heuristic: new chunk every ~2 minutes or on topic change
            if current_chunk['duration'] > min_chunk_duration and text.strip().endswith(('.', '!', '?')):
                chunks.append(current_chunk)
                current_chunk = {
                    'topics': [],
                    'segments': [],
                    'start_time': start,
                    'duration': 0
                }
            
            current_chunk['segments'].append(segment)
            current_chunk['duration'] = start + duration - current_chunk['start_time']
        
        # Don't forget last chunk
        if current_chunk['segments']:
            chunks.append(current_chunk)
        
        return chunks
    
    def chunk_to_markdown(self, chunk, source_name, source_url):
        """Convert chunk to markdown format."""
        segments = chunk.get('segments', [])
        
        if not segments:
            return None
        
        # Build timestamps
        timestamps = []
        content_lines = []
        
        for seg in segments:
            start = seg.get('start', 0)
            text = seg.get('text', '')
            minutes = int(start // 60)
            seconds = int(start % 60)
            timestamps.append(f"{minutes}:{seconds:02d}")
            content_lines.append(text)
        
        markdown = f"""# {source_name}

**Source:** {source_url}
**Duration:** {chunk.get('duration', 0) / 60:.1f} minutes

---

## Timestamps

"""
        
        # Add timestamps with content preview
        for i, (ts, text) in enumerate(zip(timestamps[::5], content_lines[::5])):
            markdown += f"- [{ts}](#{ts.replace(':', '')}) {text[:80]}...\n"
        
        markdown += """

## Full Transcript

"""
        
        # Add full transcript with timestamp markers
        for ts, text in zip(timestamps, content_lines):
            markdown += f"**[{ts}]** {text}\n\n"
        
        return markdown
    
    def ingest_youtube(self, video_url, source_name=None):
        """Ingest a YouTube video."""
        print(f"📥 Downloading: {video_url}")
        
        # Get transcript
        transcript_data = self.get_youtube_transcript(video_url)
        
        if not transcript_data or 'error' in transcript_data:
            print(f"❌ Failed to get transcript: {transcript_data.get('error', 'Unknown')}")
            return None
        
        # Get title if not provided
        if not source_name:
            source_name = f"YouTube Video {transcript_data.get('video_id', '')}"
        
        # Save raw transcript
        video_id = transcript_data.get('video_id')
        filepath = self.output_dir / f"{video_id}.json"
        with open(filepath, 'w') as f:
            json.dump(transcript_data, f, indent=2)
        
        # Chunk into topics
        chunks = self.chunk_by_topics(transcript_data)
        print(f"📝 Created {len(chunks)} chunks")
        
        # Convert each chunk to markdown
        output_files = []
        for i, chunk in enumerate(chunks):
            markdown = self.chunk_to_markdown(chunk, source_name, video_url)
            if markdown:
                filename = f"{video_id}_chunk_{i+1}.md"
                filepath = self.output_dir / filename
                filepath.write_text(markdown)
                output_files.append(str(filepath))
                print(f"  ✅ {filename}")
        
        return output_files
    
    def ingest_podcast(self, feed_url, max_episodes=5):
        """Ingest podcast episodes."""
        print(f"📥 Fetching podcast: {feed_url}")
        
        if not REQUESTS_AVAILABLE:
            print("❌ requests not installed")
            return []
        
        try:
            import xml.etree.ElementTree as ET
            response = requests.get(feed_url)
            root = ET.fromstring(response.content)
            
            episodes = []
            for i, item in enumerate(root.findall('.//item')):
                if i >= max_episodes:
                    break
                
                title = item.find('title').text if item.find('title') is not None else f"Episode {i+1}"
                enclosure = item.find('enclosure')
                audio_url = enclosure.get('url') if enclosure is not None else None
                
                if audio_url:
                    episodes.append({
                        'title': title,
                        'audio_url': audio_url
                    })
            
            return episodes
        except Exception as e:
            print(f"❌ Error fetching podcast: {e}")
            return []
    
    def ingest_pdf(self, pdf_path):
        """Extract text from PDF."""
        print(f"📄 Processing PDF: {pdf_path}")
        
        try:
            import pymupdf
            doc = pymupdf.open(pdf_path)
            
            text = ""
            for page in doc:
                text += page.get_text()
            
            # Chunk by pages or sections
            pages = text.split('\f')
            
            output_files = []
            for i, page_text in enumerate(pages):
                if page_text.strip():
                    filename = f"pdf_page_{i+1}.md"
                    filepath = self.output_dir / filename
                    filepath.write_text(f"# Page {i+1}\n\n{page_text}")
                    output_files.append(str(filepath))
            
            print(f"  ✅ Extracted {len(output_files)} pages")
            return output_files
            
        except ImportError:
            print("❌ pymupdf not installed. Run: uv pip install pymupdf")
            return []
        except Exception as e:
            print(f"❌ Error: {e}")
            return []
    
    def ingest_website(self, url):
        """Extract content from website."""
        print(f"🌐 Fetching: {url}")
        
        if not REQUESTS_AVAILABLE:
            print("❌ requests not installed")
            return []
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove scripts and styles
            for script in soup(['script', 'style']):
                script.decompose()
            
            # Get title
            title = soup.title.string if soup.title else url
            
            # Get main content
            main_content = soup.find('main') or soup.find('article') or soup.body
            
            # Extract text
            text = main_content.get_text(separator='\n', strip=True)
            
            # Save
            filename = f"web_{hash(url) % 10000}.md"
            filepath = self.output_dir / filename
            filepath.write_text(f"# {title}\n\n**Source:** {url}\n\n{text}")
            
            print(f"  ✅ {filename}")
            return [str(filepath)]
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return []
    
    def batch_import(self, urls_file):
        """Import multiple URLs from a file."""
        urls = Path(urls_file).read_text().strip().split('\n')
        
        for url in urls:
            url = url.strip()
            if not url or url.startswith('#'):
                continue
            
            if self.is_youtube_url(url):
                self.ingest_youtube(url)
            elif url.startswith('http'):
                self.ingest_website(url)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='ArchonOS Media Ingestor')
    parser.add_argument('command', choices=['youtube', 'podcast', 'pdf', 'web', 'batch'])
    parser.add_argument('source', help='URL or file path')
    parser.add_argument('--name', help='Source name (optional)')
    parser.add_argument('--output', default='kb/media', help='Output directory')
    
    args = parser.parse_args()
    
    ingestor = MediaIngestor(args.output)
    
    if args.command == 'youtube':
        result = ingestor.ingest_youtube(args.source, args.name)
        if result:
            print(f"\n✅ Imported {len(result)} chunks")
            print("Run: archonos import ./kb/media/")
    elif args.command == 'web':
        result = ingestor.ingest_website(args.source)
        if result:
            print(f"\n✅ Imported {len(result)} pages")
    elif args.command == 'pdf':
        result = ingestor.ingest_pdf(args.source)
        if result:
            print(f"\n✅ Imported {len(result)} pages")
    elif args.command == 'batch':
        ingestor.batch_import(args.source)
    else:
        print(f"Command {args.command} not fully implemented yet")


if __name__ == '__main__':
    main()
