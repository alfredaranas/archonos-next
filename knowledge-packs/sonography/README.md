# Sonography Knowledge Pack

A domain knowledge pack for ArchonOS Next — ultrasound physics and diagnostic sonography education.

## What this is

A reference consumer implementation of archonos-next. The sonography content (lessons, paths, diagrams, resources) runs on top of the archonos kernel — proving the stack works end-to-end for a real domain.

Built autonomously by Hermes (MiniMax M2.5) on the Dell Precision 5530 node.

## Contents

- `wiki.py` — Flask wiki server (lessons, paths, glossary, diagrams, chat)
- `server.py` — REST API wrapping archonos search/status
- `kb/` — knowledge content: resources.json, sources.json, diagrams/
- `ui/` — web UI for sonography

## Curriculum

- Ultrasound Physics (beginner)
- Emergency Ultrasound (intermediate)  
- ARDMS Exam Prep (advanced)

Sources: YouTube, podcasts, websites, courses, practice tests, textbooks
Gulf Coast State College + MGCCC curriculum

## Running

```bash
# From archonos-next root
archonos init
archonos import knowledge-packs/sonography/kb/
python knowledge-packs/sonography/wiki.py
# open http://localhost:5002
```

## Status

- 20 lessons loaded
- 3 learning paths
- Search via archonos FTS5 kernel
- Chat requires MINIMAX_API_KEY
