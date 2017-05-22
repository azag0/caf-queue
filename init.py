#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from app import User, db, Pushover
import json
import sys

db.create_all()
config = json.load(sys.stdin)
for user in config['users']:
    user = User(**user)
    db.session.add(user)
if 'pushover' in config:
    db.session.add(Pushover(config['pushover']))
db.session.commit()
