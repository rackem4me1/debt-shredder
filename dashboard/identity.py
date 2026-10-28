"""Local launcher identity, not authentication or permission to read another profile."""
from hashlib import sha256
import json
from pathlib import Path


def application_identity(application_root, data_directory):
    # Return only a fingerprint, never the private directory paths themselves.
    paths = [str(Path(application_root).resolve()), str(Path(data_directory).resolve())]
    digest = sha256(json.dumps(paths, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()
    return {'application': 'debt-shredder-local-v1', 'identity': digest}
