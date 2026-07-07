from querysmith.config import load_config
from querysmith.db import make_engine, test_connection
print(test_connection(make_engine(load_config())))