#!/usr/bin/env python3
"""
ArchonOS Wiki Server
A Flask-based wiki that serves content from the ArchonOS knowledge base.
Features: Paths, Modules, Search, Glossary, Diagrams, Chat
"""

from flask import Flask, render_template_string, jsonify, request
import os
import json
from pathlib import Path
import re
from datetime import datetime
from urllib.parse import quote

app = Flask(__name__)

# Paths
KB_DIR = Path("kb")
LESSONS_DIR = KB_DIR / "lessons"
TRANSCRIPTS_DIR = KB_DIR / "transcripts"
DIAGRAMS_DIR = KB_DIR / "diagrams"

def get_lessons():
    """Get all lessons from the lessons directory."""
    lessons = []
    if LESSONS_DIR.exists():
        for f in LESSONS_DIR.glob("*.md"):
            content = f.read_text()
            title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            title = title_match.group(1) if title_match else f.name
            duration_match = re.search(r'\*\*Duration:\*\*\s+([\d.]+)', content)
            duration = duration_match.group(1) if duration_match else "0"
            lessons.append({"id": f.stem, "title": title, "duration": float(duration), "file": f.name})
    return lessons

def get_lesson_content(lesson_id):
    """Get full lesson content."""
    lesson_file = LESSONS_DIR / f"{lesson_id}.md"
    if lesson_file.exists():
        return lesson_file.read_text()
    return None

def get_paths():
    """Get learning paths with modules."""
    return [
        {
            "id": "ultrasound-physics",
            "title": "Ultrasound Physics",
            "description": "Master the fundamentals of ultrasound physics",
            "difficulty": "beginner",
            "modules": [
                {"id": "w7VfXjrgjWo", "title": "Ultrasound Physics Basics", "duration": 10.4},
                {"id": "GOWlzuMziUU", "title": "Ultrasound Artifacts", "duration": 17.2},
                {"id": "pJziNYKutYA", "title": "Ultrasound Physics Explained", "duration": 7.8},
                {"id": "m1VcsUhmHqg", "title": "Ultrasound Physics Lecture 1", "duration": 15.1},
                {"id": "28ZgqgrQabc", "title": "Ultrasound Physics Made Easy", "duration": 5.2},
            ]
        },
        {
            "id": "emergency-ultrasound",
            "title": "Emergency Ultrasound",
            "description": "Point-of-care ultrasound for emergency medicine",
            "difficulty": "intermediate",
            "modules": [
                {"id": "s23_d-qeEn4", "title": "Basic Ultrasound Physics for EM", "duration": 25.3},
                {"id": "h1LIu1dl-k8", "title": "Ultrasound Beam", "duration": 18.6},
                {"id": "b1Eh4a1umdw", "title": "Ultrasound Physics - Image Generation", "duration": 22.4},
            ]
        },
        {
            "id": "exam-prep",
            "title": "ARDMS Exam Prep",
            "description": "Prepare for ARDMS registry certification",
            "difficulty": "advanced",
            "modules": []
        }
    ]

def get_glossary():
    """Get glossary terms from lessons."""
    return [
        {"term": "Artifact", "definition": "A misrepresentation of anatomy on an ultrasound image"},
        {"term": "Reverberation", "definition": "Sound wave bouncing between two reflectors"},
        {"term": "Mirror Artifact", "definition": "Object appears on opposite side of strong reflector"},
        {"term": "Ring Down", "definition": "Artifact caused by fluid between microbubbles"},
        {"term": "Comet Tail", "definition": "Series of reverberations appearing as bright band"},
        {"term": "Side Lobe", "definition": "Artifact from ultrasound beam side lobes"},
        {"term": "Specular Reflector", "definition": "Large smooth interface reflecting sound"},
        {"term": "Attenuation", "definition": "Decrease in sound wave amplitude"},
        {"term": "Piezoelectric", "definition": "Crystal that converts electrical to sound energy"},
        {"term": "Doppler", "definition": "Change in frequency due to moving reflectors"},
    ]

def get_diagrams():
    """Get all diagram files."""
    diagrams = []
    if DIAGRAMS_DIR.exists():
        for f in DIAGRAMS_DIR.glob("*.md"):
            content = f.read_text()
            title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            title = title_match.group(1) if title_match else f.stem
            diagrams.append({
                "id": f.stem,
                "title": title,
                "file": f.name,
                "content": content
            })
    return diagrams

# HTML Template
HOME_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎓 Sonography Wiki</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%); min-height: 100vh; color: #eee; }
        .container { max-width: 1100px; margin: 0 auto; padding: 20px; }
        nav { display: flex; gap: 30px; padding: 20px 0; border-bottom: 1px solid rgba(255,255,255,0.1); margin-bottom: 30px; }
        nav a { color: #aaa; text-decoration: none; font-weight: 500; transition: color 0.3s; }
        nav a:hover, nav a.active { color: #00d9ff; }
        header { text-align: center; padding: 40px 0; }
        h1 { font-size: 3rem; margin-bottom: 10px; }
        h1 span { background: linear-gradient(90deg, #00d9ff, #00ff88); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .search-box { background: rgba(255,255,255,0.05); border-radius: 16px; padding: 20px; margin: 30px 0; display: flex; gap: 10px; }
        .search-box input { flex: 1; padding: 15px 20px; font-size: 1.1rem; border: none; border-radius: 10px; background: rgba(0,0,0,0.3); color: #fff; outline: none; }
        .search-box button { padding: 15px 30px; font-size: 1rem; border: none; border-radius: 10px; background: linear-gradient(135deg, #00d9ff, #00ff88); color: #0f0c29; font-weight: bold; cursor: pointer; }
        .section { margin: 40px 0; }
        .section h2 { color: #00ff88; margin-bottom: 20px; font-size: 1.5rem; }
        .path-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .path-card { background: rgba(255,255,255,0.05); border-radius: 16px; padding: 25px; border: 1px solid rgba(255,255,255,0.1); transition: all 0.3s; }
        .path-card:hover { transform: translateY(-5px); border-color: #00d9ff; }
        .path-card h3 { color: #00d9ff; margin-bottom: 10px; }
        .path-card p { color: #888; margin-bottom: 15px; }
        .stats { display: flex; justify-content: center; gap: 40px; margin: 40px 0; }
        .stat { text-align: center; }
        .stat-value { font-size: 2.5rem; font-weight: bold; color: #00d9ff; }
        .stat-label { color: #666; }
        footer { text-align: center; padding: 40px; color: #444; border-top: 1px solid rgba(255,255,255,0.1); margin-top: 60px; }
        .badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: bold; text-transform: uppercase; }
        .badge.beginner { background: rgba(0,255,136,0.2); color: #00ff88; }
        .badge.intermediate { background: rgba(255,200,0,0.2); color: #ffc800; }
        .badge.advanced { background: rgba(255,100,100,0.2); color: #ff6464; }
    </style>
</head>
<body>
    <div class="container">
        <nav>
            <a href="/" class="active">Home</a>
            <a href="/paths">Paths</a>
            <a href="/modules">Modules</a>
            <a href="/glossary">Glossary</a>
            <a href="/diagrams">Diagrams</a>
            <a href="/search">Search</a>
            <a href="/chat">Chat</a>
        </nav>
        <header>
            <h1>🎓 <span>Sonography Wiki</span></h1>
            <p class="tagline">AI-Powered Ultrasound Education</p>
        </header>
        <div class="search-box">
            <input type="text" id="searchInput" placeholder="Search lessons, concepts, artifacts...">
            <button onclick="search()">Search</button>
        </div>
        <div class="stats">
            <div class="stat"><div class="stat-value">8</div><div class="stat-label">Video Lessons</div></div>
            <div class="stat"><div class="stat-value">3</div><div class="stat-label">Learning Paths</div></div>
            <div class="stat"><div class="stat-value">2</div><div class="stat-label">Diagrams</div></div>
        </div>
        <div class="section">
            <h2>📚 Learning Paths</h2>
            <div class="path-grid">
                {% for path in paths %}
                <div class="path-card">
                    <span class="badge {{ path.difficulty }}">{{ path.difficulty }}</span>
                    <h3>{{ path.title }}</h3>
                    <p>{{ path.description }}</p>
                </div>
                {% endfor %}
            </div>
        </div>
        <footer><p>🎓 Sonography Wiki · Built with ArchonOS</p></footer>
    </div>
    <script>
        function search() { const q = document.getElementById('searchInput').value; if (q) window.location.href = '/search?q=' + encodeURIComponent(q); }
        document.getElementById('searchInput').addEventListener('keypress', e => { if (e.key === 'Enter') search(); });
    </script>
</body>
</html>"""

# Routes
@app.route('/')
def home():
    lessons = get_lessons()
    paths = get_paths()
    return render_template_string(HOME_TEMPLATE, lessons=lessons, paths=paths)

@app.route('/paths')
def paths():
    return home()

@app.route('/modules')
def modules():
    lessons = get_lessons()
    return render_template_string(HOME_TEMPLATE, lessons=lessons, paths=get_paths())

@app.route('/module/<lesson_id>')
def module(lesson_id):
    content = get_lesson_content(lesson_id)
    if not content:
        return "Lesson not found", 404
    lessons = get_lessons()
    lesson = next((l for l in lessons if l["id"] == lesson_id), {"title": lesson_id, "duration": 0, "id": lesson_id})
    return f"<html><body><h1>{lesson['title']}</h1><pre>{content[:1000]}</pre></body></html>"

@app.route('/glossary')
def glossary():
    terms = get_glossary()
    return f"<html><body><h1>Glossary</h1>{'<br>'.join([f'{t['term']}: {t['definition']}' for t in terms])}</body></html>"

@app.route('/search')
def search():
    query = request.args.get('q', '')
    results = []
    if query:
        lessons = get_lessons()
        for lesson in lessons:
            content = get_lesson_content(lesson["id"]) or ""
            if query.lower() in content.lower() or query.lower() in lesson["title"].lower():
                results.append({"title": lesson["title"], "snippet": content[:200]})
    return f"<html><body><h1>Search: {query}</h1>{len(results)} results</body></html>"

# Diagrams routes
@app.route('/diagrams')
def diagrams_page():
    diagrams = get_diagrams()
    return f"<html><body><h1>Diagrams</h1>{'<br>'.join([f'<a href=\"/diagram/{d['id']}\">{d['title']}</a>' for d in diagrams])}</body></html>"

@app.route('/diagram/<diagram_id>')
def diagram_page(diagram_id):
    diagrams = get_diagrams()
    diagram = next((d for d in diagrams if d["id"] == diagram_id), None)
    if not diagram:
        return "Diagram not found", 404
    mermaid_url = f"https://mermaid.live/edit/#{quote(diagram['content'])}"
    return f"""<html><body>
        <h1>{diagram['title']}</h1>
        <pre style="background:#222;padding:20px;border-radius:10px;overflow:auto;">{diagram['content']}</pre>
        <p><a href="{mermaid_url}" target="_blank">🎨 Edit in Mermaid Live Editor</a></p>
    </body></html>"""

# API routes
@app.route('/api/lessons')
def api_lessons():
    return jsonify(get_lessons())

@app.route('/api/paths')
def api_paths():
    return jsonify(get_paths())

@app.route('/api/diagrams')
def api_diagrams():
    return jsonify(get_diagrams())

# Chat routes (simplified)
@app.route('/chat')
def chat_page():
    return """<!DOCTYPE html>
<html><head><title>Chat - Sonography Wiki</title></head>
<body style="background:#0f0c29;color:#eee;font-family:sans-serif;padding:40px;text-align:center;">
    <h1>💬 AI Tutor</h1>
    <p>Chat feature requires MINIMAX_API_KEY to be set locally.</p>
    <p>Run: <code>export MINIMAX_API_KEY="your-key"</code></p>
    <p><a href="/" style="color:#00d9ff;">← Back to Home</a></p>
</body></html>"""

@app.route('/api/chat', methods=['POST'])
def api_chat():
    return jsonify({"error": "API key not configured"})

if __name__ == '__main__':
    print("🎓 Starting Sonography Wiki...")
    print("   Open http://localhost:5002")
    app.run(host='0.0.0.0', port=5002, debug=True)
