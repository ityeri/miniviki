import sys
from pathlib import Path

# importlib import mode keeps test directories off sys.path, so put this one back on it
sys.path.insert(0, str(Path(__file__).resolve().parent))
