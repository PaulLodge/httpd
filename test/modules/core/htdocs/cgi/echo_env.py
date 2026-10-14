#!/usr/bin/env python3
import os
import json

print("Content-Type: application/json")
print()

data = {}
for key, value in os.environ.items():
    data[key] = value

print(json.dumps(data, indent=2))
