import os
os.environ['DATABASE_URL']='postgresql+psycopg2://risk_era:risk_era_dev@localhost:5432/risk_era'
from sqlalchemy import create_engine, text
e=create_engine(os.environ['DATABASE_URL'])
c=e.connect()
rows = c.execute(text("select table_name from information_schema.tables where table_schema='public' and table_name ilike '%audit%'"))
print(list(rows))
c.close()
