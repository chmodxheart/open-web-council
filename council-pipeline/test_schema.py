#!/usr/bin/env python3
"""Quick test to see what JSON schema is generated"""
import sys
import json

# Add current directory to path
sys.path.insert(0, '/home/eve/repo/open-web-council/council-pipeline')

from schemas import MultipleResponses, ResponseVariant

schema = MultipleResponses.model_json_schema()
print(json.dumps(schema, indent=2))
