#!/usr/bin/env python3
import os

session_value = os.environ.get("HTTP_SESSION", "")

print("Content-Type: text/plain")
print("X-Replace-Session: motto=This+is+the+end")
print()

if session_value:
    print(f"OMG, OMG I got cookie! {session_value}")
else:
    print("Nope, no cookie for me.")
