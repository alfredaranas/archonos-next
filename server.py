#!/usr/bin/env python3
"""
ArchonOS Web UI Server
Serves the sonography knowledge base with search functionality.
"""

from flask import Flask, jsonify, request
import subprocess
import os
import sys
import json

app = Flask(__name__, static_folder='ui/sonography', static_url_path='')

# Get the project root directory
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ARCHONOS_DIR = PROJECT_ROOT

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/search')
def search():
    """Search the knowledge base"""
    query = request.args.get('q', '')
    
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    
    try:
        # Run archonos search command
        result = subprocess.run(
            [sys.executable, '-c', 
             f"import sys; sys.path.insert(0, '{ARCHONOS_DIR}/src'); "
             f"from archonos.cli.main import main; main(['search', '{query}'])"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=ARCHONOS_DIR
        )
        
        output = result.stdout
        
        # Parse the output into structured results
        results = []
        lines = output.split('\n')
        current_section = None
        current_content = []

        for line in lines:
            if '# ' in line:
                if current_section and current_content:
                    results.append({
                        'title': current_section,
                        'content': '\n'.join(current_content[:5])
                    })
                current_section = line.split('# ')[1].strip()
                current_content = []
            elif line.strip() and not line.startswith('*') and not line.startswith('|'):
                current_content.append(line.strip())

        if current_section and current_content:
            results.append({
                'title': current_section,
                'content': '\n'.join(current_content[:5])
            })

        if not results:
            results = [{'title': 'Search Results', 'content': output[:1000]}]
        
        return jsonify({'results': results[:10]})
        
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Search timeout'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/resources')
def resources():
    """Get curated resources for a discipline"""
    discipline = request.args.get('discipline', 'sonography')
    
    try:
        resources_file = os.path.join(ARCHONOS_DIR, 'kb', 'resources.json')
        with open(resources_file, 'r') as f:
            all_resources = json.load(f)
        
        if discipline in all_resources:
            return jsonify(all_resources[discipline])
        else:
            return jsonify({'error': f'No resources found for {discipline}'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def stats():
    """Get knowledge base stats"""
    try:
        result = subprocess.run(
            [sys.executable, '-c', 
             f"import sys; sys.path.insert(0, '{ARCHONOS_DIR}/src'); "
             f"from archonos.cli.main import main; main(['status'])"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=ARCHONOS_DIR
        )
        
        output = result.stdout
        stats = {}
        
        for line in output.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                stats[key.strip()] = value.strip()

        return jsonify(stats)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("🎓 Starting ArchonOS Web UI...")
    print("   Open http://localhost:5000 in your browser")
    app.run(host='0.0.0.0', port=5000, debug=True)