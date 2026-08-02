#!/usr/bin/env python3
"""termux-ai: A friendly AI chat CLI for Termux and any terminal.

Single-file, zero-dependency (stdlib only). Talks to any OpenAI-compatible
endpoint, or natively to Anthropic's Messages API.
"""
import os, sys, json, sqlite3, urllib.request, urllib.error, urllib.parse, subprocess, atexit, shutil, time, threading, re, html, shlex, signal, ipaddress
import select, tempfile
import zipfile
from pathlib import Path

__version__ = "6.8.0"
