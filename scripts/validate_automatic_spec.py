#!/usr/bin/env python
import os
import sys

# Ensure project root is on path
sys.path.insert(0, r"c:\Users\moh09\OneDrive\Desktop\ProStarPaints\ProStarPaints")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from specifications.services.composer import compose_sections

print("Composer validation script starting")

enriched = [
    {"section_key": "cover", "section": None},
    {"section_key": "project_overview", "section": None},
    {"section_key": "general_notes", "section": None},
]

tmpl_sections = [
    {"section_key": "cover", "visible": True, "heading": "Professional Cover"},
    {"section_key": "project_overview", "visible": False, "heading": "Project Overview"},
]

print("--- With template defaults (project_overview hidden) ---")
result = compose_sections(enriched, template_sections=tmpl_sections, instance_metadata=None)
print(result)

print("--- Without template defaults (should return all sections) ---")
result2 = compose_sections(enriched, template_sections=None, instance_metadata=None)
print(result2)

print("--- With instance override (unhide project_overview) ---")
inst_meta = [{"section_key": "project_overview", "visible": True, "heading": "Override Overview"}]
result3 = compose_sections(enriched, template_sections=tmpl_sections, instance_metadata=inst_meta)
print(result3)

print("Composer validation script finished")
