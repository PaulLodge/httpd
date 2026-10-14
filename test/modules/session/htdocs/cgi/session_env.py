#!/usr/bin/env python3
import os

print("Content-Type: text/plain")
print("X-Replace-Session: key1=foo&key2=&key3=bar")
print()

# Dump all environment variables so the test can check HTTP_SESSION.
for key in sorted(os.environ):
    print(f"{key}={os.environ[key]}")
