import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACER_PATH = PROJECT_ROOT / "posix-tracer"

loader = SourceFileLoader("posix_tracer", str(TRACER_PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
if spec is None or spec.loader is None:
    raise ImportError(f"cannot load tracer module from {TRACER_PATH}")

tracer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tracer
spec.loader.exec_module(tracer)
