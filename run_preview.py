import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.utils.config import load_env_file

load_env_file()
application = create_app()

if __name__ == "__main__":
    application.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)
