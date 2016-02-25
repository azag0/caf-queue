#!/usr/bin/env python3

from app import User, db
import yaml
import sys

db.create_all()
users = yaml.load(sys.stdin)
for token in users:
    user = User(token)
    db.session.add(user)
db.session.commit()
