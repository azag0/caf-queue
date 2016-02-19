from flask import Flask, abort, request
import json
from pathlib import Path
from itertools import dropwhile, count

app = Flask(__name__)
db_path = app.root_path + '/db.json'
if not Path(db_path).is_file():
    with open(db_path, 'w') as f:
        json.dump({}, f)


@app.route('/submit', methods=['POST'])
def submit():
    if request.method == 'POST':
        with open(db_path) as f:
            db = json.load(f)
        id = next(dropwhile(lambda x: x in db, map(str, count(1))))
        db[id] = request.get_data().decode().split()
        with open(db_path, 'w') as f:
            json.dump(db, f)
    return id


@app.route('/get/<id>')
def get(id):
    with open(db_path) as f:
        db = json.load(f)
    if id not in db:
        abort(404)
    task = db[id].pop(0)
    if not db[id]:
        del db[id]
    with open(db_path, 'w') as f:
        json.dump(db, f)
    return task


if __name__ == '__main__':
    app.run(debug=True)
