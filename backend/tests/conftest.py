import os
import sys

# Pozwala uruchamiać `pytest` zarówno z backend/, jak i z korzenia repo,
# bez instalowania `app` jako pakietu.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
