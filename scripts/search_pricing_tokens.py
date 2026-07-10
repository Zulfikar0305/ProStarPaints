#!/usr/bin/env python3
import os,sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
file_path = os.path.join(ROOT, 'quotation', 'pricing.py')
patterns = ['packages_needed','required_litres','spread_rate_per_litre','price_per_litre','rate_per_sqm']
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i,l in enumerate(lines, start=1):
    for p in patterns:
        if p in l:
            print(f"L{i:04d}: {l.rstrip()}")
            break
