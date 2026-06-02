"""
pytest kök conftest — backend/ dizinini Python path'ine ekler.
Bu dosya backend/ altından `pytest` çalıştırıldığında `app.*` importlarını mümkün kılar.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
