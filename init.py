#!/usr/bin/env python3

from app import User, db, Pushover
import json
import sys

db.create_all()
config = json.load(sys.stdin)
for user in config['users']:
    user = User(**user)
    db.session.add(user)
db.session.add(Pushover(config['pushover']))
db.session.commit()
