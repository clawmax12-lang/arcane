"""Shared pytest fixtures for ARCANE tests.

Network tests are marked ``live`` and excluded from the gate via addopts ``-m 'not live'``.
Offline recorded-bar fixtures for the data layer are added here as it is built.
"""

from __future__ import annotations
