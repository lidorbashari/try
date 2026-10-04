import os
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))
os.environ.setdefault("DJLAB_SCRATCH", tempfile.mkdtemp(prefix="djlab_test_"))
