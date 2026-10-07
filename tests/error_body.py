"""Read the message out of an ERDDAP error body (#36).

ERDDAP answers errors as ``Error {\\n    code=N;\\n    message="...";\\n}``, with
the message quoted as JSON (but with newlines kept), and so do we.
"""

import json
import re

_MESSAGE = re.compile(r'^    message=(".*");\n}\n\Z', re.S | re.M)


def message(response) -> str:
    """The error message, with ERDDAP's prefix (``Not Found: ...``)."""
    assert response.text.startswith("Error {\n"), response.text[:200]
    assert response.headers["content-type"] == "text/plain;charset=UTF-8"
    quoted = _MESSAGE.search(response.text).group(1)
    return json.loads(quoted.replace("\n", "\\n"))
