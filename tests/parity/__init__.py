"""Parity tests: compare xpublish-erddap's responses with a real ERDDAP.

``capture.py`` (needs the network) opens a real ERDDAP dataset lazily through
its own griddap OPeNDAP URL, records what the real server answers for each
request in ``cases.py``, and saves a small snapshot of the dataset. The
offline test, ``tests/test_parity.py``, rebuilds the dataset from that
snapshot, serves it through xpublish-erddap, and compares.
"""
